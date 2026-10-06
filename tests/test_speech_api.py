"""The speech preview's routes (ADR 0006) against a stand-in speech service (tests/speech_fake.py)."""
from datetime import datetime, timedelta, timezone
import math
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from companion_api.config import Settings
from companion_api.main import create_app
from companion_api.speech.client import SpeechClient
from companion_api.store import Grant
from speech_fake import (DEMO_TOKEN, ROBERT_WAV, SPEECH_TOKEN, SPEECH_URL, EchoDiacritizer, FakeSpeech, abstained,
                         scored, speech_app, speech_settings, wav)

ONE_MIB = 1_048_576


@pytest.fixture
def fake():
    return FakeSpeech()


def _client(app):
    client = TestClient(app)
    client.headers["X-Demo-Token"] = DEMO_TOKEN
    return client


@pytest.fixture
def client(fake):
    with _client(speech_app(fake)) as value:
        yield value


def key():
    return str(uuid4())


def send(client, path, audio=None, *, idempotency=True, content_type="audio/wav", params=None, **headers):
    if idempotency:
        headers.setdefault("Idempotency-Key", key())
    return client.post(path, content=wav() if audio is None else audio, params=params,
                       headers={"Content-Type": content_type, **headers})


def attempt(client, item="takbeer", segment=0, number=1, audio=None, **headers):
    return send(client, "/v1/recitations/attempts", audio,
                params={"itemId": item, "segment": segment, "attempt": number}, **headers)


def new_round(client, dhikr="takbeer", idempotency_key=None):
    response = client.post("/v1/games/dhikr/rounds", json={"dhikrId": dhikr},
                           headers={"Idempotency-Key": idempotency_key or key()})
    assert response.status_code == 200, response.text
    return response.json()


def play(client, round_id, audio=None, **headers):
    return send(client, f"/v1/games/dhikr/rounds/{round_id}/attempts", audio, **headers)


# Switches and startup ----------------------------------------------------------------------------------------

SPEECH_ENV = ("COMPANION_SPEECH_ENABLED", "COMPANION_SPEECH_URL", "COMPANION_SPEECH_TOKEN",
              "COMPANION_SPEECH_RECITATION", "COMPANION_SPEECH_VOICE_QUESTIONS", "COMPANION_SPEECH_ROBERT_VOICE",
              "COMPANION_ROBERT_VOICE_ID", "COMPANION_SPEECH_TIMEOUT_SECONDS", "COMPANION_SPEECH_TTS_TIMEOUT_SECONDS")


def test_everything_is_off_while_the_master_switch_is_unset(monkeypatch):
    for name in SPEECH_ENV + ("COMPANION_RAG_ENABLED",):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COMPANION_DEMO_MODE", "true")
    monkeypatch.setenv("COMPANION_DEMO_TOKEN", DEMO_TOKEN)
    settings = Settings.from_environment()
    assert settings.speech_enabled is False
    with _client(create_app(settings)) as client:
        assert client.get("/v1/bootstrap").json()["features"]["speech"] == {
            "preview": False, "recitation": False, "voiceQuestions": False, "robertVoice": False,
            "maxRecordingSeconds": 15}
        tid = str(uuid4())
        for method, path in [("GET", "/v1/adhkar"), ("GET", "/v1/duas"), ("GET", "/v1/games/dhikr"),
                             ("GET", "/v1/audio/adhkar/takbeer"), ("GET", "/v1/audio/feedback/all_clear_1"),
                             ("GET", f"/v1/turns/{tid}/speech")]:
            assert client.request(method, path).json() == {"error": {"code": "speech_disabled"}}, path
        assert attempt(client).json() == {"error": {"code": "speech_disabled"}}
        assert send(client, "/v1/speech/transcriptions", idempotency=False).status_code == 404
        assert client.post(f"/v1/turns/{tid}/speech", headers={"Idempotency-Key": key()}).status_code == 404


def test_the_environment_sets_every_switch(monkeypatch):
    for name in SPEECH_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COMPANION_SPEECH_ENABLED", "true")
    monkeypatch.setenv("COMPANION_SPEECH_URL", SPEECH_URL)
    monkeypatch.setenv("COMPANION_SPEECH_TOKEN", SPEECH_TOKEN)
    monkeypatch.setenv("COMPANION_SPEECH_VOICE_QUESTIONS", "false")
    settings = Settings.from_environment()
    assert (settings.speech_recitation, settings.speech_voice_questions, settings.speech_robert_voice) == (
        True, False, True)
    assert (settings.robert_voice_id, settings.speech_timeout_seconds, settings.speech_tts_timeout_seconds) == (
        "momen-dev", 30.0, 240.0)
    assert SPEECH_TOKEN not in repr(settings)
    monkeypatch.setenv("COMPANION_SPEECH_RECITATION", "off")
    assert Settings.from_environment().speech_recitation is None  # refused at startup, never read as on


