"""Checks for the authored candidate files against canonical data (aliases, source maps, hadith selection).

Each check reads an authored YAML file, verifies every claim against
corpus/canonical, and returns the file's data with its status fields filled in.
Nothing here decides religious correctness: a passing check only means the
claim is consistent with the source text, so every entry stays draft.
"""
from pathlib import Path
import re

import yaml

from ..rag import normalize
from .hadith import compare_tokens

QURAN_REF = re.compile(r"^quran:(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?$")


def parse_quran_ref(ref: str) -> tuple[int, int, int]:
    match = QURAN_REF.match(ref)
    if not match:
        raise ValueError(f"{ref!r} is not a quran:S:A or quran:S:A-B reference")
    surah, first = int(match.group(1)), int(match.group(2))
    return surah, first, int(match.group(3) or first)


def _search(text: str) -> str:
    return f" {normalize.search_text(text)} "


def check_aliases(data: dict, simple: dict[tuple[int, int], str]) -> tuple[dict, dict]:
    searchable = {key: _search(text) for key, text in simple.items()}
    summary = {"prophets": 0, "arabic_checked": 0, "arabic_needs_check": 0, "latin_or_arabizi": 0}
    for prophet in data["prophets"]:
        summary["prophets"] += 1
        for entry in prophet.get("names_ar", []) + prophet.get("titles_ar", []):
            evidence = entry.get("evidence")
            if evidence == "auto":
                needle = _search(entry["alias"]).strip()
                found = [f"quran:{s}:{a}" for (s, a), text in sorted(searchable.items()) if needle in text]
                entry["found_in"] = {"count": len(found), "first": found[:3]}
                ok = bool(found)
            elif isinstance(evidence, dict):
                surah, first, last = parse_quran_ref(evidence["ref"])
                needle = _search(evidence["phrase"]).strip()
                ok = any(needle in searchable.get((surah, ayah), "") for ayah in range(first, last + 1))
            else:
                ok = False
            entry["status"] = "evidence_found" if ok else "needs_check"
            summary["arabic_checked" if ok else "arabic_needs_check"] += 1
        spellings = len(prophet.get("latin", [])) + len(prophet.get("arabizi", []))
        summary["latin_or_arabizi"] += spellings
        prophet["spellings_status"] = "needs_check"
    if summary["prophets"] != 25:
        raise ValueError(f"aliases.yaml lists {summary['prophets']} prophets, expected the 25 named in the Quran")
    return data, summary


def check_source_map(data: dict, simple: dict[tuple[int, int], str], aliases: dict) -> tuple[dict, dict]:
    prophet = next((p for p in aliases["prophets"] if p["id"] == data["prophet_id"]), None)
    if prophet is None:
        raise ValueError(f"source map prophet_id {data['prophet_id']!r} is not in aliases.yaml")
    needles = [_search(entry["alias"]).strip() for entry in prophet["names_ar"] + prophet.get("titles_ar", [])]
    summary = {"ranges": 0, "ayat": 0, "needs_check": 0, "missing_ayat": 0}
    for item in data["ranges"]:
        surah, first, last = parse_quran_ref(item["ref"])
        keys = [(surah, ayah) for ayah in range(first, last + 1)]
        exists = all(key in simple for key in keys) and first <= last
        named = exists and any(needle in _search(simple[key]) for key in keys for needle in needles)
        item["checks"] = {"exists": exists, "prophet_named_in_range": bool(named)}
        item["verification"] = "ok" if exists and named and item.get("confidence") == "high" else "needs_check"
        summary["ranges"] += 1
        summary["ayat"] += len(keys) if exists else 0
        summary["missing_ayat"] += 0 if exists else 1
        summary["needs_check"] += item["verification"] == "needs_check"
    return data, summary


def _contains(words: list[str], phrase: list[str]) -> bool:
    """Phrase inside the text, allowing attached prefixes on its first word (و، ف، ب ...)."""
    return " ".join(phrase) + " " in " ".join(words) + " "


def check_selection(data: dict, records: dict[str, dict], clusters: dict[str, dict],
                    nawawi_links: dict[str, dict]) -> tuple[dict, dict]:
    """records: ref -> canonical row for bukhari/muslim/nawawi40; clusters: ref -> cluster info."""
    words_cache: dict[str, list[str]] = {}

    def words(ref: str) -> list[str]:
        if ref not in words_cache:
            words_cache[ref] = compare_tokens(records[ref]["arabic_text"])
        return words_cache[ref]

    summary = {"entries": 0, "ok": 0, "needs_check": 0}
    seen_clusters: dict[str, int] = {}
    for position, item in enumerate(data["hadith"], 1):
        summary["entries"] += 1
        reasons = []
        if item["collection"] == "nawawi40":
            link = nawawi_links.get(item["number"], {"status": "not_linked", "ref": None})
            item["linked_record"] = link["ref"]
            ref = link["ref"]
            if link["status"] != "linked":
                reasons.append(f"nawawi_link_{link['status']}")
        else:
            phrase = compare_tokens(item["lookup_phrase"])
            hits = [ref for ref, row in records.items() if ref.startswith(item["collection"] + ":")
                    and row["eligible"] and _contains(words(ref), phrase)]
            hits.sort(key=lambda r: (clusters[r]["primary"] != r, float(r.split(":")[1].split(".")[0])))
            item["lookup_matches"] = len(hits)
            ref = hits[0] if hits else None
            if ref:
                item["number"] = ref.split(":", 1)[1]
            else:
                reasons.append("lookup_phrase_not_found_in_eligible_records")
        if ref:
            row = records[ref]
            info = clusters[ref]
            item["ref"] = ref
            item["cluster_id"] = info["cluster_id"]
            item["cluster_primary"] = info["primary"]
            if not row["eligible"]:
                reasons.append("record_not_eligible")
            if not row["arabic_text"].strip():
                reasons.append("empty_text")
            if info["cluster_id"] in seen_clusters:
                reasons.append(f"same_cluster_as_entry_{seen_clusters[info['cluster_id']]}")
            seen_clusters.setdefault(info["cluster_id"], position)
        item["needs_check"] = bool(reasons)
        item["check_reasons"] = reasons
        summary["needs_check" if reasons else "ok"] += 1
    if summary["entries"] != 40:
        raise ValueError(f"hadith_selection.yaml lists {summary['entries']} hadith, expected 40")
    return data, summary


def load_yaml(path: Path) -> tuple[str, dict]:
    text = Path(path).read_text(encoding="utf-8")
    header = text[:text.index("schema_version:")]
    return header, yaml.safe_load(text)


def save_yaml(path: Path, header: str, data: dict) -> None:
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000, default_flow_style=None)
    Path(path).write_text(header + body, encoding="utf-8", newline="\n")
