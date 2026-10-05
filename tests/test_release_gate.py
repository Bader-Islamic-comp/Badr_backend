"""The release gate (doc/governance/release-gate.md): one checklist that must be green before /v1/bootstrap offers a
child `generativeAnswers` or `voice`."""
from pathlib import Path
import sys
import typing

import pytest

from companion_api import schemas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_release_gate as gate  # noqa: E402


def _values(model, field) -> set:
    return set(typing.get_args(model.model_fields[field].annotation))


def test_the_checklist_is_well_formed_and_documented():
    config = gate.load()
    assert config["switches"] == ["generativeAnswers", "voice"]
    doc = (ROOT / "doc/governance/release-gate.md").read_text(encoding="utf-8")
    for item in config["items"]:
        assert f"| {item['id']} | {item['kind']} |" in doc, item["id"]
    for switch in config["switches"]:
        assert any(item["kind"] == "H" and switch in item["gates"] for item in config["items"]), switch


@pytest.mark.parametrize("item, problem", [
    ({"id": "X1", "kind": "Q", "gates": ["voice"], "text": "t"}, "kind must be one of"),
    ({"id": "X1", "kind": "M", "gates": ["chat"], "text": "t", "evidence": ["a"]}, "gates must be"),
    ({"id": "X1", "kind": "H", "gates": ["voice"], "text": "t", "decisions": ["reviewers"]},
     "needs decisions and an owner"),
    ({"id": "X1", "kind": "M", "gates": ["voice"], "text": "t"}, "needs evidence or a check"),
    ({"id": "X1", "kind": "M", "gates": ["voice"], "text": "t", "check": "vibes"}, "unknown check"),
])
def test_a_malformed_item_is_refused(item, problem):
    problems = gate.validate({"switches": ["generativeAnswers", "voice"], "items": [item]})
    assert any(problem in line for line in problems), problems


def test_items_are_green_only_with_applied_audited_decisions_and_passing_evidence(monkeypatch):
    monkeypatch.setattr(gate, "decision_state", lambda: {"items": {"reviewers": {"status": "approved"},
                                                                  "policy-scope": {"status": "approved"}}})
    monkeypatch.setattr(gate, "_audited_items", lambda: {"reviewers"})
    monkeypatch.setattr(gate.decisions, "known_items", lambda root: frozenset({"reviewers", "policy-scope"}))
    config = {"switches": ["generativeAnswers", "voice"], "items": [
        {"id": "H1", "kind": "H", "gates": ["voice"], "text": "decided", "owner": "o", "decisions": ["reviewers"]},
        {"id": "H2", "kind": "H", "gates": ["voice"], "text": "not audited", "owner": "o",
         "decisions": ["policy-scope"]},
        {"id": "H3", "kind": "H", "gates": ["generativeAnswers"], "text": "no document", "owner": "o",
         "decisions": ["policy-dpia-chatbot"]},
        {"id": "M1", "kind": "M", "gates": ["voice"], "text": "present", "evidence": ["pyproject.toml"]},
        {"id": "M2", "kind": "M", "gates": ["voice"], "text": "absent", "evidence": ["no/such/file.txt"]},
        {"id": "M3", "kind": "M", "gates": ["voice"], "text": "skipped", "evidence": ["python3 -c pass"]},
    ]}
    result = gate.evaluate(config, no_run=True)
    assert {row["id"]: row["green"] for row in result["items"]} == {
        "H1": True, "H2": False, "H3": False, "M1": True, "M2": False, "M3": False}
    why = {row["id"]: row["why"] for row in result["items"]}
    assert why["H3"] == "write doc/governance/dpia-chatbot.md, then decide it"
    assert why["M2"] == "missing no/such/file.txt" and why["M3"] == "not run (--no-run)"
    assert not result["green"]
    voice = gate.evaluate(config, switch="voice", no_run=True)
    assert [row["id"] for row in voice["items"]] == ["H1", "H2", "M1", "M2", "M3"]
    assert gate.evaluate({"switches": ["voice"], "items": [config["items"][0]]}, no_run=True)["green"]


def test_bootstrap_offers_a_child_no_switch_while_the_gate_is_red():
    # The schema is the switch: /v1/bootstrap reports mode "development" only, where generativeAnswers serves adult
    # operators (ADR 0003), and voice is always false. Allowing another mode or voice=true fails here unless every
    # human item of the switch is green; the automated items are the script's, run by CI before a release.
    switches = []
    if _values(schemas.Bootstrap, "mode") != {"development"}:
        switches.append("generativeAnswers")
    if _values(schemas.Features, "voice") != {False}:
        switches.append("voice")
    config = gate.load()
    for switch in switches:
        human = {"switches": config["switches"],
                 "items": [item for item in config["items"] if item["kind"] == "H"]}
        result = gate.evaluate(human, switch=switch)
        assert result["green"], [f"{row['id']}: {row['why']}" for row in result["items"] if not row["green"]]
    assert switches or (_values(schemas.Bootstrap, "mode"), _values(schemas.Features, "voice")) == ({"development"},
                                                                                                  {False})


@pytest.mark.parametrize("expected, outcome, possible, ok", [
    ("redirect", "redirected", {"redirected"}, True),
    ("refuse", "redirected", {"redirected"}, True),
    ("redirect", "abstained", {"abstained"}, False),     # a fixed route must be taken as such
    ("safety", "safety", {"safety"}, True),
    ("disclose", "disclosed", {"disclosed"}, True),
    ("abstain", "abstained", {"abstained"}, True),
    ("abstain", "grounded", {"grounded", "abstained"}, True),           # the model may still decline
    ("abstain", "grounded", {"grounded", "abstained", "chat"}, False),  # but never chat about it
    ("abstain", "grounded", {"grounded"}, False),                       # served word for word: no abstention left
])
def test_the_harmful_check_accepts_only_where_the_set_says(expected, outcome, possible, ok):
    import eval_serving
    assert eval_serving._as_expected(expected, outcome, possible) is ok