def test_an_enabled_preview_fails_closed_naming_every_problem():
    settings = Settings(demo_mode=False, demo_token=DEMO_TOKEN, speech_enabled=True,
                        speech_url="http://8.8.8.8:8100", speech_token="short", speech_recitation=None,
                        robert_voice_id="Robert Voice", speech_timeout_seconds=math.nan,
                        speech_tts_timeout_seconds=5000)
    with pytest.raises(RuntimeError) as raised:
        settings.require_speech()
    message = str(raised.value)
    for name in ("COMPANION_DEMO_MODE", "COMPANION_SPEECH_URL", "COMPANION_SPEECH_TOKEN",
                 "COMPANION_SPEECH_RECITATION", "COMPANION_ROBERT_VOICE_ID", "COMPANION_SPEECH_TIMEOUT_SECONDS",
                 "COMPANION_SPEECH_TTS_TIMEOUT_SECONDS"):
        assert name in message, name
    assert "short" not in message


@pytest.mark.parametrize("url", ["", "http://8.8.8.8:8100", "http://speech.example.com:8100",
                                 "http://user:pw@127.0.0.1:8100", "http://127.0.0.1:8100?x=1", "ftp://127.0.0.1"])
def test_the_speech_service_must_be_private(url):
    with pytest.raises(RuntimeError, match="COMPANION_SPEECH_URL"):
        create_app(speech_settings(speech_url=url))
    with pytest.raises(RuntimeError, match="COMPANION_SPEECH_TOKEN"):
        create_app(speech_settings(speech_token=""))


def test_bootstrap_reports_the_preview_and_voice_stays_false(client):
    features = client.get("/v1/bootstrap").json()["features"]
    assert features["voice"] is False
    assert features["speech"] == {"preview": True, "recitation": True, "voiceQuestions": True,
                                  "robertVoice": True, "maxRecordingSeconds": 15}


def test_each_feature_has_its_own_kill_switch(fake):
    settings = speech_settings(speech_recitation=False, speech_voice_questions=False)
    with _client(speech_app(fake, settings=settings)) as client:
        speech = client.get("/v1/bootstrap").json()["features"]["speech"]
        assert (speech["recitation"], speech["voiceQuestions"], speech["robertVoice"]) == (False, False, True)
        assert attempt(client).json() == {"error": {"code": "speech_disabled"}}
        assert client.get("/v1/games/dhikr").status_code == 404
        assert send(client, "/v1/speech/transcriptions", idempotency=False).status_code == 404
        assert [item["practice"] for item in client.get("/v1/adhkar").json()["items"]] == [False] * 4
    assert not fake.calls("POST", "/v1/dua-attempts") and not fake.calls("POST", "/v1/transcribe")


def test_robert_voice_is_off_without_a_model_for_the_tashkeel(fake):
    client = SpeechClient(SPEECH_URL, SPEECH_TOKEN, transport=fake.transport)
    with _client(create_app(speech_settings(), speech_client=client)) as api:
        assert api.get("/v1/bootstrap").json()["features"]["speech"]["robertVoice"] is False
        assert api.get(f"/v1/turns/{uuid4()}/speech").json() == {"error": {"code": "speech_disabled"}}


# Request size and type -------------------------------------------------------------------------------------

