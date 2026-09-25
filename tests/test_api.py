from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from companion_api.config import Settings
from companion_api.main import create_app


TOKEN = "synthetic-operator-token-for-tests"


@pytest.fixture
def client():
    with TestClient(create_app(Settings(demo_mode=True, demo_token=TOKEN))) as value:
        value.headers["X-Demo-Token"] = TOKEN
        yield value


def write(client, method, path, body=None, key=None):
    return client.request(method, path, json=body, headers={"Idempotency-Key": key or str(uuid4())})


def conversation(client):
    response = write(client, "POST", "/v1/conversations", {})
    assert response.status_code == 200
    return response.json()["conversationId"]


def test_disabled_or_missing_secret_denies_startup():
    for settings in [Settings(), Settings(demo_mode=True), Settings(demo_mode=True, demo_token="short")]:
        with pytest.raises(RuntimeError):
            create_app(settings)


def test_demo_requires_operator_token(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/v1/bootstrap", headers={"X-Demo-Token": "wrong"}).status_code == 401
    data = client.get("/v1/bootstrap").json()
    assert data["features"] == {"voice": False, "generativeAnswers": False, "unity": False}
    assert data["contentStatus"] == "awaiting_review"


def test_reward_retry_and_new_keys_grant_exactly_once(client):
    path = "/v1/lessons/demo-learning/complete"
    first = write(client, "POST", path, {}, "reward-key-1")
    assert first.json() == {"lessonId": "demo-learning", "completed": True, "earned": 5, "balance": 5}
    assert write(client, "POST", path, {}, "reward-key-1").json() == first.json()
    assert write(client, "POST", path, {}).json()["earned"] == 0
    assert client.get("/v1/rewards").json()["balance"] == 5
    assert client.get("/v1/challenges/today").json()["items"][0]["completed"] is True
    assert len(client.app.state.store.ledger) == 1


def test_concurrent_reward_writes_are_atomic(client):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: write(client, "POST", "/v1/lessons/demo-learning/complete", {}).json(), range(16)))
    assert sum(r["earned"] for r in results) == 5
    assert len(client.app.state.store.ledger) == 1


def test_cosmetics_reject_unknown_and_write_key_conflicts(client):
    path = "/v1/equipped-cosmetics"
    assert write(client, "PUT", path, {"cosmeticId": "default"}, "cosmetic-key").json()["cosmeticId"] == "default"
    assert write(client, "PUT", path, {"cosmeticId": "secret-value"}, "cosmetic-key").status_code == 409
    assert write(client, "PUT", path, {"cosmeticId": "secret-value"}).status_code == 403
    assert client.get("/v1/inventory").json()["items"][0]["equipped"] is True


def test_turn_idempotency_does_not_retain_input(client):
    cid = conversation(client)
    text = "SYNTHETIC_SENSITIVE_TEXT_do_not_retain"
    first = write(client, "POST", f"/v1/conversations/{cid}/turns", {"text": text}, "turn-key-1")
    assert first.status_code == 200
    assert write(client, "POST", f"/v1/conversations/{cid}/turns", {"text": text}, "turn-key-1").json() == first.json()
    assert write(client, "POST", f"/v1/conversations/{cid}/turns", {"text": "changed"}, "turn-key-1").status_code == 409
    turn = client.get("/v1/turns/" + first.json()["turnId"]).json()
    assert turn["citations"] == [] and turn["sources"] == []
    assert (turn["status"], turn["answerType"]) == ("completed", "unavailable")
    assert text not in turn["text"]
    assert text not in repr(vars(client.app.state.store))


