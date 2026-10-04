"""Look up the glossary's terms in the Jamharah dictionary and write one snapshot file (reference package task).

    python scripts/crawl_jamharah.py --record                 crawl, write the snapshot, record its digest
    python scripts/crawl_jamharah.py --cache-dir DIR --record  keep every response in DIR; a rerun reads it
    python scripts/crawl_jamharah.py --dry-run                 list the terms and queries, request nothing

Polite by construction: its own user agent, robots.txt read first and obeyed for every URL, at least
5 seconds between requests (6 by default), a hard request budget (default 140, robots.txt included), and
it stops at the first 403 or 429. It uses the site's search page (`/search?query=..&type=word`), never
/api/ (disallowed by robots.txt), and reads only the matched entries: the package's page-7 terms and the
glossary's `sensitive` terms first, then the other words, until the budget ends. With --cache-dir, a rerun
reads every earlier response from the cache and spends the budget only on what is still missing.

Output: corpus/raw/jamharah-dictionary-entries/jamharah-dictionary-entries.json, outside git (third-party
text). Per term: the query, the matched entry's id and url, its Arabic title, the definition sections, the
English equivalent when the entry has an English translation, and when it was fetched. Unmatched terms are
listed, never guessed. With --record, the snapshot's sha256 and retrieval time go into the registry entry
`jamharah-dictionary-entries` (nothing else in the registry changes); its status stays a governance decision.
Exit status: 0 done, 1 stopped by the site (403/429) or by robots.txt, 2 refused (a recorded snapshot exists).
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.robotparser import RobotFileParser

import httpx
import yaml

import _common  # noqa: F401
from _common import REGISTRY, ROOT
from companion_api.corpusprep import fetch, jamharah, registry as registry_module

SOURCE_ID = "jamharah-dictionary-entries"
USER_AGENT = "badr-corpus-fetch/1 (+offline corpus preparation)"
GLOSSARY = ROOT / "corpus/glossary_cross_lingual.yaml"
MIN_DELAY = 5.0
CRAWLER_VERSION = "jamharah-crawl-v1"


class Stopped(RuntimeError):
    pass


class Budget(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Client:
    """GET with robots.txt, a minimum delay, a request budget and an optional response cache."""

    def __init__(self, *, delay: float, budget: int, cache_dir: Path | None, out=sys.stderr):
        self.delay, self.budget, self.cache_dir, self.out = max(delay, MIN_DELAY), budget, cache_dir, out
        self.requests, self.cached, self.last = 0, 0, 0.0
        self.http = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.5"},
                                 timeout=30.0, follow_redirects=False)
        self.robots: RobotFileParser | None = None
        self.memory: dict[str, tuple[int, str, str]] = {}

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + ".json")

    def get(self, url: str) -> tuple[int, str, str]:
        """(status, body, fetched_at). Cached and repeated responses cost no request."""
        if url in self.memory:
            return self.memory[url]
        cached = self._cache_path(url)
        if cached is not None and cached.is_file():
            data = json.loads(cached.read_text(encoding="utf-8"))
            self.cached += 1
            return data["status"], data["body"], data["fetched_at"]
        if self.robots is not None and not self.robots.can_fetch(USER_AGENT, url):
            raise Stopped(f"robots.txt disallows {url}")
        if self.requests >= self.budget:
            raise Budget(f"request budget of {self.budget} reached")
        wait = self.last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            response = self.http.get(url)
        finally:
            self.last = time.monotonic()
            self.requests += 1
        fetched_at = _now()
        print(f"  [{self.requests:>3}] {response.status_code} {url}", file=self.out, flush=True)
        if response.status_code in (403, 429):
            raise Stopped(f"HTTP {response.status_code} at {url}: the site refused; stopping")
        body = response.text
        if cached is not None and response.status_code == 200:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps({"url": url, "status": response.status_code, "body": body,
                                          "fetched_at": fetched_at}, ensure_ascii=False), encoding="utf-8")
        self.memory[url] = (response.status_code, body, fetched_at)
        return self.memory[url]

    def read_robots(self) -> None:
        status, body, _ = self.get(f"{jamharah.BASE}/robots.txt")
        parser = RobotFileParser()
        parser.parse(body.splitlines() if status == 200 else [])
        self.robots = parser
        for probe in (jamharah.search_url("x"), jamharah.entry_url(1), jamharah.entry_url(1, "en")):
            if not parser.can_fetch(USER_AGENT, probe):
                raise Stopped(f"robots.txt disallows {probe}")
        crawl_delay = parser.crawl_delay(USER_AGENT)
        if crawl_delay:
            self.delay = max(self.delay, float(crawl_delay))


def _entry(client: Client, entry_id: int, language: str):
    status, body, fetched_at = client.get(jamharah.entry_url(entry_id, None if language == "ar" else language))
    if status != 200:
        return None, fetched_at, f"HTTP {status}"
    try:
        return jamharah.parse_entry(body, entry_id, language), fetched_at, None
    except ValueError as error:
        return None, fetched_at, str(error)


def _read(client: Client, row: dict, language: str) -> None:
    """Reads one entry page into `row`: the English heading and definition, or the Arabic definition."""
    entry, fetched_at, problem = _entry(client, row["entry_id"], language)
    row["fetched_at"] = fetched_at
    row.setdefault("pages_read", []).append(language)
    if entry is None:
        row.setdefault("entry_problems", []).append(f"{language}: {problem}")
    elif language == "en":
        if entry.title:
            row.update(english=entry.title, url_en=jamharah.entry_url(row["entry_id"], "en"),
                       definition_en=entry.sections)
    else:
        row.update(title_ar=entry.title_ar or row["title_ar"], categories=entry.categories or row["categories"],
                   definition_ar=entry.sections, translations=entry.translations)
        if not row.get("english") and "en" in entry.translations:
            row["english_listed_but_empty"] = True


def crawl(terms: list[dict], client: Client) -> tuple[list[dict], str | None, bool]:
    """Searches every query, then reads the matched entries in priority order until the budget ends.

    Returns the rows, why the crawl stopped early (or None) and whether the site or robots.txt stopped it.
    """
    rows = [{"term": term["term"], "query": term["query"], "origin": term["origin"],
             "sensitive": term.get("sensitive", False), "status": "not_searched", "fetched_at": None} for term in terms]
    try:
        for row in rows:  # 1. one search per distinct query (repeats come from the client's memory)
            status, body, fetched_at = client.get(jamharah.search_url(row["query"]))
            hits = jamharah.parse_search(body) if status == 200 else []
            chosen, others = jamharah.choose(row["query"], hits)
            row.update(fetched_at=fetched_at, results_on_first_page=len(hits))
            if status != 200:
                row.update(status="search_failed", reason=f"HTTP {status}")
            elif chosen is None:
                row.update(status="unmatched", reason="no entry with this exact title on the first results page")
            else:
                row.update(status="matched", entry_id=chosen.entry_id, url=jamharah.entry_url(chosen.entry_id),
                           title_ar=chosen.title, categories=list(chosen.categories), english=None,
                           alternatives=[hit.entry_id for hit in others])
        # 2. The entries, in tiers: the package's page-7 terms and the glossary's sensitive terms first, then
        # the other words. Per tier, the English page (its heading is the English equivalent, empty when there
        # is none), then the Arabic page where there is no English text. The Arabic page of a page-7 term that
        # has English text comes last. The budget may end before the last tier.
        matched = [row for row in rows if row["status"] == "matched"]
        first = [row for row in matched if row["origin"] == "package_page_7" or row["sensitive"]]
        for tier in (first, [row for row in matched if row not in first]):
            for row in tier:
                _read(client, row, "en")
            for row in tier:
                if not row.get("english"):
                    _read(client, row, "ar")
        for row in matched:
            if row["origin"] == "package_page_7" and row.get("english"):
                _read(client, row, "ar")
    except Budget as error:
        return rows, str(error), False
    except Stopped as error:
        return rows, str(error), True
    return rows, None, False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--glossary", type=Path, default=GLOSSARY)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "corpus/raw")
    parser.add_argument("--max-requests", type=int, default=140, help="hard budget, robots.txt included")
    parser.add_argument("--delay", type=float, default=6.0, help=f"seconds between requests (at least {MIN_DELAY})")
    parser.add_argument("--cache-dir", type=Path, help="keep responses here; a rerun reads them instead of the site")
    parser.add_argument("--record", action="store_true", help="record the snapshot's sha256 in the registry")
    parser.add_argument("--refresh", action="store_true", help="replace a snapshot whose digest is recorded")
    parser.add_argument("--dry-run", action="store_true", help="list the terms and queries; request nothing")
    args = parser.parse_args(argv)

    terms = jamharah.lookup_terms(yaml.safe_load(args.glossary.read_text(encoding="utf-8")))
    if args.dry_run:
        for term in terms:
            print(f"{term['origin']:<15} {term['term']}  ->  {term['query']}")
        print(f"{len(terms)} terms, {len({t['query'] for t in terms})} distinct queries")
        return 0
    registry = registry_module.load(args.registry)
    source = registry.get(SOURCE_ID)
    target = fetch.raw_path(args.raw_dir, source)
    if source["sha256"] and target.is_file() and not args.refresh:
        print(f"{target} is recorded in the registry; rerun with --refresh to replace it", file=sys.stderr)
        return 2

    client = Client(delay=args.delay, budget=args.max_requests, cache_dir=args.cache_dir)
    started = _now()
    try:
        client.read_robots()
    except Stopped as error:
        print(f"STOPPED: {error}", file=sys.stderr)
        return 1
    rows, stopped, blocked = crawl(terms, client)
    snapshot = {
        "schema_version": 1, "source_id": SOURCE_ID, "site": f"{jamharah.BASE}/dictionary",
        "publisher": "Osool Center (مركز أصول), islamic-content.com", "crawler": "scripts/crawl_jamharah.py",
        "crawler_version": CRAWLER_VERSION, "parser_version": jamharah.PARSER_VERSION, "user_agent": USER_AGENT,
        "robots_txt": "read first and obeyed; /api/ is disallowed, so the site search page is used",
        "delay_seconds": client.delay, "started_at": started, "finished_at": _now(),
        "requests": client.requests, "responses_from_cache": client.cached, "stopped": stopped,
        "glossary": (args.glossary.relative_to(ROOT) if args.glossary.is_relative_to(ROOT) else args.glossary).as_posix(),
        "terms": rows,
        "unmatched": [row["term"] for row in rows if row["status"] != "matched"],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    target.write_bytes(data)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    english = sum(1 for row in rows if row.get("english"))
    print(f"wrote {target} ({len(rows)} terms: {counts}; English equivalents: {english}; "
          f"requests: {client.requests}, from cache: {client.cached})")
    if stopped:
        print(f"STOPPED: {stopped}", file=sys.stderr)
    if blocked:
        return 1
    if args.record:
        source["sha256"] = hashlib.sha256(data).hexdigest()
        source["retrieved_at"] = snapshot["finished_at"]
        registry_module.save(registry)
        print(f"recorded {SOURCE_ID}: sha256 {source['sha256']}, retrieved_at {source['retrieved_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