def test_audio_routes_take_one_raw_wav_of_at_most_one_mib(client, fake):
    exactly = wav(frames=(ONE_MIB - 44) // 2)
    assert len(exactly) == ONE_MIB
    assert attempt(client, audio=exactly).status_code == 200
    over = attempt(client, audio=exactly + b"\x00")
    assert (over.status_code, over.json()) == (413, {"error": {"code": "request_too_large"}})
    assert send(client, "/v1/speech/transcriptions", exactly + b"\x00", idempotency=False).status_code == 413
    # Anything but audio/wav keeps the 8 KiB bound, and a small one is refused by type.
    assert attempt(client, audio=b"x" * 9000, **{"Content-Type": "audio/flac"}).status_code == 413
    small = send(client, "/v1/recitations/attempts", b"{}", content_type="application/json",
                 params={"itemId": "takbeer", "segment": 0, "attempt": 1})
    assert (small.status_code, small.json()) == (415, {"error": {"code": "unsupported_media_type"}})
    # The 1 MiB bound is for the audio routes only.
    assert client.post("/v1/conversations", content=wav(frames=5000),
                       headers={"Content-Type": "audio/wav", "Idempotency-Key": key()}).status_code == 413
    assert attempt(client, audio=b"RIFF" + b"\x00" * 60).json() == {"error": {"code": "invalid_request"}}
    assert attempt(client, audio=b"").status_code == 422
    assert len(fake.calls("POST", "/v1/dua-attempts")) == 1  # only the valid one reached the service


def test_a_chunked_recording_is_bounded_by_its_actual_bytes(client):
    def chunks():
        for _ in range(17):
            yield b"\x00" * 65536
    response = client.post("/v1/recitations/attempts", content=chunks(),
                           params={"itemId": "takbeer", "segment": 0, "attempt": 1},
                           headers={"Content-Type": "audio/wav", "Idempotency-Key": key()})
    assert response.status_code == 413


# Learn content ----------------------------------------------------------------------------------------------

def test_adhkar_list_the_four_with_audio_and_practice_from_the_service(client):
    data = client.get("/v1/adhkar").json()
    assert data["reviewStatus"] == "draft"
    assert [item["id"] for item in data["items"]] == ["takbeer", "tasbeeh", "tahmeed", "istighfar"]
    takbeer = data["items"][0]
    assert takbeer == {"id": "takbeer", "nameAr": "التكبير", "nameEn": "Takbeer", "transliteration": "Allahu akbar",
                       "text": "اللَّهُ أَكْبَرُ", "audio": True, "practice": True}
    assert [item["audio"] for item in data["items"]] == [True, False, False, False]
    assert all(item["practice"] for item in data["items"])


def test_learn_content_degrades_gracefully_without_the_service(client, fake):
    fake.down = True
    items = client.get("/v1/adhkar").json()["items"]
    assert len(items) == 4 and not any(item["audio"] or item["practice"] for item in items)
    duas = client.get("/v1/duas").json()["items"]
    assert len(duas) == 22 and not any(item["segments"] or item["audio"] for item in duas)
    assert not fake.calls("GET", "/v1/audio/recorded/dua-sleep")  # no probe per dua while the service is down


def test_practice_needs_stt_and_audio_needs_the_same_words(client, fake):
    fake.stt = False
    fake.adhkar_text["tahmeed"] = "الْحَمْدُ لِلَّهِ رَبِّ"
    fake.audio[("adhkar", "tahmeed")] = (wav(), "draft")
    items = {item["id"]: item for item in client.get("/v1/adhkar").json()["items"]}
    assert not any(item["practice"] for item in items.values())
    assert items["tahmeed"]["audio"] is False  # the recording would say other words than the ones shown


def test_duas_list_content_with_only_verified_segments(client, fake):
    fake.audio[("recorded", "dua-sleep")] = (wav(b"human"), "draft")
    data = client.get("/v1/duas").json()
    assert data["reviewStatus"] == "draft"
    items = {item["id"]: item for item in data["items"]}
    assert len(items) == 22
    assert [item["group"] for item in data["items"]].count("adhkar") == 7
    morning = items["morning-by-god"]
    assert morning["kind"] == "hadith_invocation" and morning["repeat"] == 1 and morning["occasions"] == ["morning"]
    assert morning["segments"] == [
        {"index": 0, "text": "اللهم بك أصبحنا، وبك أمسينا، وبك نحيا، وبك نموت، وإليك النشور"}]
    assert morning["childNote"] == "أبدأ صباحي بذكر الله."
    # "33" is two words to the speech service, so these segments are not the ones it scores: none offered.
    assert items["after-prayer-tasbih"]["segments"] == []
    # Quranic items never carry their text or segments here, even when the service has segments for them.
    assert items["dua-parents"]["kind"] == "quran_recitation" and items["dua-parents"]["segments"] == []
    assert items["dua-parents"]["title"] == "دعاء الرحمة للوالدين" and items["dua-parents"]["occasions"] == [
        "for_parents"]
    assert items["dua-sleep"]["audio"] == "recorded" and items["dua-wake"]["audio"] is None
    assert items["morning-evening-tasbih"]["repeat"] == 100


def test_a_dua_the_service_counts_differently_has_no_segments(client, fake, monkeypatch):
    import speech_fake
    monkeypatch.setitem(speech_fake.DUA_COUNTS, "dua-wake", [6, 2])
    assert {item["id"]: item for item in client.get("/v1/duas").json()["items"]}["dua-wake"]["segments"] == []


def test_audio_is_proxied_from_the_service(client, fake):
    response = client.get("/v1/audio/adhkar/takbeer")
    assert response.status_code == 200 and response.headers["content-type"] == "audio/wav"
    assert response.content == wav(b"takbeer") and response.headers["x-audio-status"] == "draft"
    assert client.get("/v1/audio/feedback/all_clear_1").content == wav(b"all-clear")
    for path in ["/v1/audio/adhkar/tasbeeh", "/v1/audio/adhkar/not-a-dhikr", "/v1/audio/duas/dua-sleep",
                 "/v1/audio/duas/not-a-dua", "/v1/audio/feedback/no_such_copy", "/v1/audio/feedback/UPPER"]:
        assert client.get(path).json() == {"error": {"code": "audio_not_found"}}, path
    assert client.get("/v1/audio/feedback/..%2F..%2Fsecret").status_code == 404
    assert not any("secret" in request[1] for request in fake.requests)
    fake.audio[("recorded", "dua-sleep")] = (wav(b"human"), "approved")
    recorded = client.get("/v1/audio/duas/dua-sleep")
    assert recorded.content == wav(b"human") and recorded.headers["x-audio-status"] == "approved"
    assert not any("not-a" in request[1] or "UPPER" in request[1] for request in fake.requests)
    fake.down = True
    assert client.get("/v1/audio/adhkar/takbeer").json() == {"error": {"code": "speech_unavailable"}}


# Recitation practice -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("result, number, outcome, words, show", [
    (scored("clear", "clear"), 1, "clear", [{"index": 0, "state": "clear"}, {"index": 1, "state": "clear"}], True),
    (scored("clear", "try_again", copy_id="mostly_clear"), 2, "try_again",
     [{"index": 0, "state": "clear"}, {"index": 1, "state": "try_again"}], True),
    (scored("unsure", "unsure", copy_id="mostly_clear"), 1, "try_again",
     [{"index": 0, "state": "unsure"}, {"index": 1, "state": "unsure"}], True),
    (scored("clear", "try_again", copy_id="mostly_clear"), 4, "try_again", [], False),   # after three attempts
    (abstained("audio_quality", "abstain_quality"), 1, "unsure", [], False),
    (abstained("low_confidence"), 2, "unsure", [], False),
])
def test_practice_outcomes(client, fake, result, number, outcome, words, show):
    fake.attempts = [result]
    data = attempt(client, number=number).json()
    assert (data["outcome"], data["words"], data["showWords"]) == (outcome, words, show)
    assert data["feedback"]["copyId"] == result["feedbackCopyId"]
    assert fake.calls("POST", "/v1/dua-attempts")[0][2] == {"duaId": "dhikr-takbeer", "version": "1", "segment": "0",
                                                           "attempt": str(number)}


