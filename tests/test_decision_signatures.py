"""Signed decisions (governance/signatures.py): only a commit SSH-signed by the person a decision names counts.

Runs real git and ssh-keygen in a temporary repository; skipped where either is missing.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

from companion_api.governance import signatures

pytestmark = pytest.mark.skipif(not (shutil.which("git") and shutil.which("ssh-keygen")),
                                reason="needs git and ssh-keygen")

DECISION = """schema_version: 1
decisions:
- decision_id: D-0001
  item_ids: ["policy-scope"]
  decision: approve
  decided_by: Mousa al-Rashdan
  role: governance
  date: 2026-10-01
  note: "test decision"
"""


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def _key(folder: Path, name: str) -> Path:
    key = folder / name
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True,
                   capture_output=True)
    return key


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    _run(repo, "config", "user.name", "Test")
    _run(repo, "config", "user.email", "test@example.invalid")
    _run(repo, "config", "commit.gpgsign", "false")
    return repo


def _commit(repo: Path, message: str, key: Path | None = None):
    _run(repo, "add", "-A")
    if key is None:
        _run(repo, "commit", "-q", "-m", message)
    else:
        _run(repo, "-c", "gpg.format=ssh", "-c", f"user.signingkey={key.as_posix()}", "commit", "-q", "-S", "-m",
             message)


def _signers(path: Path, key: Path, principal: str = "mousa@example.invalid"):
    public = (key.parent / (key.name + ".pub")).read_text(encoding="utf-8").strip()
    path.write_text(f"signers:\n- name: Mousa al-Rashdan\n  principal: {principal}\n  key: {public}\n",
                    encoding="utf-8")


def _check(repo: Path, signers: Path):
    decisions = repo / "decisions.yaml"
    import yaml
    entries = yaml.safe_load(decisions.read_text(encoding="utf-8"))["decisions"]
    return signatures.check(decisions, entries, signers, repo)


def test_a_decision_signed_by_the_person_it_names_passes(repo, tmp_path):
    key = _key(tmp_path, "mousa")
    _signers(tmp_path / "signers.yaml", key)
    (repo / "decisions.yaml").write_text(DECISION, encoding="utf-8")
    _commit(repo, "D-0001", key)
    assert _check(repo, tmp_path / "signers.yaml") == {}


def test_an_unsigned_or_uncommitted_decision_is_refused(repo, tmp_path):
    key = _key(tmp_path, "mousa")
    _signers(tmp_path / "signers.yaml", key)
    (repo / "decisions.yaml").write_text(DECISION, encoding="utf-8")
    problems = _check(repo, tmp_path / "signers.yaml")
    assert problems and any("committed" in problem for problem in problems["D-0001"])
    _commit(repo, "D-0001 unsigned")
    assert any("not signed by a registered key" in p for p in _check(repo, tmp_path / "signers.yaml")["D-0001"])


def test_a_signature_by_someone_else_does_not_count(repo, tmp_path):
    mousa, other = _key(tmp_path, "mousa"), _key(tmp_path, "other")
    _signers(tmp_path / "signers.yaml", mousa)
    (repo / "decisions.yaml").write_text(DECISION, encoding="utf-8")
    _commit(repo, "D-0001 by someone else", other)
    assert any("not signed by a registered key" in p for p in _check(repo, tmp_path / "signers.yaml")["D-0001"])


def test_a_signed_entry_edited_in_an_unsigned_commit_is_refused(repo, tmp_path):
    key = _key(tmp_path, "mousa")
    _signers(tmp_path / "signers.yaml", key)
    (repo / "decisions.yaml").write_text(DECISION, encoding="utf-8")
    _commit(repo, "D-0001", key)
    (repo / "decisions.yaml").write_text(DECISION.replace("policy-scope", "policy-source-policy"), encoding="utf-8")
    _commit(repo, "changed the item, unsigned")
    assert "D-0001" in _check(repo, tmp_path / "signers.yaml")


def test_no_registered_key_refuses_every_decision(repo, tmp_path):
    (tmp_path / "signers.yaml").write_text("signers: []\n", encoding="utf-8")
    (repo / "decisions.yaml").write_text(DECISION, encoding="utf-8")
    assert "no signing key is registered" in _check(repo, tmp_path / "signers.yaml")["D-0001"][0]


def test_entry_lines_cover_each_decision():
    text = DECISION + DECISION.split("decisions:\n")[1].replace("D-0001", "D-0002")
    lines = signatures.entry_lines(text)
    assert lines["D-0001"] == (3, 9) and lines["D-0002"] == (10, 16)
