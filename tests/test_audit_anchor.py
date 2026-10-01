"""Audit anchors (test/corpus-tasks): a chain plus an anchor kept elsewhere catches lost final events and a
consistent rewrite, which the chain alone verified as fine."""
import json

from companion_api.governance import audit


def _trail(path, count=3):
    for number in range(count):
        audit.append(path, actor="tester", action="review.approve", item=f"item-{number}", from_state="draft",
                     to_state="approved", at="2026-10-01T00:00:00+00:00")


def test_deleting_the_last_events_is_caught_by_the_anchor(tmp_path):
    path = tmp_path / "audit.jsonl"
    _trail(path)
    anchor = audit.head(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
    assert audit.verify(path).ok  # the chain alone cannot tell
    result = audit.verify(path, [anchor])
    assert not result.ok and "events were removed" in result.problem


def test_a_consistent_rewrite_is_caught_by_the_anchor(tmp_path):
    path, forged = tmp_path / "audit.jsonl", tmp_path / "forged.jsonl"
    _trail(path)
    anchor = audit.head(path)
    for number in range(3):  # a whole new, internally valid chain with different content
        audit.append(forged, actor="someone else", action="review.approve", item=f"item-{number}",
                     from_state="draft", to_state="approved", at="2026-10-01T00:00:00+00:00")
    path.write_text(forged.read_text(encoding="utf-8"), encoding="utf-8")
    assert audit.verify(path).ok
    result = audit.verify(path, [anchor])
    assert not result.ok and "rewritten" in result.problem


def test_a_trail_that_grew_past_its_anchor_is_fine(tmp_path):
    path = tmp_path / "audit.jsonl"
    _trail(path, 2)
    anchor = audit.head(path)
    _trail(path, 2)
    assert audit.verify(path, [anchor, None]).ok and audit.head(path)["seq"] == 4
    assert audit.head(tmp_path / "missing.jsonl") is None
    assert json.loads(json.dumps(anchor)) == anchor  # an anchor is plain JSON, for a committed file