def test_feedback_comes_from_the_service_only_when_it_is_gentle(client, fake):
    data = attempt(client).json()
    assert data["feedback"] == {"copyId": "all_clear_1", "text": "ما شاء الله، أحسنت!", "audio": True}
    fake.attempts = [scored("clear", "try_again", copy_id="bad_line")]
    assert attempt(client).json()["feedback"] == {"copyId": "try_again_first", "text": "لا بأس، جرّب مرة ثانية ببطء.",
                                                 "audio": False}
    fake.attempts = [abstained("off_script", copy_id=None)]
    assert attempt(client).json()["feedback"]["copyId"] == "abstain_generic"


def test_feedback_falls_back_without_the_copy_list(fake):
    fake.feedback_copy = False
    with _client(speech_app(fake)) as client:
        assert attempt(client).json()["feedback"] == {"copyId": "all_clear_1", "text": "ما شاء الله، أحسنت!",
                                                     "audio": False}


def test_practice_items_are_adhkar_or_duas_with_verified_segments(client, fake):
    assert attempt(client, "morning-by-god").status_code == 200
    assert fake.calls("POST", "/v1/dua-attempts")[-1][2]["duaId"] == "morning-by-god"
    for item, segment in [("takbeer", 1), ("morning-by-god", 1), ("after-prayer-tasbih", 0), ("dua-parents", 0),
                          ("no-such-dua", 0)]:
        assert attempt(client, item, segment).json() == {"error": {"code": "item_not_found"}}, item
    for params in [{"itemId": "takbeer", "segment": 0, "attempt": 0},
                   {"itemId": "takbeer", "segment": 0, "attempt": 11},
                   {"itemId": "Takbeer!", "segment": 0, "attempt": 1}, {"itemId": "takbeer", "attempt": 1}]:
        assert send(client, "/v1/recitations/attempts", params=params).status_code == 422, params
    missing = send(client, "/v1/recitations/attempts", idempotency=False,
                   params={"itemId": "takbeer", "segment": 0, "attempt": 1})
    assert missing.json() == {"error": {"code": "invalid_request"}}
    assert len(fake.calls("POST", "/v1/dua-attempts")) == 1


