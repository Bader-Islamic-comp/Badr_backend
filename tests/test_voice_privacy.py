"""Voice privacy (release gate item A09, doc/governance/release-gate.md; ADR 0006).

What these tests hold for every route that takes a child's recording:
- Audio stays in memory: nothing is opened for writing, no temporary file is made, while a recording is handled.
- Nothing from a recording or a transcript reaches the logs, at any level, or any state the process keeps.
- A transcript is returned once and never kept, not even in the idempotency replay cache.
- Push-to-talk is one bounded request: one raw body of at most 1 MiB, with no streaming or socket route.
- Robert's rendered voice lives in memory only and goes with its conversation.
"""
import builtins
import dataclasses
import io
import logging
import os
import tempfile
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from speech_fake import DEMO_TOKEN, FakeSpeech, speech_app, wav

AUDIO_MARKER = b"CHILD-AUDIO-MARKER-7f3a"
TRANSCRIPT_MARKER = "رسالة الطفل السرية 7f3a"
AUDIO_PATHS = {"/v1/recitations/attempts", "/v1/speech/transcriptions",
               "/v1/games/dhikr/rounds/{round_id}/attempts"}


@pytest.fixture
def fake():
    value = FakeSpeech()
    value.transcript = {"status": "transcribed", "text": TRANSCRIPT_MARKER, "abstainReason": None, "language": "ar"}
    return value


@pytest.fixture
def client(fake):
    with TestClient(speech_app(fake)) as value:
        value.headers["X-Demo-Token"] = DEMO_TOKEN
        yield value


def _headers(**extra):
    return {"Content-Type": "audio/wav", "Idempotency-Key": str(uuid4()), **extra}


def _exercise_every_audio_route(client):
    recording = wav(AUDIO_MARKER)
    assert client.post("/v1/recitations/attempts", content=recording, headers=_headers(),
                       params={"itemId": "takbeer", "segment": 0, "attempt": 1}).status_code == 200
    assert client.post("/v1/recitations/attempts", content=recording, headers=_headers(),
                       params={"itemId": "morning-by-god", "segment": 0, "attempt": 2}).status_code == 200
    rid = client.post("/v1/games/dhikr/rounds", json={"dhikrId": "takbeer"},
                      headers={"Idempotency-Key": str(uuid4())}).json()["roundId"]
    assert client.post(f"/v1/games/dhikr/rounds/{rid}/attempts", content=recording,
                       headers=_headers()).status_code == 200
    transcript = client.post("/v1/speech/transcriptions", content=recording, headers={"Content-Type": "audio/wav"})
    assert transcript.json() == {"status": "transcribed", "text": TRANSCRIPT_MARKER}


class _Writes:
    """Records every attempt to open a file for writing or to make a temporary file."""

    def __init__(self, monkeypatch):
        self.calls = []
        real_open, real_os_open = builtins.open, os.open

        def guarded_open(file, mode="r", *args, **kwargs):
            if any(flag in str(mode) for flag in "wax+"):
                self.calls.append(("open", str(file), mode))
            return real_open(file, mode, *args, **kwargs)

        def guarded_os_open(path, flags, *args, **kwargs):
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
                self.calls.append(("os.open", str(path), flags))
            return real_os_open(path, flags, *args, **kwargs)

        def refuse(name):
            def temporary(*args, **kwargs):
                self.calls.append((name, args, kwargs))
                raise AssertionError(f"{name} called while handling audio")
            return temporary

        monkeypatch.setattr(builtins, "open", guarded_open)
        monkeypatch.setattr(io, "open", guarded_open)
        monkeypatch.setattr(os, "open", guarded_os_open)
        for name in ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile",
                     "TemporaryDirectory"):
            monkeypatch.setattr(tempfile, name, refuse(name))


def test_audio_is_never_written_to_disk(client, monkeypatch):
    writes = _Writes(monkeypatch)
    _exercise_every_audio_route(client)
    _cid, tid = _robert_turn(client)
    client.post(f"/v1/turns/{tid}/speech", headers={"Idempotency-Key": str(uuid4())})
    _settle(client, tid)
    assert client.get(f"/v1/turns/{tid}/speech/parts/0").status_code == 200
    assert writes.calls == []


def test_no_audio_or_transcript_reaches_the_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    _exercise_every_audio_route(client)
    logged = caplog.text + "".join(repr(record.args) + repr(record.__dict__) for record in caplog.records)
    assert AUDIO_MARKER.decode() not in logged and repr(AUDIO_MARKER) not in logged
    assert TRANSCRIPT_MARKER not in logged


