"""Verify the hash-chained audit trails (governance task 7); exit 1 if any is broken.

    python scripts/verify_audit.py [PATH ...]
    python scripts/verify_audit.py --write-anchor    record the content trail's head for committing

Defaults: corpus/governance/audit.jsonl and releases/audit.jsonl (a missing file has no events).

Anchors (test/corpus-tasks): a hash chain alone misses lost final events and a consistent rewrite. The content
trail is checked against corpus/governance/audit_anchor.json, which `--write-anchor` writes and which is
committed with each batch of decisions; the release trail is checked against the `auditHead` every release
manifest recorded when it was built. A trail that ends before an anchor, or differs at it, is broken.
"""
import json
import sys
from pathlib import Path

import _common  # noqa: F401
from _common import CONTENT_AUDIT, RELEASES, ROOT
from companion_api.governance import audit

ANCHOR = ROOT / "corpus/governance/audit_anchor.json"


def _release_anchors(releases: Path) -> list[dict]:
    anchors = []
    for manifest in sorted(releases.glob("*/manifest.json")):
        head = json.loads(manifest.read_text(encoding="utf-8")).get("pipeline", {}).get("auditHead")
        if head:
            anchors.append(head)
    return anchors


def anchors_for(path: Path) -> list[dict]:
    if path.resolve() == CONTENT_AUDIT.resolve() and ANCHOR.is_file():
        return [json.loads(ANCHOR.read_text(encoding="utf-8"))]
    if path.resolve() == (RELEASES / "audit.jsonl").resolve():
        return _release_anchors(RELEASES)
    return []


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--write-anchor" in args:
        head = audit.head(CONTENT_AUDIT)
        if head is None:
            print("the content trail has no events; nothing to anchor")
            return 0
        ANCHOR.write_text(json.dumps(head, indent=1) + "\n", encoding="utf-8")
        print(f"anchored {CONTENT_AUDIT.relative_to(ROOT)} at event {head['seq']}; commit {ANCHOR.relative_to(ROOT)}")
        return 0
    paths = [Path(p) for p in args] or [CONTENT_AUDIT, RELEASES / "audit.jsonl"]
    broken = 0
    for path in paths:
        anchors = anchors_for(path)
        result = audit.verify(path, anchors)
        print(f"{'ok    ' if result.ok else 'BROKEN'} {path}: {result.events} events, {len(anchors)} anchors"
              + (f" - {result.problem}" if result.problem else ""))
        broken += not result.ok
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