def test_a_practice_retry_replays_without_the_recording_reaching_the_service_again(client, fake):
    first = attempt(client, **{"Idempotency-Key": "practice-key-1"})
    fake.attempts = [scored("try_again", "try_again")]
    assert attempt(client, **{"Idempotency-Key": "practice-key-1"}).json() == first.json()
    assert len(fake.calls("POST", "/v1/dua-attempts")) == 1
    other = attempt(client, audio=wav(b"another recording"), **{"Idempotency-Key": "practice-key-1"})
    assert other.json() == {"error": {"code": "idempotency_conflict"}}


def test_a_full_queue_is_retried_twice_then_busy(client, fake):
    fake.queue_full = 2
    assert attempt(client).status_code == 200
    assert len(fake.calls("POST", "/v1/dua-attempts")) == 3
    fake.queue_full = 3
    busy = attempt(client, **{"Idempotency-Key": "busy-key-1"})
    assert (busy.status_code, busy.json()) == (503, {"error": {"code": "speech_busy"}})
    assert len(fake.calls("POST", "/v1/dua-attempts")) == 6
    # A failure is not cached: the same key runs again once the queue has room.
    assert attempt(client, **{"Idempotency-Key": "busy-key-1"}).status_code == 200


@pytest.mark.parametrize("break_it", ["down", "token"])
def test_an_outage_is_speech_unavailable(fake, break_it):
    if break_it == "down":
        fake.down = True
        app = speech_app(fake)
    else:  # a misconfigured token: the service answers 401
        app = create_app(speech_settings(), speech_client=SpeechClient(
            SPEECH_URL, "a-different-token-of-sufficient-length", transport=fake.transport, backoff=(0, 0)),
            diacritizer=EchoDiacritizer())
    with _client(app) as client:
        response = attempt(client)
        assert (response.status_code, response.json()) == (503, {"error": {"code": "speech_unavailable"}})
        rid = new_round(client)["roundId"]
        assert play(client, rid).json() == {"error": {"code": "speech_unavailable"}}
        assert client.get("/v1/games/dhikr").json()["items"][0]["practice"] is False


def test_a_changed_dua_version_is_read_again_once(client, fake):
    fake.stale_versions = 1
    assert attempt(client).status_code == 200
    fake.stale_versions = 2
    assert attempt(client).json() == {"error": {"code": "speech_unavailable"}}


# The dhikr game ------------------------------------------------------------------------------------------------

def test_the_game_lists_the_adhkar_and_its_star_rules(client):
    data = client.get("/v1/games/dhikr").json()
    assert (data["starsPerRound"], data["dailyStarCap"], data["starsToday"]) == (1, 10, 0)
    assert data["items"][0] == {"id": "takbeer", "nameAr": "التكبير", "nameEn": "Takbeer", "text": "اللَّهُ أَكْبَرُ",
                                "audio": True, "practice": True}


def test_a_clear_attempt_completes_the_round_with_one_star(client, fake):
    game_round = new_round(client, "tasbeeh")
    assert game_round == {"roundId": game_round["roundId"], "dhikrId": "tasbeeh", "attempts": 0,
                          "countedAttempts": 0, "complete": False, "starAwarded": False}
    rid = game_round["roundId"]
    done = play(client, rid, **{"Idempotency-Key": "round-attempt-1"})
    assert done.status_code == 200
    body = done.json()
    assert body["attempt"]["outcome"] == "clear" and body["balance"] == 1
    assert body["round"] == {"roundId": rid, "dhikrId": "tasbeeh", "attempts": 1, "countedAttempts": 1,
                             "complete": True, "starAwarded": True}
    assert fake.calls("POST", "/v1/dua-attempts")[0][2]["duaId"] == "dhikr-tasbeeh"
    assert client.app.state.store.ledger == (Grant(f"dhikr-game:{rid}", 1),)
    # The retry replays; a new attempt on a finished round is refused; no second star either way.
    assert play(client, rid, **{"Idempotency-Key": "round-attempt-1"}).json() == body
    assert play(client, rid).json() == {"error": {"code": "round_complete"}}
    assert client.get("/v1/rewards").json()["balance"] == 1
    assert client.get("/v1/games/dhikr").json()["starsToday"] == 1


