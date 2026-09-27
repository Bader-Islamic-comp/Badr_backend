"""Build corpus/eval/gold.jsonl and harmful.jsonl from their source YAML (tasks 12 and 13).

    python scripts/build_eval.py

Gold references are resolved to parent chunk ids of corpus/wave1 (built by scripts/build_corpus.py);
a reference the corpus does not hold fails the build. Every item is synthetic and pending approval.
"""
from collections import Counter
import json
from pathlib import Path
import sys

import yaml

import _common  # noqa: F401
from _common import ROOT
from companion_api.corpusprep.candidates import parse_quran_ref
from companion_api.rag.chunking import chunk_documents
from companion_api.rag.corpus import load_corpus

EVAL = ROOT / "corpus/eval"
VARIANTS = ("msa", "gulf", "levantine", "egyptian", "misspelled", "arabizi", "english_transliteration")
ROUTES = ("abstain", "redirect", "safety", "refuse")


def main() -> int:
    corpus, report = load_corpus(ROOT / "corpus/wave1")
    if not report.ok:
        print("corpus/wave1 does not validate; run scripts/build_corpus.py", file=sys.stderr)
        return 1
    parents = [chunk for chunk in chunk_documents(corpus.documents) if not chunk.is_child]
    by_ayah, by_ref = {}, {}
    for chunk in parents:
        for ref in chunk.source_refs:
            if ref.startswith("quran:"):
                surah, first, last = parse_quran_ref(ref)
                for ayah in range(first, last + 1):
                    by_ayah.setdefault((surah, ayah), []).append(chunk.id)
            else:
                by_ref.setdefault(ref, []).append(chunk.id)
    selection = yaml.safe_load((ROOT / "corpus/candidate/hadith_selection.yaml").read_text(encoding="utf-8"))["hadith"]
    source = yaml.safe_load((EVAL / "gold_source.yaml").read_text(encoding="utf-8"))
    problems, gold = [], []
    for intent in source["intents"]:
        expected = []
        for ref in intent["refs"]:
            if ref.startswith("selection:"):
                entry = selection[int(ref.split(":")[1]) - 1]
                ids = by_ref.get(entry["cluster_primary"], []) if not entry["needs_check"] else []
            else:
                surah, first, last = parse_quran_ref(ref)
                ids = [cid for ayah in range(first, last + 1) for cid in by_ayah.get((surah, ayah), [])]
            if not ids:
                problems.append(f"{intent['id']}: {ref} is not in corpus/wave1")
            expected += ids
        expected = list(dict.fromkeys(expected))
        for variant, question in intent["q"].items():
            if variant not in VARIANTS:
                problems.append(f"{intent['id']}: unknown variant {variant}")
            gold.append({"id": f"{intent['id']}-{variant}", "intent": intent["id"], "question": question,
                         "variant": variant, "expected_chunk_ids": expected, "expected_refs": intent["refs"],
                         "expected_answer_notes": intent["notes"], "approval_status": "pending", "synthetic": True})
    harmful = []
    for block in yaml.safe_load((EVAL / "harmful_source.yaml").read_text(encoding="utf-8"))["categories"]:
        if block["expected_route"] not in ROUTES:
            problems.append(f"{block['category']}: unknown route {block['expected_route']}")
        for number, item in enumerate(block["items"], 1):
            if item["v"] not in VARIANTS:
                problems.append(f"{block['category']} #{number}: unknown variant {item['v']}")
            harmful.append({"id": f"{block['category']}-{number:02d}", "question": item["q"], "variant": item["v"],
                            "category": block["category"], "expected_route": block["expected_route"],
                            "notes": block["notes"], "approval_status": "pending", "synthetic": True})
    if len({item["question"] for item in gold + harmful}) != len(gold) + len(harmful):
        problems.append("a question appears twice")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    for name, rows in (("gold.jsonl", gold), ("harmful.jsonl", harmful)):
        (EVAL / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                                 encoding="utf-8", newline="\n")
    print(json.dumps({"gold": len(gold), "gold_variants": Counter(r["variant"] for r in gold),
                      "harmful": len(harmful), "harmful_routes": Counter(r["expected_route"] for r in harmful),
                      "harmful_categories": Counter(r["category"] for r in harmful)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
