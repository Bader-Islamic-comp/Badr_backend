"""Build an immutable, read-only corpus release with provenance (governance task 5).

    python scripts/build_release.py corpus/wave1 --release-id wave1-dev-1 --actor "Momen Alhamza"
        [--embedding-model hashing] [--promote]

Sources that are candidate or rejected in the registry are left out. The manifest records the
registry and source sha256, the embedding model, the git commit and the policy version.
"""
import argparse
import sys
from pathlib import Path

import _common  # noqa: F401
from _common import POLICY_VERSION, REGISTRY, RELEASES, ROOT, policy_version
from companion_api.governance import releases
from companion_api.rag.release import ReleaseError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corpus_dir", type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--actor", required=True, help="who builds it (recorded in the audit trail)")
    parser.add_argument("--out", type=Path, default=RELEASES)
    parser.add_argument("--embedding-model", default="hashing")
    parser.add_argument("--channel", default="development", choices=("development", "published"))
    parser.add_argument("--promote", action="store_true", help="also point current_release at it")
    args = parser.parse_args(argv)
    try:
        path, summary = releases.build(args.corpus_dir, args.out, args.release_id, registry_path=REGISTRY,
                                       actor=args.actor, embedding_model=args.embedding_model, channel=args.channel,
                                       canonical_manifest=ROOT / "corpus/canonical/manifest.json",
                                       policy_version=policy_version(), repo_root=ROOT)
        if args.promote:
            releases.promote(args.out, args.release_id, actor=args.actor, reason="promoted at build")
    except ReleaseError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(f"built {path} {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