def test_a_round_completes_after_three_counted_attempts(client, fake):
    fake.attempts = [scored("try_again", "clear", copy_id="mostly_clear"), abstained("audio_quality"),
                     abstained("off_script"), abstained("too_long"), abstained("service_unavailable"),
                     abstained("low_confidence"), scored("unsure", "clear", copy_id="mostly_clear")]
    rid = new_round(client)["roundId"]
    rounds = [play(client, rid).json()["round"] for _ in range(7)]
    assert [entry["countedAttempts"] for entry in rounds] == [1, 1, 1, 1, 1, 2, 3]
    assert [entry["complete"] for entry in rounds] == [False] * 6 + [True]
    assert rounds[-1]["attempts"] == 7 and rounds[-1]["starAwarded"] is True
    assert client.get("/v1/rewards").json()["balance"] == 1


def test_the_game_attempt_number_follows_the_round(client, fake):
    fake.attempts = [scored("try_again", "try_again", copy_id="mostly_clear")]
    rid = new_round(client)["roundId"]
    shown = [play(client, rid).json()["attempt"]["showWords"] for _ in range(3)]
    assert shown == [True, True, True]
    assert [call[2]["attempt"] for call in fake.calls("POST", "/v1/dua-attempts")] == ["1", "2", "3"]


def test_stars_stop_at_the_daily_cap_and_rounds_still_complete(client):
    game = client.app.state.speech.game
    today = datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc)
    game._now = lambda: today
    results = [play(client, new_round(client)["roundId"]).json() for _ in range(11)]
    assert [result["round"]["starAwarded"] for result in results] == [True] * 10 + [False]
    assert all(result["round"]["complete"] for result in results)
    assert results[-1]["balance"] == 10 and client.get("/v1/games/dhikr").json()["starsToday"] == 10
    today += timedelta(hours=2)  # a new UTC day
    assert play(client, new_round(client)["roundId"]).json()["round"]["starAwarded"] is True
    assert client.get("/v1/games/dhikr").json()["starsToday"] == 1
    assert client.get("/v1/rewards").json()["balance"] == 11


def test_rounds_are_idempotent_and_validated(client):
    first = new_round(client, idempotency_key="round-key-1")
    assert new_round(client, idempotency_key="round-key-1") == first
    assert client.post("/v1/games/dhikr/rounds", json={"dhikrId": "something-else"},
                       headers={"Idempotency-Key": key()}).json() == {"error": {"code": "invalid_request"}}
    assert play(client, str(uuid4())).json() == {"error": {"code": "round_not_found"}}
    assert play(client, "not-a-round").status_code == 422


def test_game_stars_unlock_a_look(client):
    for _ in range(5):
        play(client, new_round(client)["roundId"])
    claimed = client.post("/v1/cosmetics/claim", json={"cosmeticId": "sunset"}, headers={"Idempotency-Key": key()})
    assert claimed.json() == {"cosmeticId": "sunset", "owned": True, "spent": 5, "balance": 0}
    assert client.get("/v1/rewards").json()["balance"] == 0


# Voice questions ---------------------------------------------------------------------------------------------------

def test_a_transcription_is_trimmed_for_the_composer_and_never_kept(client, fake):
    store = client.app.state.store
    replays = len(store.replays)
    response = send(client, "/v1/speech/transcriptions", idempotency=False)
    assert response.json() == {"status": "transcribed", "text": "شو اسمك يا روبرت؟"}
    assert send(client, "/v1/speech/transcriptions", idempotency=False).json() == response.json()
    assert len(fake.calls("POST", "/v1/transcribe")) == 2  # never replayed from a cache
    assert len(store.replays) == replays
    assert "شو اسمك" not in repr(vars(store)) and "شو اسمك" not in repr(vars(client.app.state.speech))
    assert fake.calls("POST", "/v1/transcribe")[0][2] == {"language": "ar"}
    send(client, "/v1/speech/transcriptions", idempotency=False, params={"language": "en"})
    assert fake.calls("POST", "/v1/transcribe")[-1][2] == {"language": "en"}
    assert send(client, "/v1/speech/transcriptions", idempotency=False,
                params={"language": "fr"}).json() == {"error": {"code": "invalid_request"}}


