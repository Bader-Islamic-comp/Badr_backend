"""Build ai_prereview batches for the independent reviewer (agent B), and summarize its verdicts.

    python scripts/prereview_batches.py build      write corpus/reviews/ai_prereview/batches/batch-NN.json
    python scripts/prereview_batches.py summary    count verdicts, check the output schema and scope

Batch items carry only neutral facts (ids, references, questions, file pointers), never agent A's
judgments (needs_check, verification, confidence, check reasons), so B reviews from the sources.
"""
from collections import Counter
import json
import subprocess
import sys

import yaml

import _common  # noqa: F401
from _common import ROOT

OUT = ROOT / "corpus/reviews/ai_prereview"
BATCH = 50
VERDICTS = ("pass", "flag", "fail")
FIELDS = {"item_id", "item_type", "verdict", "reasons", "evidence_refs", "suggested_fix", "confidence"}


def _items() -> list[dict]:
    items = []
    selection = yaml.safe_load((ROOT / "corpus/candidate/hadith_selection.yaml").read_text(encoding="utf-8"))
    for position, entry in enumerate(selection["hadith"], 1):
        ref = entry["cluster_primary"]
        collection, number = ref.split(":")
        items.append({"item_id": f"selection-{position:02d}", "item_type": "hadith", "ref": ref,
                      "also_listed_as": f"nawawi40:{entry['number']}" if entry["collection"] == "nawawi40" else None,
                      "topic": entry["topic"],
                      "displayed_text_file": f"corpus/wave1/documents/hadith-{collection}-{number.replace('.', '-')}.json",
                      "canonical_file": f"corpus/canonical/hadith/{collection}.jsonl"})
    for path in sorted((ROOT / "corpus/candidate/prophets").glob("*_source_map.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for position, item in enumerate(data["ranges"], 1):
            items.append({"item_id": f"map-{data['prophet_id']}-{position:02d}", "item_type": "source_map_range",
                          "prophet": data["prophet_id"], "ref": item["ref"], "stated_topic": item["topic"],
                          "canonical_file": "corpus/canonical/quran/ayat.jsonl"})
    for line in (ROOT / "corpus/eval/gold.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        items.append({"item_id": row["id"], "item_type": "gold_question", "question": row["question"],
                      "variant": row["variant"], "expected_chunk_ids": row["expected_chunk_ids"],
                      "documents_dir": "corpus/wave1/documents"})
    for line in (ROOT / "corpus/eval/harmful.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        items.append({"item_id": row["id"], "item_type": "harmful_question", "question": row["question"],
                      "variant": row["variant"], "category": row["category"],
                      "expected_route": row["expected_route"]})
    for path in sorted((ROOT / "doc/governance").glob("*.md")):
        items.append({"item_id": f"policy-{path.stem}", "item_type": "policy",
                      "file": str(path.relative_to(ROOT)), "compare_with": ["doc/architecture.md", "AGENTS.md"]})
    return items


def build() -> int:
    items = _items()
    batches = OUT / "batches"
    batches.mkdir(parents=True, exist_ok=True)
    for old in batches.glob("batch-*.json"):
        old.unlink()
    # Group by type so a batch needs one kind of reading; keep batches at most BATCH items.
    number = 0
    for kind in ("hadith", "source_map_range", "policy", "harmful_question", "gold_question"):
        group = [item for item in items if item["item_type"] == kind]
        for start in range(0, len(group), BATCH):
            number += 1
            (batches / f"batch-{number:02d}.json").write_text(json.dumps(
                {"batch": number, "output": f"corpus/reviews/ai_prereview/batch-{number:02d}.jsonl",
                 "items": group[start:start + BATCH]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(items), "batches": number, "by_type": Counter(i["item_type"] for i in items)}))
    return 0


def summary() -> int:
    expected = {item["item_id"]: item["item_type"] for item in _items()}
    seen, problems, counts = {}, [], Counter()
    for path in sorted(OUT.glob("batch-*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                problems.append(f"{path.name}:{number} is not JSON")
                continue
            if set(row) != FIELDS or row.get("verdict") not in VERDICTS:
                problems.append(f"{path.name}:{number} does not follow the schema")
                continue
            seen[row["item_id"]] = row
            counts[(row["item_type"], row["verdict"])] += 1
    missing = sorted(set(expected) - set(seen))
    changed = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    out_of_scope = [line[3:] for line in changed.splitlines()
                    if line[3:].startswith("corpus/") and not line[3:].startswith("corpus/reviews/")
                    and "batch" in line]
    table = {}
    for (kind, verdict), count in counts.items():
        table.setdefault(kind, {v: 0 for v in VERDICTS})[verdict] = count
    print(json.dumps({"reviewed": len(seen), "expected": len(expected), "missing": len(missing),
                      "by_type": table, "schema_problems": problems[:10], "out_of_scope_writes": out_of_scope},
                     ensure_ascii=False, indent=1))
    return 1 if problems or out_of_scope else 0


if __name__ == "__main__":
    sys.exit({"build": build, "summary": summary}[sys.argv[1]]())
