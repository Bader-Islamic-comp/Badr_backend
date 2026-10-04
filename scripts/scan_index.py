"""Scan a release (the vector index) for anything that must not be there (task 15); exit 1 on any problem.

    python scripts/scan_index.py [RELEASE_DIR or releases/current_release]

Checks that every chunk id is listed in the manifest, every chunk's text matches its checksum, and every
chunk passes the admission rule: registered, non-blocked sources, or synthetic app help. Prints ids only.
"""
import sys
from pathlib import Path

import _common  # noqa: F401
from _common import REGISTRY, RELEASES
from companion_api.corpusprep import registry as registry_module
from companion_api.rag.release import ReleaseError, scan


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    target = Path(args[0]) if args else RELEASES / "current_release"
    sources = {s["source_id"]: s["status"] for s in registry_module.load(REGISTRY).sources}
    try:
        problems = scan(target, sources)
    except ReleaseError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    for problem in problems[:50]:
        print(f"PROBLEM {problem}")
    print(f"{target}: {'clean' if not problems else f'{len(problems)} problems'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
