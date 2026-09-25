"""Evaluation harness: `python -m companion_api.rag.evaluate` (doc/rag-system.md section 8).

    --release DIR --cases eval.json [--generate] [--include-drafts] [--json]

Offline (the default) needs no model: it reports routing accuracy and
retrieval recall@4 using the embedder the server would use. A case expecting
`grounded` or `reviewed_answer` passes offline when the question routes to
retrieval, the evidence is not weak and an expected document is in the top 4;
any other case passes when the deterministic outcome (fixed reply, weak-evidence
abstention, reviewed answer) is one it expects. `--generate` also runs every
case through the full answer service against the configured model and reports
the answer-type match, grounding pass and abstention rates.

Embedder and model settings come from the server's environment variables (section 9),
so an evaluation measures what the server would do. Exit status is 0 when every
case passes, 1 when any fails and 2 when the cases or the release are refused.

These are development cases on synthetic text. They are not the reviewed
religious and child-safety evaluation set, which needs the scholarly board.
`--json` output carries case ids and outcomes, never question text.
"""
import argparse
import json
from pathlib import Path
import sys

from ..config import Settings
from .service import AnswerService, assemble

ANSWER_TYPES = frozenset({"unavailable", "grounded", "reviewed_answer", "abstained", "redirected", "safety"})
GENERATIVE = frozenset({"grounded", "reviewed_answer"})


class CasesError(ValueError):
    pass


def load_cases(path: Path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exception:
        raise CasesError(f"cannot read {path}: {exception}") from None
    if not isinstance(data, dict) or data.get("schemaVersion") != 1 or not isinstance(data.get("cases"), list):
        raise CasesError('expected {"schemaVersion": 1, "cases": [...]}')
    seen = set()
    for number, case in enumerate(data["cases"], start=1):
        where = f"case {number}"
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise CasesError(f"{where}: needs a string id")
        if case["id"] in seen:
            raise CasesError(f"{where}: duplicate id {case['id']!r}")
        seen.add(case["id"])
        expect = case.get("expect")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise CasesError(f"{case['id']}: needs a question")
        if (not isinstance(expect, dict) or not isinstance(expect.get("answerTypes"), list) or not expect["answerTypes"]
                or not set(expect["answerTypes"]) <= ANSWER_TYPES):
            raise CasesError(f"{case['id']}: expect.answerTypes must list some of {', '.join(sorted(ANSWER_TYPES))}")
        documents = expect.get("documents", [])
        if not isinstance(documents, list) or not all(isinstance(value, str) for value in documents):
            raise CasesError(f"{case['id']}: expect.documents must be a list of document ids")
    if not seen:
        raise CasesError("no cases")
    return data["cases"]


def _documents(retrieval) -> list[str]:
    return list(dict.fromkeys(candidate.chunk.document_id for candidate in retrieval.candidates)) if retrieval else []


def evaluate_case(service: AnswerService, case: dict, *, generate: bool = False) -> dict:
    question, expect = case["question"], case["expect"]
    expected, documents = set(expect["answerTypes"]), expect.get("documents", [])
    early, retrieval = service.prepare(question)
    # Offline, a question that reaches the model is predicted `grounded`; only
    # generation can tell whether the model abstains instead.
    predicted = early.answer_type if early is not None else "grounded"
    top = _documents(retrieval)
    if expected & GENERATIVE:
        routed = predicted in GENERATIVE and (not documents or any(doc in top for doc in documents))
    else:
        routed = predicted in expected
    row = {"id": case["id"], "routingPass": routed, "predicted": predicted, "topDocuments": top}
    if documents:
        # Recall is a retrieval measure, so it is taken whatever the router did.
        found = _documents(service.retriever.retrieve(question, language=service.language, age_band=service.age_band))
        row["recallHit"] = any(doc in found for doc in documents)
    if generate:
        result = service.answer(question)
        row.update(answerType=result.answer_type, reason=result.reason, typeMatch=result.answer_type in expected,
                   citations=list(result.citations))
    row["passed"] = row["typeMatch"] if generate else routed
    return row


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def summarize(rows: list[dict], *, generate: bool) -> dict:
    recall = [row["recallHit"] for row in rows if "recallHit" in row]
    summary = {"cases": len(rows), "passed": sum(row["passed"] for row in rows),
               "routingAccuracy": _rate(sum(row["routingPass"] for row in rows), len(rows)),
               "recallAt4": _rate(sum(recall), len(recall)), "recallCases": len(recall)}
    if generate:
        generated = [row for row in rows if row["reason"] == "grounded" or row["reason"].startswith("grounding:")]
        summary.update(
            answerTypeMatchRate=_rate(sum(row["typeMatch"] for row in rows), len(rows)),
            groundingPassRate=_rate(sum(row["reason"] == "grounded" for row in generated), len(generated)),
            generatedCases=len(generated),
            abstentionRate=_rate(sum(row["answerType"] == "abstained" for row in rows), len(rows)))
    return summary


def _percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * 100:.1f}%"


def report(service: AnswerService, cases: list[dict], *, generate: bool = False, as_json: bool = False) -> int:
    rows = [evaluate_case(service, case, generate=generate) for case in cases]
    summary = summarize(rows, generate=generate)
    if as_json:
        print(json.dumps({"provenance": service.provenance, "mode": "generate" if generate else "offline",
                          "includeDrafts": service.retriever.include_drafts, "summary": summary, "cases": rows},
                         indent=2, ensure_ascii=False))
    else:
        provenance = service.provenance
        print(f"Release {provenance['releaseId']} ({provenance['embedder']}), "
              f"{'generate with ' + provenance['model'] if generate else 'offline'}"
              f"{', drafts included' if service.retriever.include_drafts else ''}")
        questions = {case["id"]: case["question"] for case in cases}
        for row in rows:
            outcome = f"{row['answerType']} ({row['reason']})" if generate else row["predicted"]
            print(f"{'PASS' if row['passed'] else 'FAIL'}  {row['id']:<22} {outcome:<34} "
                  f"top: {', '.join(row['topDocuments']) or '-'}  | {questions[row['id']]}")
        print(f"Routing accuracy {_percent(summary['routingAccuracy'])} of {summary['cases']} cases; "
              f"recall@4 {_percent(summary['recallAt4'])} of {summary['recallCases']}")
        if generate:
            print(f"Answer-type match {_percent(summary['answerTypeMatchRate'])}; grounding pass "
                  f"{_percent(summary['groundingPassRate'])} of {summary['generatedCases']} generated; "
                  f"abstention {_percent(summary['abstentionRate'])}")
    return 0 if summary["passed"] == summary["cases"] else 1


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="python -m companion_api.rag.evaluate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", required=True, help="release directory to evaluate")
    parser.add_argument("--cases", required=True, help="eval.json (doc/rag-system.md section 8)")
    parser.add_argument("--generate", action="store_true", help="also call the configured model")
    parser.add_argument("--include-drafts", action="store_true", help="retrieve draft chunks too (operators only)")
    parser.add_argument("--json", action="store_true", help="machine-readable output without question text")
    args = parser.parse_args(argv)
    try:
        cases = load_cases(Path(args.cases))
        service = assemble(Settings.from_environment(), args.release, include_drafts=args.include_drafts)
    except (CasesError, RuntimeError) as exception:
        print(f"Evaluation refused: {exception}", file=sys.stderr)
        return 2
    return report(service, cases, generate=args.generate, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
