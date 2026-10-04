#!/usr/bin/env python3
"""Validate the Arabic competition corpus candidate.

The Quran is not stored here: sources.json names the registry's pinned Quranpedia mushaf
(corpus/sources/registry.yaml), and this check verifies the file scripts/fetch_sources.py placed in
corpus/raw/ by the registry's sha256 and its coverage (114 surahs, 6236 ayat).
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from companion_api.corpusprep import fetch, registry as registry_module  # noqa: E402
from companion_api.corpusprep.quranpedia import QuranpediaError, load as load_dump  # noqa: E402

REGISTRY = REPO / "corpus/sources/registry.yaml"
RAW = REPO / "corpus/raw"
QURAN = re.compile(r"quran:(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?\Z")
HADITH = re.compile(r"hadith:([a-z-]+):(\d+)\Z")
FIQH = re.compile(r"fiqh:[a-z-]+:[a-z-]+\Z")


def load(folder, name):
    with (folder / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def check_quran(quran_source, verse_counts, registry_path, raw_root):
    """Problems with the registry-pinned Quran file: registered, present, the registry's sha256, full coverage."""
    errors = []
    try:
        registry = registry_module.load(registry_path)
        entry = registry.get(quran_source["registry_source_id"])
        license_entry = registry.get(quran_source["registry_license_source_id"])
    except (OSError, registry_module.RegistryError, KeyError) as exc:
        return [f"Quran source not in the registry: {exc}"]
    for source in (entry, license_entry):
        path = fetch.raw_path(raw_root, source)
        if not source.get("sha256"):
            errors.append(f"{source['source_id']}: no sha256 in the registry")
        elif not path.is_file():
            errors.append(f"{source['source_id']}: {path} is missing; run scripts/fetch_sources.py")
        elif fetch.digest(path) != source["sha256"]:
            errors.append(f"{source['source_id']}: {path} does not match the registry's sha256")
    if errors:
        return errors
    try:
        mushaf = load_dump(fetch.raw_path(raw_root, entry))
        surahs = mushaf["data"]["surahs"]
        if len(surahs) != 114 or sum(len(s["ayahs"]) for s in surahs) != 6236:
            errors.append("Quran source coverage is not 114 surahs / 6236 ayahs")
        actual_counts = {s["id"]: len(s["ayahs"]) for s in surahs}
        if any(actual_counts.get(n) != count for n, count in verse_counts.items()):
            errors.append("Quran verse-count metadata mismatch")
        if any([a["number"] for a in s["ayahs"]] != list(range(1, len(s["ayahs"]) + 1)) for s in surahs):
            errors.append("Quran ayah numbering is not sequential")
        if mushaf["license"]["version"] != quran_source["dump_version_in_file"]:
            errors.append("Quran source version mismatch")
    except (QuranpediaError, KeyError, ValueError, TypeError) as exc:
        errors.append(f"Quran source unreadable: {exc}")
    return errors