def _holds(value, needle_text: str, needle_bytes: bytes, seen: set) -> bool:
    """Whether `value` or anything reachable from it holds the marker (dicts, sequences, objects, dataclasses)."""
    if id(value) in seen:
        return False
    seen.add(id(value))
    if isinstance(value, str):
        return needle_text in value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return needle_bytes in bytes(value)
    if isinstance(value, dict):
        return any(_holds(key, needle_text, needle_bytes, seen) or _holds(item, needle_text, needle_bytes, seen)
                   for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_holds(item, needle_text, needle_bytes, seen) for item in value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return any(_holds(getattr(value, field.name), needle_text, needle_bytes, seen)
                   for field in dataclasses.fields(value))
    if hasattr(value, "__dict__") and type(value).__module__.startswith(("companion_api", "speech_fake")):
        return _holds(vars(value), needle_text, needle_bytes, seen)
    return False


def test_no_audio_or_transcript_is_kept_anywhere_in_the_process_state(client):
    store = client.app.state.store
    replays, speech_replays = len(store.replays), len(store.speech_replays)
    _exercise_every_audio_route(client)
    # The three scored attempts and the round keep a replay each (outcome and counts only), in the speech replay
    # cache; the transcript none.
    assert (len(store.replays), len(store.speech_replays)) == (replays, speech_replays + 4)
    for state in (store, client.app.state.speech):
        assert not _holds(state, TRANSCRIPT_MARKER, AUDIO_MARKER, set())
        # Nor the recording decoded to text, nor the transcript encoded to bytes.
        assert not _holds(state, AUDIO_MARKER.decode(), TRANSCRIPT_MARKER.encode(), set())


def test_a_transcription_is_not_replayed_from_any_cache(client, fake):
    key = {"Idempotency-Key": "transcript-key-1"}
    for _ in range(2):
        response = client.post("/v1/speech/transcriptions", content=wav(AUDIO_MARKER),
                               headers={"Content-Type": "audio/wav", **key})
        assert response.json()["text"] == TRANSCRIPT_MARKER
    assert len(fake.calls("POST", "/v1/transcribe")) == 2
    store = client.app.state.store
    assert not _holds((store.replays, store.speech_replays), TRANSCRIPT_MARKER, b"\x00never", set())


def _routes(routes):
    """Every route, including those of included routers."""
    for route in routes:
        yield route
        inner = getattr(route, "original_router", None) or getattr(route, "router", None)
        yield from _routes(getattr(inner, "routes", []))


def test_push_to_talk_is_one_bounded_request(client):
    routes = list(_routes(client.app.routes))
    assert any(isinstance(route, APIRoute) and route.path == "/v1/recitations/attempts" for route in routes)
    assert not [route for route in routes if "WebSocket" in type(route).__name__]  # no open microphone channel
    paths = client.app.openapi()["paths"]
    assert {path: set(paths[path]) for path in AUDIO_PATHS} == {path: {"post"} for path in AUDIO_PATHS}
    for path in AUDIO_PATHS:
        assert set(paths[path]["post"]["requestBody"]["content"]) == {"audio/wav"}
    assert client.get("/v1/bootstrap").json()["features"]["speech"]["maxRecordingSeconds"] == 15
    over = wav(frames=(1_048_576 - 44) // 2 + 1)
    for path, params in [("/v1/recitations/attempts", {"itemId": "takbeer", "segment": 0, "attempt": 1}),
                         ("/v1/speech/transcriptions", None)]:
        response = client.post(path, content=over, params=params, headers=_headers())
        assert (response.status_code, response.json()) == (413, {"error": {"code": "request_too_large"}})
        # A body that streams in chunks is counted as it arrives and refused the same way.
        streamed = client.post(path, content=iter([over[:600_000], over[600_000:]]), params=params,
                               headers=_headers())
        assert streamed.status_code == 413


def test_the_recording_reaches_the_speech_service_once_as_raw_bytes(client, fake):
    recording = wav(AUDIO_MARKER)
    client.post("/v1/recitations/attempts", content=recording, headers=_headers(),
                params={"itemId": "takbeer", "segment": 0, "attempt": 1})
    assert [call[3] for call in fake.calls("POST", "/v1/dua-attempts")] == [len(recording)]


def _robert_turn(client):
    store = client.app.state.store
    cid = client.post("/v1/conversations", json={}, headers={"Idempotency-Key": str(uuid4())}).json()[
        "conversationId"]
    tid = str(uuid4())
    with store.lock:
        store.turns[tid] = {"conversationId": cid, "turnId": tid, "status": "completed", "answerType": "chat",
                            "text": "أهلًا، أنا روبرت.", "citations": [], "sources": [], "segments": []}
    return cid, tid


def _settle(client, tid):
    for _ in range(200):
        body = client.get(f"/v1/turns/{tid}/speech").json()
        if body["status"] != "pending":
            return body
    raise AssertionError("Robert's voice did not settle")


def test_robert_s_voice_is_memory_only_and_goes_with_its_conversation(client):
    cid, tid = _robert_turn(client)
    client.post(f"/v1/turns/{tid}/speech", headers={"Idempotency-Key": str(uuid4())})
    assert _settle(client, tid)["status"] == "ready"
    voice = client.app.state.speech.voice
    assert voice._jobs[tid].parts[0].text is None  # the sentence is let go once rendered
    client.delete(f"/v1/conversations/{cid}", headers={"Idempotency-Key": str(uuid4())})
    assert voice._jobs == {}
    assert client.get(f"/v1/turns/{tid}/speech/parts/0").status_code == 404
