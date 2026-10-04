#!/usr/bin/env python3
"""Create an immutable, hashed corpus snapshot after all review gates pass."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ("content.json", "sources.json", "evaluation.json", "approvals.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="new version, e.g. 1.0.0")
    parser.add_argument("--supersedes", help="previous release version, if any")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        parser.error("version must be numeric major.minor.patch")
    if subprocess.call([sys.executable, str(HERE / "validate.py"), "--release"]) != 0:
        return 1
    releases = HERE / "releases"
    target = releases / args.version
    if target.exists():
        parser.error("release already exists; create a new version")
    if args.supersedes and not (releases / args.supersedes / "manifest.json").is_file():
        parser.error("superseded release not found")
    target.mkdir(parents=True)
    # Third-party files stay out of the package: the release records the registry's pins for them instead.
    sys.path.insert(0, str(HERE.parents[1] / "src"))
    from companion_api.corpusprep import registry as registry_module
    registry = registry_module.load(HERE.parents[1] / "corpus/sources/registry.yaml")
    source_list = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))["sources"]
    pinned = {
        source[key]: registry.get(source[key])["sha256"] for source in source_list
        for key in ("registry_source_id", "registry_license_source_id") if source.get(key)
    }
    hashes = {}
    for name in FILES:
        source = (HERE / name).resolve()
        if not source.is_relative_to(HERE):
            parser.error(f"source path escapes corpus directory: {name}")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {
        "version": args.version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "supersedes": args.supersedes,
        "sha256": hashes,
        "registry_sources_sha256": pinned,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
