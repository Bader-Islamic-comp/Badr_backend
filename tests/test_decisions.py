"""Signed human decisions (apply_decisions): the only path to approved, cleared or rejected."""
import json

import pytest
import yaml

from companion_api.governance import audit, decisions, review

SOURCE = {"source_id": "tanzil-demo", "format": "txt", "title": "t", "edition": "e", "publisher": "p",
          "url": "https://example.invalid/x", "license": "l", "license_url": None, "terms_summary": "t",
          "retrieved_at": None, "sha256": None, "numbering_system": "n", "status": "pending_legal", "notes": None}


def _setup(tmp_path, entries, reviewers=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    registry = tmp_path / "registry.yaml"
    registry.write_text("# header\nschema_version: 1\nsources:\n" + yaml.safe_dump([SOURCE], sort_keys=False))
    (tmp_path / "reviewers.yaml").write_text(yaml.safe_dump({"reviewers": list(reviewers)}))
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    version = {"text": "t", "lesson": "l", "author": "Writer", "reviewer": None, "review_status": "in_review",
               "reading_level_checks": {"status": "pass"}}
    (drafts / "d.yaml").write_text("# h\n" + yaml.safe_dump({"schema_version": 1, "id": "story-yusuf-s01",
                                                             "versions": {"7-9": version, "10-11": dict(version)}}))
    (tmp_path / "decisions.yaml").write_text(yaml.safe_dump({"schema_version": 1, "decisions": entries}))
    return decisions.Paths(decisions=tmp_path / "decisions.yaml", state=tmp_path / "state.json",
                           audit=tmp_path / "audit.jsonl", reviewers=tmp_path / "reviewers.yaml",
                           registry=registry, drafts=drafts,
                           known_items=frozenset({"source:tanzil-demo", "policy-scope", "selection-01",
                                                  "story-yusuf-s01@7-9", "adam-01-msa", "adr-0005"}))


def _entry(**overrides):
    base = {"decision_id": "D-1", "item_ids": ["source:tanzil-demo"], "decision": "approve",
            "decided_by": "Mousa al-Rashdan", "role": "governance", "date": "2026-10-01", "note": "ok"}
    base.update(overrides)
    return base


def test_rights_owner_clears_a_source_and_it_is_audited(tmp_path):
    paths = _setup(tmp_path, [_entry()])
    assert decisions.apply(paths)["applied"] == ["D-1"]
    assert yaml.safe_load(paths.registry.read_text())["sources"][0]["status"] == "cleared"
    assert paths.registry.read_text().startswith("# header\n")
    events = [json.loads(line) for line in paths.audit.read_text().splitlines()]
    assert events[0]["action"] == "decision.approve" and events[0]["actor"] == "Mousa al-Rashdan"
    assert audit.verify(paths.audit).ok
    assert decisions.apply(paths) == {"applied": [], "already_applied": 1}  # idempotent


@pytest.mark.parametrize("change, message", [
    ({"decided_by": ""}, "decided_by is empty"),
    ({"date": "2026-10"}, "full ISO date"),
    ({"decision": "ok"}, "decision must be one of"),
    ({"decided_by": "Momen Alhamza", "role": "pipeline"}, "belong to Mousa al-Rashdan"),
    ({"item_ids": ["source:unknown"]}, "unknown item"),
])
def test_invalid_or_unauthorised_decisions_refuse_the_whole_file(tmp_path, change, message):
    paths = _setup(tmp_path, [_entry(decision_id="D-0", item_ids=["policy-scope"]), _entry(**change)])
    with pytest.raises(decisions.DecisionError, match=message):
        decisions.apply(paths)
    assert not paths.audit.exists() and not paths.state.exists()  # nothing applied, not even the valid one


def test_missing_field_is_refused(tmp_path):
    entry = _entry()
    del entry["note"]
    with pytest.raises(decisions.DecisionError, match="missing note"):
        decisions.apply(_setup(tmp_path, [entry]))


def test_content_needs_a_qualified_reviewer_with_the_role(tmp_path):
    item = {"item_ids": ["selection-01"], "decided_by": "Mousa al-Rashdan", "role": "governance"}
    with pytest.raises(decisions.DecisionError, match="not a qualified reviewer"):
        decisions.apply(_setup(tmp_path, [_entry(**item)]))
    scholar = {"name": "Scholar", "qualified": True, "roles": ["scholarly"], "conflicts": []}
    paths = _setup(tmp_path / "ok", [_entry(item_ids=["selection-01"], decided_by="Scholar", role="scholarly")],
                   [scholar])
    decisions.apply(paths)
    assert decisions.status_of(paths.state, "selection-01") == "approved"


def test_age_band_approval_goes_through_the_review_tool(tmp_path):
    scholar = {"name": "Scholar", "qualified": True, "roles": ["scholarly"], "conflicts": []}
    paths = _setup(tmp_path, [_entry(item_ids=["story-yusuf-s01@7-9"], decided_by="Scholar", role="scholarly")],
                   [scholar])
    decisions.apply(paths)
    item = next(i for i in review.items(paths.drafts) if i.item_id == "story-yusuf-s01@7-9")
    assert item.status == "approved" and item.reviewer == "Scholar"
    assert json.loads(paths.audit.read_text().splitlines()[0])["action"] == "review.approve"


def test_review_tool_refuses_approval_without_a_decision(tmp_path):
    paths = _setup(tmp_path, [])
    with pytest.raises(review.ReviewError, match="signed decision"):
        review.transition(paths.drafts, "story-yusuf-s01@7-9", "approve", "Scholar", audit_path=paths.audit,
                          reviewers_path=paths.reviewers)


def test_eval_items_by_pipeline_owner_and_adr(tmp_path):
    paths = _setup(tmp_path, [_entry(item_ids=["adam-01-msa", "adr-0005"], decided_by="Momen Alhamza",
                                     role="pipeline")])
    decisions.apply(paths)
    assert decisions.status_of(paths.state, "adr-0005") == "approved"