def test_sse_resume_and_invalid_cursor(client):
    cid = conversation(client)
    tid = write(client, "POST", f"/v1/conversations/{cid}/turns", {"text": "synthetic question"}).json()["turnId"]
    path = f"/v1/turns/{tid}/events"
    events = client.get(path)
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "id: 1\nevent: segment" in events.text
    assert "id: 2\nevent: completed" in events.text and '"answerType": "unavailable"' in events.text
    resumed = client.get(path, headers={"Last-Event-ID": "1"}).text
    assert "event: segment" not in resumed and "event: completed" in resumed
    assert client.get(path, headers={"Last-Event-ID": "2"}).text == ""
    for cursor in ["-1", "3", "not-an-id"]:
        assert client.get(path, headers={"Last-Event-ID": cursor}).status_code == 422


def test_deletion_removes_turn_replay_and_creation_replay(client):
    cid = write(client, "POST", "/v1/conversations", {}, "create-key").json()["conversationId"]
    path = f"/v1/conversations/{cid}/turns"
    tid = write(client, "POST", path, {"text": "synthetic"}, "turn-key").json()["turnId"]
    deleted = write(client, "DELETE", f"/v1/conversations/{cid}", key="delete-key")
    assert deleted.status_code == 204 and deleted.content == b""
    assert write(client, "DELETE", f"/v1/conversations/{cid}", key="delete-key").status_code == 204
    assert client.get(f"/v1/turns/{tid}").status_code == 404
    assert client.get(f"/v1/turns/{tid}/events").status_code == 404
    assert write(client, "POST", path, {"text": "synthetic"}, "turn-key").status_code == 404
    replacement = write(client, "POST", "/v1/conversations", {}, "create-key").json()["conversationId"]
    assert replacement != cid


@pytest.mark.parametrize("body", [{"text": ""}, {"text": " "}, {"text": "x" * 2001}, {"text": 12}, {"text": "ok", "raw_private": "secret-marker"}])
def test_input_bounds_and_redacted_validation(client, body):
    cid = conversation(client)
    result = write(client, "POST", f"/v1/conversations/{cid}/turns", body)
    assert result.status_code == 422
    assert result.json() == {"error": {"code": "invalid_request"}}


def test_raw_body_limit_and_missing_write_key(client):
    result = client.post("/v1/conversations", content=b"x" * 8193)
    assert result.status_code == 413
    result = client.post("/v1/conversations", json={})
    assert result.status_code == 422
    assert result.json() == {"error": {"code": "invalid_request"}}


def test_synthetic_state_is_bounded_and_restart_isolated(client):
    client.app.state.store.max_conversations = 1
    conversation(client)
    assert write(client, "POST", "/v1/conversations", {}).status_code == 503
    with TestClient(create_app(Settings(demo_mode=True, demo_token=TOKEN))) as fresh:
        fresh.headers["X-Demo-Token"] = TOKEN
        assert fresh.get("/v1/rewards").json()["balance"] == 0


def test_full_replay_capacity_still_allows_deletion(client):
    client.app.state.store.max_replays = 2
    cid = conversation(client)
    tid = write(client, "POST", f"/v1/conversations/{cid}/turns", {"text": "synthetic"}).json()["turnId"]
    assert write(client, "POST", "/v1/conversations", {}).status_code == 503
    assert write(client, "DELETE", f"/v1/conversations/{cid}", key="capacity-delete").status_code == 204
    assert write(client, "DELETE", f"/v1/conversations/{cid}", key="capacity-delete").status_code == 204
    assert client.get(f"/v1/turns/{tid}").status_code == 404
    conversation(client)


def test_invalid_unicode_has_redacted_error(client):
    cid = conversation(client)
    result = client.post(f"/v1/conversations/{cid}/turns", content=b'{"text":"\\ud800"}',
                         headers={"Idempotency-Key": "unicode-key", "Content-Type": "application/json"})
    assert result.status_code == 422
    assert result.json() == {"error": {"code": "invalid_request"}}


def test_turn_capacity_preserves_existing_replay(client):
    client.app.state.store.max_turns = 1
    cid = conversation(client)
    path = f"/v1/conversations/{cid}/turns"
    first = write(client, "POST", path, {"text": "synthetic"}, "capacity-turn")
    assert first.status_code == 200
    assert write(client, "POST", path, {"text": "another"}).status_code == 503
    assert write(client, "POST", path, {"text": "synthetic"}, "capacity-turn").json() == first.json()


