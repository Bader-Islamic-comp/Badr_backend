#!/usr/bin/env python3
"""Check that a frozen corpus release still matches its recorded hashes."""

import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("version must be numeric major.minor.patch")
    folder = HERE / "releases" / args.version
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != args.version:
        parser.error("release version mismatch")
    for name, expected in manifest["sha256"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            parser.error(f"release file changed or missing: {name}")
    print(f"OK: release {args.version}, {len(manifest['sha256'])} files verified")


if __name__ == "__main__":
    main()