@pytest.mark.parametrize("transcript, expected", [
    ({"status": "transcribed", "text": "ب" * 1500}, {"status": "transcribed", "text": "ب" * 1000}),
    ({"status": "transcribed", "text": "   "}, {"status": "unsure", "text": None}),
    ({"status": "abstained", "text": None, "abstainReason": "no_speech"}, {"status": "unsure", "text": None}),
    ({"status": "abstained", "text": "should not show", "abstainReason": "low_confidence"},
     {"status": "unsure", "text": None}),
])
def test_transcriptions_are_bounded_and_doubt_is_unsure(client, fake, transcript, expected):
    fake.transcript = transcript
    assert send(client, "/v1/speech/transcriptions", idempotency=False).json() == expected


def test_transcription_failures(client, fake):
    fake.queue_full = 3
    assert send(client, "/v1/speech/transcriptions", idempotency=False).json() == {"error": {"code": "speech_busy"}}
    fake.queue_full = 0
    fake.down = True
    assert send(client, "/v1/speech/transcriptions", idempotency=False).json() == {
        "error": {"code": "speech_unavailable"}}
    assert send(client, "/v1/speech/transcriptions", content_type="text/plain", audio=b"hello",
                idempotency=False).status_code == 415


# Robert's voice ------------------------------------------------------------------------------------------------------

ANSWER = ("أهلًا! أنا روبرت، رفيقك في التعلم. قال إبراهيم لأبيه: «يا أبت». "
          "This sentence is English. نتعلم معًا كل يوم شيئًا جديدًا [1].")


def add_turn(client, text=ANSWER, answer_type="chat", status="completed", conversation_id=None):
    store = client.app.state.store
    cid = conversation_id or client.post("/v1/conversations", json={},
                                         headers={"Idempotency-Key": key()}).json()["conversationId"]
    tid = str(uuid4())
    with store.lock:
        store.turns[tid] = {"conversationId": cid, "turnId": tid, "status": status, "answerType": answer_type,
                            "text": text, "citations": [], "sources": [], "segments": []}
    return cid, tid


def speak(client, tid):
    return client.post(f"/v1/turns/{tid}/speech", headers={"Idempotency-Key": key()})


def settle(client, tid, attempts=200):
    for _ in range(attempts):
        body = client.get(f"/v1/turns/{tid}/speech").json()
        if body["status"] != "pending":
            return body
    raise AssertionError("Robert's voice did not settle")


def test_robert_reads_his_own_arabic_sentences_in_order(client, fake):
    _cid, tid = add_turn(client)
    started = speak(client, tid)
    assert started.status_code == 202 and started.json()["status"] in {"pending", "ready"}
    body = settle(client, tid)
    assert body == {"status": "ready", "parts": [{"index": 0, "ready": True}], "reason": None}
    # The quoted sentence and the English one are not spoken; the citation marker is gone.
    assert len(fake.rendered) == 1
    spoken = fake.rendered[0]
    assert "يا أبت" not in spoken and "[1]" not in spoken and "This" not in spoken
    assert spoken.replace("\u064e", "") == "أهلًا! أنا روبرت، رفيقك في التعلم. نتعلم معًا كل يوم شيئًا جديدًا."
    part = client.get(f"/v1/turns/{tid}/speech/parts/0")
    assert part.status_code == 200 and part.content == ROBERT_WAV and part.headers["content-type"] == "audio/wav"
    assert client.get(f"/v1/turns/{tid}/speech/parts/1").json() == {"error": {"code": "audio_not_found"}}
    # A second request reports the same job and renders nothing new.
    assert speak(client, tid).json() == body and len(fake.rendered) == 1


def test_parts_are_rendered_one_by_one_in_order(client, fake):
    numbers = ["واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة"]
    sentences = [f"هذه جملة رقم {number} من كلام روبرت الطويل جدًا " + "وفيها كلمات كثيرة تملأ المساحة " * 3 + "."
                 for number in numbers]
    _cid, tid = add_turn(client, " ".join(sentences))
    speak(client, tid)
    body = settle(client, tid)
    assert [part["index"] for part in body["parts"]] == list(range(6))  # at most six parts
    assert all(len(text.replace("\u064e", "")) <= 140 for text in fake.rendered)
    assert [text.replace("\u064e", "")[:16] for text in fake.rendered] == [
        sentence[:16] for sentence in sentences[:6]]


