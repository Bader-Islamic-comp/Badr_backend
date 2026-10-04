"""Age-band drafts (corpus tasks Phase 3): empty templates and the reading-level checker.

    python scripts/age_band.py templates   create a template per source-map range and selected hadith
                                           (never overwrites an existing draft)
    python scripts/age_band.py check       validate every draft against schema.json and write
                                           reading_level_checks; exit 1 when any draft fails

Children's text is written and reviewed by people (doc/corpus-tasks.md, task 10). These tools never
write text and never change a review status.
"""
import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from companion_api.corpusprep import age_band  # noqa: E402

HEADER = ("# Age-band draft (tier 2). Human-written, human-reviewed: see WRITING_GUIDE.md in this folder.\n"
          "# Write only in `text` and `lesson` of each version; never type Quran or hadith text, use\n"
          "# [[quote:<ref>]] markers. `reading_level_checks` is written by scripts/age_band.py check.\n")


def _path(drafts: Path, item: dict) -> Path:
    if item["kind"] == "story_scene":
        return drafts / "prophets" / item["prophet_id"] / f"{item['id']}.yaml"
    return drafts / "hadith" / f"{item['id']}.yaml"


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
                    encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("templates", "check"))
    parser.add_argument("--corpus-root", type=Path, default=ROOT / "corpus")
    args = parser.parse_args(argv)
    base = args.corpus_root
    drafts = base / "drafts/age_band"

    if args.command == "templates":
        maps = [yaml.safe_load(p.read_text(encoding="utf-8"))
                for p in sorted((base / "candidate/prophets").glob("*_source_map.yaml"))]
        selection = yaml.safe_load((base / "candidate/hadith_selection.yaml").read_text(encoding="utf-8"))
        created = kept = 0
        for item in age_band.templates(maps, selection):
            path = _path(drafts, item)
            if path.exists():
                kept += 1
                continue
            _dump(path, item)
            created += 1
        print(f"templates: {created} created, {kept} already existed (not touched)")
        return 0

    schema = age_band.load_schema()
    aliases = yaml.safe_load((base / "aliases.yaml").read_text(encoding="utf-8"))
    names = {p["id"]: p["names_ar"][0]["alias"] for p in aliases["prophets"]}
    canonical = base / "canonical"
    print("indexing canonical Quran and hadith text for the verbatim check", file=sys.stderr)
    quran_texts = [json.loads(line)["text_simple"] for line in (canonical / "quran/ayat.jsonl").open(encoding="utf-8")]
    hadith_texts = [json.loads(line)["arabic_text"] for name in ("bukhari", "muslim", "nawawi40")
                    for line in (canonical / f"hadith/{name}.jsonl").open(encoding="utf-8")]
    index = age_band.SacredIndex(quran_texts, hadith_texts)
    totals = {"drafts": 0, "empty_versions": 0, "passed_versions": 0, "failed_drafts": 0}
    for path in sorted(drafts.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        problems = age_band.check_file(data, index, names, schema)
        totals["drafts"] += 1
        if problems:
            totals["failed_drafts"] += 1
            for problem in problems:
                print(f"FAIL {path.relative_to(base)}: {problem}")
        else:
            _dump(path, data)
        for band in age_band.BANDS:
            status = (data["versions"][band].get("reading_level_checks") or {}).get("status")
            totals["empty_versions"] += status == "empty"
            totals["passed_versions"] += status == "pass"
    print(json.dumps(totals))
    return 1 if totals["failed_drafts"] else 0


if __name__ == "__main__":
    sys.exit(main())
