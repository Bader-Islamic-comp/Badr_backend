"""Governance tooling (corpus tasks Phase 4): audit trail, review workflow, releases, re-review triggers."""
import json
import os
from pathlib import Path

import pytest
import yaml

from companion_api.config import Settings
from companion_api.governance import audit, due, releases, review
from companion_api.rag.release import ReleaseError, load_release

SOURCE = {"title": "t", "edition": "e", "publisher": "p", "url": "https://example.invalid/x", "license": "l",
          "license_url": None, "terms_summary": "t", "retrieved_at": "2026-09-27T00:00:00+00:00",
          "sha256": "a" * 64, "numbering_system": "n", "notes": "reason", "format": "txt"}


# --- audit ------------------------------------------------------------------------------------------------

def _trail(tmp_path, n=3):
    path = tmp_path / "audit.jsonl"
    for i in range(n):
        audit.append(path, actor="A", action="x", item=f"i{i}", from_state=None, to_state="s")
    return path


def test_audit_chain_verifies_and_detects_every_kind_of_tampering(tmp_path):
    path = _trail(tmp_path)
    assert audit.verify(path).ok and audit.verify(path).events == 3
    lines = path.read_text().splitlines()
    for broken, expected in (
        ([lines[0], lines[1].replace('"i1"', '"i9"'), lines[2]], "line 2 was modified"),
        ([lines[0], lines[2]], "line 2 has seq 3"),
        ([lines[1], lines[0], lines[2]], "line 1 has seq 2"),
    ):
        path.write_text("\n".join(broken) + "\n")
        result = audit.verify(path)
        assert not result.ok and expected in result.problem


def test_append_refuses_a_broken_trail(tmp_path):
    path = _trail(tmp_path, 2)
    path.write_text(path.read_text().replace('"i0"', '"zz"'))
    with pytest.raises(audit.AuditError, match="broken"):
        audit.append(path, actor="A", action="x", item="i", from_state=None, to_state="s")


# --- review -----------------------------------------------------------------------------------------------

def _draft(tmp_path, status="draft", checks="pass", author="Writer"):
    drafts = tmp_path / "drafts"
    drafts.mkdir(exist_ok=True)
    version = {"text": "t", "lesson": "l", "author": author, "reviewer": None, "review_status": status,
               "reading_level_checks": {"status": checks}}
    data = {"schema_version": 1, "id": "story-yusuf-s01", "versions": {"7-9": version, "10-11": dict(version)}}
    (drafts / "d.yaml").write_text("# header\n" + yaml.safe_dump(data, allow_unicode=True))
    reviewers = tmp_path / "reviewers.yaml"
    reviewers.write_text(yaml.safe_dump({"reviewers": [
        {"name": "Scholar", "qualified": True, "conflicts": []},
        {"name": "Conflicted", "qualified": True, "conflicts": ["story-yusuf-s01"]},
        {"name": "Trainee", "qualified": False}]}))
    return drafts, reviewers


def _go(drafts, reviewers, tmp_path, action, actor, reason=""):
    decision = "D-test" if action in ("approve", "reject") else None
    return review.transition(drafts, "story-yusuf-s01@7-9", action, actor, audit_path=tmp_path / "a.jsonl",
                             reviewers_path=reviewers, reason=reason, decision_id=decision)


def test_review_flow_is_audited(tmp_path):
    drafts, reviewers = _draft(tmp_path)
    assert _go(drafts, reviewers, tmp_path, "submit", "Writer").status == "in_review"
    item = _go(drafts, reviewers, tmp_path, "approve", "Scholar")
    assert item.status == "approved" and item.reviewer == "Scholar"
    assert (drafts / "d.yaml").read_text().startswith("# header\n")
    events = [json.loads(line) for line in (tmp_path / "a.jsonl").read_text().splitlines()]
    assert [(e["action"], e["from_state"], e["to_state"]) for e in events] == [
        ("review.submit", "draft", "in_review"), ("review.approve", "in_review", "approved")]
    assert audit.verify(tmp_path / "a.jsonl").ok


@pytest.mark.parametrize("actor, message", [("Writer", "cannot review"), ("Trainee", "not a qualified"),
                                            ("Stranger", "not a qualified"), ("Conflicted", "conflict of interest")])
def test_approval_refusals(tmp_path, actor, message):
    drafts, reviewers = _draft(tmp_path, status="in_review")
    with pytest.raises(review.ReviewError, match=message):
        _go(drafts, reviewers, tmp_path, "approve", actor)
    assert not (tmp_path / "a.jsonl").exists()  # a refused action leaves no event


def test_failed_checks_block_approval_and_reject_needs_reason(tmp_path):
    drafts, reviewers = _draft(tmp_path, status="in_review", checks="fail")
    with pytest.raises(review.ReviewError, match="reading-level checks"):
        _go(drafts, reviewers, tmp_path, "approve", "Scholar")
    with pytest.raises(review.ReviewError, match="needs a reason"):
        _go(drafts, reviewers, tmp_path, "reject", "Scholar")
    assert _go(drafts, reviewers, tmp_path, "reject", "Scholar", "unsupported detail").status == "rejected"
    assert _go(drafts, reviewers, tmp_path, "revise", "Writer").status == "draft"


