"""Apply signed human decisions from doc/decisions/decisions.yaml (the only path to approved/cleared).

    python scripts/apply_decisions.py [--check]

Each decision needs decision_id, item_ids, decision (approve|reject|revise|defer), decided_by, role, date
and note. decided_by must be a qualified reviewer in corpus/governance/reviewers.yaml, or Mousa al-Rashdan /
Momen Alhamza for the administrative decisions they own. Any invalid decision refuses the whole file.
Every applied decision is written to corpus/governance/audit.jsonl; state is kept in
corpus/governance/decision_state.json. --check validates without applying. Exit 1 on refusal.
"""
import sys

import _common  # noqa: F401
from _common import CONTENT_AUDIT, DRAFTS, REGISTRY, REVIEWERS, ROOT
from companion_api.governance import decisions


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    paths = decisions.Paths(decisions=ROOT / "doc/decisions/decisions.yaml",
                            state=ROOT / "corpus/governance/decision_state.json", audit=CONTENT_AUDIT,
                            reviewers=REVIEWERS, registry=REGISTRY, drafts=DRAFTS,
                            known_items=decisions.known_items(ROOT))
    if "--check" in args:
        import yaml
        data = yaml.safe_load(paths.decisions.read_text(encoding="utf-8")) or {}
        reviewers = decisions.review.load_reviewers(REVIEWERS)
        bad = {e.get("decision_id"): decisions.validate(e, paths, reviewers) for e in data.get("decisions") or []}
        bad = {k: v for k, v in bad.items() if v}
        print(bad or "all decisions valid")
        return 1 if bad else 0
    try:
        result = decisions.apply(paths)
    except (decisions.DecisionError, decisions.review.ReviewError) as error:
        print(error, file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
