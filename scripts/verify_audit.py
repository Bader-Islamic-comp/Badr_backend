"""Verify the hash-chained audit trails (governance task 7); exit 1 if any is broken.

    python scripts/verify_audit.py [PATH ...]
Defaults: corpus/governance/audit.jsonl and releases/audit.jsonl (a missing file has no events).
"""
import sys
from pathlib import Path

import _common  # noqa: F401
from _common import CONTENT_AUDIT, RELEASES
from companion_api.governance import audit


def main(argv=None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])] or [CONTENT_AUDIT, RELEASES / "audit.jsonl"]
    broken = 0
    for path in paths:
        result = audit.verify(path)
        print(f"{'ok    ' if result.ok else 'BROKEN'} {path}: {result.events} events"
              + (f" - {result.problem}" if result.problem else ""))
        broken += not result.ok
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
