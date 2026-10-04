"""Shared setup for the corpus scripts: repository root on sys.path and default paths."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

REGISTRY = ROOT / "corpus/sources/registry.yaml"
GOVERNANCE = ROOT / "corpus/governance"
CONTENT_AUDIT = GOVERNANCE / "audit.jsonl"
REVIEWERS = GOVERNANCE / "reviewers.yaml"
POLICY_VERSION = GOVERNANCE / "policy_version.txt"
DRAFTS = ROOT / "corpus/drafts/age_band"
RELEASES = ROOT / "releases"


def policy_version() -> str:
    return POLICY_VERSION.read_text(encoding="utf-8").strip() if POLICY_VERSION.is_file() else "unversioned"
