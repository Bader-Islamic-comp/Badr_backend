"""Point current_release back at the previous verified release (governance task 5).

    python scripts/rollback.py --actor NAME --reason TEXT [--quarantine]
    python scripts/rollback.py --promote RELEASE_ID --actor NAME --reason TEXT
    python scripts/rollback.py --status

--quarantine also marks the current release so it can never be served again.
"""
import argparse
import json
import sys
from pathlib import Path

import _common  # noqa: F401
from _common import RELEASES
from companion_api.governance import releases
from companion_api.rag.release import ReleaseError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--releases", type=Path, default=RELEASES)
    parser.add_argument("--actor")
    parser.add_argument("--reason", default="")
    parser.add_argument("--quarantine", action="store_true")
    parser.add_argument("--promote", metavar="RELEASE_ID")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    root = args.releases
    if args.status:
        history = json.loads((root / releases.HISTORY).read_text()) if (root / releases.HISTORY).is_file() else []
        print(json.dumps({"current": releases.current(root), "history": history}, indent=2))
        return 0
    if not args.actor:
        parser.error("--actor is required")
    try:
        if args.promote:
            releases.promote(root, args.promote, actor=args.actor, reason=args.reason)
            print(f"current_release -> {args.promote}")
        else:
            target = releases.rollback(root, actor=args.actor, reason=args.reason, quarantine=args.quarantine)
            print(f"current_release -> {target}")
    except ReleaseError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