def test_cross_operation_key_reuse_conflicts(client):
    write(client, "POST", "/v1/conversations", {}, "shared-key")
    assert write(client, "POST", "/v1/lessons/demo-learning/complete", {}, "shared-key").status_code == 409
    assert client.get("/v1/rewards").json()["balance"] == 0


def test_openapi_errors_match_redacted_runtime_payload(client):
    from jsonschema import Draft202012Validator

    document = client.app.openapi()
    for path, methods in document["paths"].items():
        if not path.startswith("/v1/"):
            continue
        for operation in methods.values():
            schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorEnvelope"}
    response = client.post("/v1/conversations", json={})
    assert response.status_code == 422
    Draft202012Validator({"$ref": "#/components/schemas/ErrorEnvelope", "components": document["components"]}).validate(response.json())
    assert "HTTPValidationError" not in document["components"]["schemas"]


def test_looks_are_earned_from_the_ledger_and_never_go_negative(client):
    claim = "/v1/cosmetics/claim"
    # Nothing is owned on credit: the catalogue price is checked against the
    # ledger this process owns, not against anything the client sends.
    assert write(client, "POST", claim, {"cosmeticId": "sunset"}).status_code == 403
    assert write(client, "POST", claim, {"cosmeticId": "not-a-look"}).status_code == 404

    write(client, "POST", "/v1/lessons/demo-learning/complete", {})
    assert client.get("/v1/rewards").json()["balance"] == 5

    earned = write(client, "POST", claim, {"cosmeticId": "sunset"}).json()
    assert earned == {"cosmeticId": "sunset", "owned": True, "spent": 5, "balance": 0}
    # A second claim under a fresh key must not charge twice.
    assert write(client, "POST", claim, {"cosmeticId": "sunset"}).json()["spent"] == 0
    assert client.get("/v1/rewards").json()["balance"] == 0

    # Spending wrote to the ledger; completing the lesson again still earns
    # nothing, and a look that costs more than the balance stays locked.
    assert write(client, "POST", "/v1/lessons/demo-learning/complete", {}).json()["earned"] == 0
    assert write(client, "POST", claim, {"cosmeticId": "dune"}).status_code == 403
    assert client.get("/v1/rewards").json()["balance"] == 0


def test_equipment_follows_ownership(client):
    path = "/v1/equipped-cosmetics"
    assert write(client, "PUT", path, {"cosmeticId": "sunset"}).status_code == 403

    write(client, "POST", "/v1/lessons/demo-learning/complete", {})
    write(client, "POST", "/v1/cosmetics/claim", {"cosmeticId": "sunset"})
    assert write(client, "PUT", path, {"cosmeticId": "sunset"}).json() == {
        "cosmeticId": "sunset", "characterId": "robert"}

    items = {item["id"]: item for item in client.get("/v1/inventory").json()["items"]}
    assert items["sunset"] == {"id": "sunset", "characterId": "robert", "name": "Sunset Copper",
                               "description": "Warm copper, the colour of the room at dusk.",
                               "cost": 5, "owned": True, "equipped": True}
    assert items["default"]["equipped"] is False
    assert items["dune"]["owned"] is False


def test_published_contract_matches_the_routes_the_app_serves():
    # The app serves no /openapi.json, so contracts/openapi-v1.json is what
    # consumers build against. Hand-editing is how it drifts from the routes;
    # regenerate it with tools/export_contracts.py.
    from pathlib import Path
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from export_contracts import contract  # noqa: E402

    published = Path(__file__).resolve().parent.parent / "contracts" / "openapi-v1.json"
    assert json.loads(published.read_text(encoding="utf-8")) == json.loads(contract()), (
        "contracts/openapi-v1.json is stale; run python tools/export_contracts.py "
        "../comp-mobile/contracts/openapi-v1.json"
    )