def validate(folder=HERE, release=False, registry_path=REGISTRY, raw_root=RAW):
    """(errors, summary line) for the package in `folder`."""
    content, sources = load(folder, "content.json"), load(folder, "sources.json")
    errors = []
    items = []
    ids = set()
    domains = set(sources["policy"]["allowed_domains"])
    verse_counts = {int(k): v for k, v in sources["quran_verse_counts_used"].items()}
    quran_source = next((s for s in sources["sources"] if s["id"] == "quranpedia-quran"), None)
    if not quran_source:
        errors.append("Quran source missing")
    else:
        errors += check_quran(quran_source, verse_counts, registry_path, raw_root)

    def check_item(item):
        item_id = item.get("id")
        if not item_id or item_id in ids:
            errors.append(f"duplicate/missing item id: {item_id}")
        ids.add(item_id)
        items.append(item)
        if item.get("review_status") not in ("draft", "approved"):
            errors.append(f"{item_id}: invalid review status")
        if not item.get("refs"):
            errors.append(f"{item_id}: missing source reference")
        if not any(item.get(k) for k in ("text", "display", "prayer")):
            errors.append(f"{item_id}: missing child-facing content")
        for ref in item.get("refs", []):
            quran = QURAN.fullmatch(ref)
            if quran:
                surah, first, last = map(int, (quran[1], quran[2], quran[3] or quran[2]))
                if not (1 <= surah <= 114 and 1 <= first <= last <= verse_counts.get(surah, 0)):
                    errors.append(f"{item_id}: invalid Quran range {ref}")
            elif HADITH.fullmatch(ref):
                if not item.get("grading") or not item.get("evidence_url"):
                    errors.append(f"{item_id}: hadith needs grading and evidence URL")
            elif FIQH.fullmatch(ref):
                pass
            else:
                errors.append(f"{item_id}: invalid reference {ref}")
        if item.get("quote_ref") and item["quote_ref"] not in item.get("refs", []):
            errors.append(f"{item_id}: quote_ref not in refs")
        for key in ("evidence_url",):
            if item.get(key):
                url = urlparse(item[key])
                if url.scheme != "https" or url.hostname not in domains:
                    errors.append(f"{item_id}: unapproved evidence URL")

    for story in content["stories"]:
        if story.get("review_status") not in ("draft", "approved") or not story.get("scenes"):
            errors.append(f"{story.get('id')}: incomplete story")
        for scene in story["scenes"]:
            check_item(scene)
    for group in ("adhkar", "daily_duas"):
        for item in content[group]:
            check_item(item)
    prayer = content["prayer_learning"]
    for group in ("preparation", "wudu", "prayer_steps", "prayer_counts"):
        for item in prayer[group]:
            check_item(item)
    for key, url in prayer["evidence_urls"].items():
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in domains:
            errors.append(f"prayer_learning: unapproved URL {key}")
    if prayer["madhhab_applicability"] not in ("shared_basics_only", "approved_policy_recorded"):
        errors.append("unexpected madhhab policy; review validator before changing")
    if content["language"] != sources["policy"]["language"] or content["locale"] != sources["policy"]["market"]:
        errors.append("language/market mismatch")
    if content["age_bands"] != sources["policy"]["age_bands"]:
        errors.append("age bands mismatch")
    if {story["id"] for story in content["stories"]} != {"story-adam", "story-musa", "story-isa", "story-muhammad"}:
        errors.append("story scope changed")
    required_occasions = {"morning", "evening", "after_obligatory_prayer"}
    actual_occasions = {occasion for item in content["adhkar"] for occasion in item["occasions"]}
    if not required_occasions <= actual_occasions:
        errors.append("missing morning, evening, or after-prayer adhkar")
    if not content["daily_duas"] or any(not prayer[group] for group in ("preparation", "wudu", "prayer_steps", "prayer_counts")):
        errors.append("missing daily duas or prayer-learning section")

    evaluation = load(folder, "evaluation.json")
    approvals = load(folder, "approvals.json")
    for case in evaluation["cases"]:
        for item_id in case.get("expected_item_ids", []):
            if item_id not in ids:
                errors.append(f"evaluation {case['id']}: missing {item_id}")
        if case["expected_action"] not in ("answer_from_corpus", "abstain_or_redirect"):
            errors.append(f"evaluation {case['id']}: invalid action")
        if case["expected_action"] == "abstain_or_redirect" and case.get("expected_item_ids"):
            errors.append(f"evaluation {case['id']}: abstention must not cite an item")

    if release:
        if content.get("status") != "approved" or not content.get("publication_allowed"):
            errors.append("release blocked: package remains draft")
        if content.get("rights_status") != "cleared" or any(s["rights_status"] != "cleared" for s in sources["sources"]):
            errors.append("release blocked: source rights not cleared")
        review = content.get("review", {})
        if not all(review.get(field) for field in ("religious_reviewer", "child_language_reviewer", "approved_at")):
            errors.append("release blocked: named human reviews and approval date missing")
        if any(item.get("review_status") != "approved" for item in items + content["stories"]):
            errors.append("release blocked: item review incomplete")
        content_hash = hashlib.sha256((folder / "content.json").read_bytes()).hexdigest()
        for role in ("religious", "child_language"):
            if not any(
                row.get("role") == role and row.get("decision") == "approved"
                and row.get("scope") == "all_content_items"
                and row.get("content_sha256") == content_hash
                and row.get("reviewer") and row.get("credentials_ref")
                and row.get("conflicts_declared") is True and row.get("approved_at")
                for row in approvals["package_reviews"]
            ):
                errors.append(f"release blocked: {role} package review for current content hash missing")
        for source in sources["sources"]:
            if not any(
                row.get("source_id") == source["id"] and row.get("decision") == "cleared"
                and row.get("reviewer") and row.get("evidence_ref") and row.get("approved_at")
                for row in approvals["source_rights"]
            ):
                errors.append(f"release blocked: {source['id']} lacks rights record")
        if quran_source:
            try:
                registry = registry_module.load(registry_path)
                for sid in (quran_source["registry_source_id"], quran_source["registry_license_source_id"]):
                    if registry.get(sid)["status"] != "cleared":
                        errors.append(f"release blocked: registry source {sid} is {registry.get(sid)['status']}, "
                                      "not cleared")
            except (OSError, registry_module.RegistryError, KeyError) as exc:
                errors.append(f"release blocked: registry unreadable ({exc})")
        if not approvals["prayer_policy"]:
            errors.append("release blocked: prayer policy not approved")
        if not approvals["recheck_due_at"]:
            errors.append("release blocked: re-review date not set")

    summary = (f"OK: {len(content['stories'])} stories, {len(items)} referenced content items, "
               f"{len(evaluation['cases'])} evaluation cases; release={'checked' if release else 'not requested'}")
    return errors, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", action="store_true", help="also enforce publication gates")
    parser.add_argument("--package-dir", type=Path, default=HERE, help=argparse.SUPPRESS)
    parser.add_argument("--registry", type=Path, default=REGISTRY, help="the source registry (default: the repository's)")
    parser.add_argument("--raw-root", type=Path, default=RAW, help="where scripts/fetch_sources.py puts raw files")
    args = parser.parse_args(argv)
    errors, summary = validate(args.package_dir, args.release, args.registry, args.raw_root)
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