def test_only_the_author_submits(tmp_path):
    drafts, reviewers = _draft(tmp_path)
    with pytest.raises(review.ReviewError, match="only the author"):
        _go(drafts, reviewers, tmp_path, "submit", "Scholar")


# --- releases ---------------------------------------------------------------------------------------------

def _corpus(tmp_path, statuses=("pending_legal", "candidate")):
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"schema_version": 1, "sources": [
        dict(SOURCE, source_id="good-source", status=statuses[0]),
        dict(SOURCE, source_id="unclear-source", status=statuses[1])]}, sort_keys=False))
    root = tmp_path / "corpus"
    (root / "documents").mkdir(parents=True, exist_ok=True)
    (root / "corpus.json").write_text(json.dumps({"schemaVersion": 1, "id": "demo", "title": "Demo"}))
    for doc_id, source_id in (("doc-good", "good-source"), ("doc-unclear", "unclear-source")):
        (root / "documents" / f"{doc_id}.json").write_text(json.dumps({
            "schemaVersion": 2, "id": doc_id, "kind": "passage", "title": doc_id, "language": "en",
            "ageBands": ["7-9"], "contentType": "tafsir", "madhhab": [], "curriculumPolicy": "t", "synthetic": False,
            "source": {"work": "w", "edition": "e", "publisher": "p", "translator": None, "license": "l",
                       "checksum": None}, "grading": None,
            "review": {"status": "draft", "reviewer": None, "approvedOn": None, "supersedes": None},
            "tier": 1, "sourceIds": [source_id],
            "units": [{"id": "u1", "text": f"text of {doc_id} here", "sourceRefs": ["quran:1:1"]}]}))
    return root, registry


def _build(tmp_path, release_id, **kwargs):
    root, registry = _corpus(tmp_path)
    return releases.build(root, tmp_path / "releases", release_id, registry_path=registry, actor="Builder",
                          policy_version="p1", **kwargs)


def test_release_excludes_candidate_sources_records_provenance_and_is_read_only(tmp_path):
    path, summary = _build(tmp_path, "rel-1")
    assert summary["documents"] == 1 and summary["excluded"] == {"source unclear-source is candidate": 1}
    loaded = load_release(path)
    assert {chunk.document_id for chunk in loaded.chunks} == {"doc-good"}
    assert all(chunk.release_id == "rel-1" for chunk in loaded.chunks)
    pipeline = loaded.manifest.pipeline
    assert pipeline["sourceSha256"] == {"good-source": "a" * 64} and pipeline["policyVersion"] == "p1"
    assert len(pipeline["registrySha256"]) == 64 and pipeline["gitCommit"]
    assert not os.access(path / "chunks.jsonl", os.W_OK)


def test_editing_a_published_file_fails_verification(tmp_path):
    path, _ = _build(tmp_path, "rel-1")
    target = path / "chunks.jsonl"
    path.chmod(0o755)
    target.chmod(0o644)
    target.write_text(target.read_text().replace("text of doc-good", "altered text"))
    with pytest.raises(ReleaseError, match="checksum"):
        load_release(path)


def test_promote_rollback_and_quarantine(tmp_path):
    root = tmp_path / "releases"
    _build(tmp_path, "rel-1")
    _build(tmp_path, "rel-2")
    releases.promote(root, "rel-1", actor="Ops")
    releases.promote(root, "rel-2", actor="Ops")
    assert load_release(root / "current_release").manifest.release_id == "rel-2"
    assert releases.rollback(root, actor="Ops", reason="drill") == "rel-1"
    assert releases.current(root) == "rel-1"
    with pytest.raises(ReleaseError, match="no earlier release"):
        releases.rollback(root, actor="Ops", reason="again")
    releases.promote(root, "rel-2", actor="Ops")
    assert releases.rollback(root, actor="Ops", reason="bad content", quarantine=True) == "rel-1"
    with pytest.raises(ReleaseError, match="quarantined"):
        releases.promote(root, "rel-2", actor="Ops")
    with pytest.raises(ReleaseError, match="quarantined"):
        load_release(root / "rel-2")
    assert audit.verify(root / "audit.jsonl").ok


def test_config_accepts_a_current_release_pointer(tmp_path):
    root = tmp_path / "releases"
    _build(tmp_path, "rel-1")
    releases.promote(root, "rel-1", actor="Ops")
    settings = Settings(rag_enabled=True, rag_release=str(root / "current_release"), embedding_model="hashing")
    settings.require_rag()


# --- re-review triggers -----------------------------------------------------------------------------------

def test_due_for_review_triggers(tmp_path):
    path, _ = _build(tmp_path, "rel-1")
    _, registry = _corpus(tmp_path)
    same = due.due(path, registry, embedding_model="hashing-v1", policy_version="p1")
    assert same["due"] == 0 and same["reason_counts"] == {"never_approved": 1}
    data = yaml.safe_load(registry.read_text())
    data["sources"][0]["sha256"] = "b" * 64
    registry.write_text(yaml.safe_dump(data, sort_keys=False))
    changed = due.due(path, registry, embedding_model="other-model", policy_version="p2")
    assert changed["items"][0]["reasons"] == ["embedding_changed", "policy_changed", "source_changed",
                                              "never_approved"]
