"""List chunks of a release that are due for re-review, with the reason (governance task 8).

    python scripts/due_for_review.py [RELEASE_DIR or releases/current_release] [--cadence-days 365]
        [--embedding-model M] [--json] [--fail-if-due]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import _common  # noqa: F401
from _common import REGISTRY, RELEASES, policy_version
from companion_api.governance import due
from companion_api.rag.embeddings import DEFAULT_EMBEDDING_MODEL
from companion_api.rag.release import ReleaseError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("release", nargs="?", type=Path, default=RELEASES / "current_release")
    parser.add_argument("--cadence-days", type=int, default=due.DEFAULT_CADENCE_DAYS)
    parser.add_argument("--embedding-model", default=os.environ.get("COMPANION_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-if-due", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = due.due(args.release, REGISTRY, embedding_model=args.embedding_model,
                         policy_version=policy_version(), cadence_days=args.cadence_days)
    except (ReleaseError, FileNotFoundError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"release {result['release_id']}: {result['due']} of {result['chunks']} chunks due; "
              f"reasons {result['reason_counts']}")
        for item in result["items"][:20]:
            print(f"  {item['chunk_id']}: {', '.join(item['reasons'])}")
    return 3 if args.fail_if_due and result["due"] else 0


if __name__ == "__main__":
    sys.exit(main())