@pytest.mark.parametrize("answer_type", ["safety", "unavailable"])
def test_safety_and_unavailable_replies_are_never_spoken(client, fake, answer_type):
    _cid, tid = add_turn(client, answer_type=answer_type)
    response = speak(client, tid)
    assert response.status_code == 202
    assert response.json() == {"status": "unavailable", "parts": [], "reason": "answer_type_not_spoken"}
    assert not fake.rendered


@pytest.mark.parametrize("answer_type", ["chat", "grounded", "reviewed_answer", "abstained", "redirected"])
def test_robert_speaks_every_answer_type_of_his_own(client, answer_type):
    _cid, tid = add_turn(client, "سؤال جميل، لنتعلم معًا.", answer_type=answer_type)
    speak(client, tid)
    assert settle(client, tid)["status"] == "ready"


def test_a_pending_or_unknown_turn(client):
    _cid, tid = add_turn(client, status="pending")
    assert speak(client, tid).json() == {"error": {"code": "turn_pending"}}
    assert speak(client, str(uuid4())).json() == {"error": {"code": "not_found"}}
    assert client.get(f"/v1/turns/{uuid4()}/speech").json() == {"error": {"code": "not_found"}}
    assert client.post(f"/v1/turns/{uuid4()}/speech").status_code == 422  # Idempotency-Key required


def test_nothing_arabic_to_say(client, fake):
    _cid, tid = add_turn(client, "Only English here. «كلام مقتبس».")
    assert speak(client, tid).json() == {"status": "unavailable", "parts": [], "reason": "nothing_to_speak"}


def test_a_changed_letter_drops_the_part(fake):
    with _client(speech_app(fake, diacritizer=EchoDiacritizer(broken=True))) as client:
        _cid, tid = add_turn(client)
        speak(client, tid)
        assert settle(client, tid) == {"status": "unavailable", "parts": [], "reason": "no_part_ready"}
    assert not fake.rendered


def test_a_guard_refusal_drops_only_that_part(client, fake):
    fake.reject = ("ر\u064eف\u064eي\u064eق\u064e",)  # «رفيق» as the echo diacritizes it
    # Part 0 is the first sentence and the second; part 1 repeats the second.
    text = "أنا روبرت رفيقك في التعلم اليوم وكل يوم معك دائمًا. " + (
        "نتعلم معًا شيئًا جديدًا ومفيدًا وجميلًا كل يوم بإذن الله تعالى. " * 2)
    _cid, tid = add_turn(client, text)
    speak(client, tid)
    body = settle(client, tid)
    assert body["status"] == "ready" and [part["index"] for part in body["parts"]] == [1]
    assert client.get(f"/v1/turns/{tid}/speech/parts/0").json() == {"error": {"code": "audio_not_found"}}


def test_a_speech_outage_is_unavailable_and_a_new_request_retries(client, fake):
    fake.tts = False
    _cid, tid = add_turn(client)
    speak(client, tid)
    assert settle(client, tid) == {"status": "unavailable", "parts": [], "reason": "speech_unavailable"}
    fake.tts = True
    speak(client, tid)
    assert settle(client, tid)["status"] == "ready"


def test_deleting_the_conversation_drops_robert_s_voice(client):
    cid, tid = add_turn(client)
    speak(client, tid)
    assert settle(client, tid)["status"] == "ready"
    assert client.delete(f"/v1/conversations/{cid}", headers={"Idempotency-Key": key()}).status_code == 204
    assert client.get(f"/v1/turns/{tid}/speech").json() == {"error": {"code": "not_found"}}
    assert client.get(f"/v1/turns/{tid}/speech/parts/0").json() == {"error": {"code": "not_found"}}
    assert client.app.state.speech.voice._jobs == {}


def test_robert_s_voice_expires_and_is_bounded(client):
    voice = client.app.state.speech.voice
    now = [1000.0]
    voice._clock = lambda: now[0]
    _cid, tid = add_turn(client)
    speak(client, tid)
    settle(client, tid)
    now[0] += 15 * 60 - 1
    assert client.get(f"/v1/turns/{tid}/speech").json()["status"] == "ready"
    now[0] += 1
    assert client.get(f"/v1/turns/{tid}/speech").json() == {"error": {"code": "not_found"}}
    turns = [add_turn(client)[1] for _ in range(17)]
    for turn in turns:
        speak(client, turn)
        settle(client, turn)
    assert len(voice._jobs) == 16 and turns[0] not in voice._jobs and turns[-1] in voice._jobs
