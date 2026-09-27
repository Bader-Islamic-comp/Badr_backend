"""Review workflow CLI for age-band drafts (governance task 6).

    python scripts/review.py list [--status in_review]
    python scripts/review.py submit     ITEM --actor AUTHOR
    python scripts/review.py approve    ITEM --actor REVIEWER
    python scripts/review.py reject     ITEM --actor REVIEWER --reason TEXT
    python scripts/review.py revise     ITEM --actor AUTHOR
    python scripts/review.py quarantine ITEM --actor NAME --reason TEXT

approve and reject are refused here: they come only from doc/decisions/decisions.yaml through
scripts/apply_decisions.py. ITEM is `<draft id>@<band>`, e.g. story-yusuf-s01@7-9. Approval needs a qualified reviewer from
corpus/governance/reviewers.yaml who is not the author and has no declared conflict. Every change
is written to corpus/governance/audit.jsonl first.
"""
import argparse
from collections import Counter
import sys
from pathlib import Path

import _common  # noqa: F401
from _common import CONTENT_AUDIT, DRAFTS, REVIEWERS
from companion_api.governance import review
from companion_api.governance.audit import AuditError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("list",) + tuple(review.TRANSITIONS))
    parser.add_argument("item", nargs="?")
    parser.add_argument("--actor")
    parser.add_argument("--reason", default="")
    parser.add_argument("--status")
    parser.add_argument("--drafts", type=Path, default=DRAFTS)
    parser.add_argument("--audit", type=Path, default=CONTENT_AUDIT)
    parser.add_argument("--reviewers", type=Path, default=REVIEWERS)
    args = parser.parse_args(argv)
    if args.action == "list":
        found = review.items(args.drafts)
        for item in found:
            if not args.status or item.status == args.status:
                if args.status:
                    print(f"{item.item_id}\t{item.status}\tauthor={item.author}\tchecks={item.checks}")
        print(dict(Counter(item.status for item in found)))
        return 0
    if not args.item or not args.actor:
        parser.error(f"{args.action} needs ITEM and --actor")
    try:
        item = review.transition(args.drafts, args.item, args.action, args.actor, audit_path=args.audit,
                                 reviewers_path=args.reviewers, reason=args.reason)
    except (review.ReviewError, AuditError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(f"{item.item_id} -> {item.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
