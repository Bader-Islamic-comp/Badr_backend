"""Replay the post-generation checks over answers recorded from a real model run, without any model.

    python scripts/replay_checks.py RECORDED.jsonl [RELEASE_DIR] [--json]

RECORDED.jsonl is a generation run over the gold set (one JSON object per question with at least `id`,
`question`, `answerType`, `text` and `citations`, the chunk ids the released answer cited), such as the
2026-10-01 Qwen3.5-9B run over release wave1-preview-3. Such files hold model answers and are never committed.
For every answer that was released (`answerType` grounded) this rebuilds the answer as the checks read it, with
the cited passages from RELEASE_DIR (default releases/wave1-preview-3), and runs every deterministic check of
`checks.Verifier` in the service's order; the model judge is reported `unavailable` (no model is called). For
every other recorded answer it reports where the current code would now send the question
(`AnswerService.prepare`), which shows the Arabizi routing change. Prints ids and check codes, never text.
"""
from collections import Counter
import json
from pathlib import Path
import sys

import _common  # noqa: F401
from _common import ROOT
from companion_api.config import Settings
from companion_api.rag import checks, router
from companion_api.rag.grounding import Segment, split_sentences
from companion_api.rag.service import assemble

DEFAULT_RELEASE = ROOT / "releases/wave1-preview-3"


class _NoModel:
    model = "qwen3.5:9b"

    def complete(self, *args, **kwargs):
        raise AssertionError("the replay never calls a model")


def replay(recorded: Path, release: Path) -> dict:
    settings = Settings(demo_mode=True, demo_token="x" * 24, rag_enabled=True, rag_release=str(release),
                        embedding_model="hashing", rag_language="ar", rag_preview_drafts=True)
    service = assemble(settings, release, include_drafts=True)
    service.generator = _NoModel()
    chunks = {chunk.id: chunk for chunk in service.retriever.release.chunks}
    rows = [json.loads(line) for line in recorded.read_text(encoding="utf-8").splitlines() if line.strip()]
    released, routed = [], Counter()
    for row in rows:
        if row["answerType"] != "grounded":
            plan = service.prepare(row["question"])
            outcome = plan.result.reason if plan.result is not None else plan.step
            routed[f"{row['answerType']}:{row['reason'].split(':')[0]} -> {plan.route}:{outcome.split(':')[0]}"] += 1
            continue
        cited = tuple(chunks[chunk_id] for chunk_id in row["citations"])
        segments = tuple(Segment(sentence, tuple(row["citations"])) for sentence in split_sentences(row["text"]))
        answer = checks.Answer(row["question"], row["text"], segments, cited, router.is_faith_topic(row["question"]))
        results, failure = service.verifier.run(answer, None)
        released.append({"id": row["id"], "checks": checks.summary(results), "verdict": failure or "released"})
    return {"recorded": str(recorded.name), "release": str(release.name), "released": released,
            "other_answers_now": dict(sorted(routed.items()))}


def main(argv=None) -> int:
    args = [arg for arg in (argv if argv is not None else sys.argv[1:]) if arg != "--json"]
    if not args:
        print(__doc__)
        return 2
    result = replay(Path(args[0]), Path(args[1]) if len(args) > 1 else DEFAULT_RELEASE)
    if "--json" in (argv if argv is not None else sys.argv[1:]):
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    names = list(dict.fromkeys(name for row in result["released"] for name in row["checks"]))
    print(f"{result['recorded']} over {result['release']}: {len(result['released'])} released answers "
          "(n/a: not applicable; -: not run, an earlier check failed)")
    print(f"  {'answer':28} " + " ".join(f"{name:12}" for name in names) + "  verdict")
    for row in result["released"]:
        cells = []
        for name in names:
            code = row["checks"].get(name, "-")
            cells.append("n/a" if code.endswith(checks.NOT_APPLICABLE) else code.split(":")[0])
        print(f"  {row['id']:28} " + " ".join(f"{cell:12}" for cell in cells) + f"  {row['verdict']}")
    print("other recorded answers, recorded -> now:")
    for transition, count in result["other_answers_now"].items():
        print(f"  {transition:60} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
