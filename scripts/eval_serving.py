"""Measure the serving path itself on the corpus-tasks evaluation sets (test/corpus-tasks).

    python scripts/eval_serving.py RELEASE_DIR [--language ar] [--json]

`scripts/eval_retrieval.py` compares embedders with its own evaluation retriever; this script asks the server's
own code: `AnswerService.prepare` (routing, language, Arabizi rewriting, faith detection) and `HybridRetriever`
(with drafts included, as in the corpus preview), with no model call. It reports, per question variant of
corpus/eval/gold.jsonl, how many questions reach the corpus and how many find an expected passage in the four
the prompt would get; and, per category of corpus/eval/harmful.jsonl, where each question is routed. Question
text is never printed.
"""
from collections import Counter, defaultdict
import json
import sys

import _common  # noqa: F401
from _common import ROOT
from companion_api.config import Settings
from companion_api.rag.evaluate import predict
from companion_api.rag.service import assemble

EVAL = ROOT / "corpus/eval"


class _NoModel:
    model = "qwen3.5:9b"

    def complete(self, *args, **kwargs):
        raise AssertionError("the serving evaluation never calls a model")


def _cases(name: str) -> list[dict]:
    return [json.loads(line) for line in (EVAL / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def run(release: str, language: str = "ar") -> dict:
    settings = Settings(demo_mode=True, demo_token="x" * 24, rag_enabled=True, rag_release=release,
                        embedding_model="hashing", rag_language=language, rag_preview_drafts=True)
    service = assemble(settings, release, include_drafts=True)
    service.generator = _NoModel()
    gold = defaultdict(Counter)
    for case in _cases("gold.jsonl"):
        row = gold[case["variant"]]
        plan = service.prepare(case["question"])
        row["questions"] += 1
        row[f"route:{plan.route}"] += 1
        if plan.faith:
            row["faith"] += 1
        expected = set(case["expected_chunk_ids"])
        found = [candidate.chunk.id for candidate in (plan.retrieval.candidates if plan.retrieval else ())]
        if found:
            row["reached_corpus"] += 1
        if expected & set(found):
            row["expected_in_top4"] += 1
    harmful = defaultdict(Counter)
    for case in _cases("harmful.jsonl"):
        plan = service.prepare(case["question"])
        predicted, _ = predict(plan)
        outcome = plan.result.answer_type if plan.step == "done" and plan.result else predicted
        harmful[f"{case['category']} (expect {case['expected_route']})"][outcome] += 1
    return {"release": release, "language": language,
            "gold": {variant: dict(row) for variant, row in sorted(gold.items())},
            "harmful": {category: dict(row) for category, row in sorted(harmful.items())}}


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    language = args[args.index("--language") + 1] if "--language" in args else "ar"
    result = run(args[0], language)
    if "--json" in args:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print(f"gold ({result['release']}, language {language})")
    print(f"  {'variant':24} {'questions':>9} {'reached':>8} {'top-4 hit':>9} {'faith':>6}")
    total = Counter()
    for variant, row in result["gold"].items():
        total.update(row)
        print(f"  {variant:24} {row['questions']:9} {row.get('reached_corpus', 0):8} "
              f"{row.get('expected_in_top4', 0):9} {row.get('faith', 0):6}")
    print(f"  {'all':24} {total['questions']:9} {total['reached_corpus']:8} {total['expected_in_top4']:9} "
          f"{total['faith']:6}")
    print("harmful")
    for category, row in result["harmful"].items():
        print(f"  {category:46} " + ", ".join(f"{k}={v}" for k, v in sorted(row.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
