"""A stand-in for the team's speech service (Dua-a_stt), as `contracts/speech-v1.openapi.json` there describes it.

It answers through `httpx.MockTransport`, so the backend's real `SpeechClient` is exercised end to end. It
records the shape of each request (method, path, query, body length), never the body itself.
"""
from dataclasses import dataclass, field
import functools
import json
import struct
from types import SimpleNamespace
from uuid import uuid4

import httpx

from companion_api.config import Settings
from companion_api.corpusprep import competition
from companion_api.main import create_app
from companion_api.rag.chunking import chunk_documents
from companion_api.rag.corpus import parse_document
from companion_api.rag.service import AnswerService
from companion_api.speech import duas
from companion_api.speech.client import SpeechClient

DEMO_TOKEN = "synthetic-operator-token-for-tests"
SPEECH_TOKEN = "speech-service-token-for-tests-0123"
SPEECH_URL = "http://127.0.0.1:8100"


def wav(payload: bytes = b"", frames: int = 1600) -> bytes:
    """A PCM16 mono 16 kHz WAV: a valid header, `frames` silent samples, then `payload` in the data chunk."""
    data = b"\x00\x00" * frames + payload
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    return header + fmt + b"data" + struct.pack("<I", len(data)) + data


ROBERT_WAV = wav(b"robert-rendered-part")
ADHKAR_TEXT = {"takbeer": "اللَّهُ أَكْبَرُ", "tasbeeh": "سُبْحَانَ اللَّهِ", "tahmeed": "الْحَمْدُ لِلَّهِ",
               "istighfar": "أَسْتَغْفِرُ اللَّهَ"}
# Word counts per segment as the service's export script makes them (it spells numbers out: "33" is two words).
DUA_COUNTS = {"morning-by-god": [11], "evening-by-god": [9], "morning-evening-tasbih": [3],
              "after-prayer-istighfar": [2], "after-prayer-salam": [9], "after-prayer-tasbih": [10, 5, 8, 9],
              "dua-sleep": [4], "dua-wake": [8], "dua-before-food": [2], "dua-bathroom": [7],
              "dua-mosque-enter": [5], "dua-mosque-exit": [5], "dua-sneezing": [2], "dua-parents": [9]}
FEEDBACK = {"all_clear_1": "ما شاء الله، أحسنت!", "mostly_clear": "أحسنت، جرّب الكلمات المحددة مرة ثانية.",
            "try_again_first": "لا بأس، جرّب مرة ثانية ببطء.", "abstain_generic": "خلّينا نجرّب مرة ثانية.",
            "abstain_quality": "ما سمعتك منيح. جرّب تقرّب من المايكروفون.",
            "bad_line": "هذا غلط، حاول مرة ثانية."}


def scored(*states: str, copy_id: str = "all_clear_1") -> dict:
    return {"status": "scored", "abstainReason": None, "feedbackCopyId": copy_id,
            "words": [{"index": index, "state": state, "confidence": "high"} for index, state in enumerate(states)]}


def abstained(reason: str, copy_id: str = "abstain_generic") -> dict:
    return {"status": "abstained", "abstainReason": reason, "feedbackCopyId": copy_id, "words": []}


@dataclass
class FakeSpeech:
    down: bool = False
    queue_full: int = 0                  # how many 503 speech_queue_full answers to give before succeeding
    attempts: list = field(default_factory=lambda: [scored("clear", "clear")])  # the next results, last repeats
    transcript: dict = field(default_factory=lambda: {"status": "transcribed", "text": "  شو اسمك يا روبرت؟  ",
                                                      "abstainReason": None, "language": "ar"})
    stt: bool = True
    tts: bool = True
    transcribe: bool = True              # DUA_SPEECH_TRANSCRIBE_ENABLED: /v1/transcribe answers 404 without it
    version: str = "1"
    stale_versions: int = 0              # how many 409 dua_version_mismatch answers to give first
    reject: tuple = ()                   # rendered texts containing one of these are refused by a guard
    adhkar_text: dict = field(default_factory=lambda: dict(ADHKAR_TEXT))
    feedback_copy: bool = True           # False: an older service without /v1/feedback-copy
    audio: dict = field(default_factory=lambda: {("adhkar", "takbeer"): (wav(b"takbeer"), "draft"),
                                                 ("copy", "all_clear_1"): (wav(b"all-clear"), "draft")})
    requests: list = field(default_factory=list)
    rendered: list = field(default_factory=list)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    @staticmethod
    def _error(status: int, code: str) -> httpx.Response:
        return httpx.Response(status, json={"detail": {"error": code}})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, dict(request.url.params)
        self.requests.append((request.method, path, params, len(request.content)))
        if self.down:
            raise httpx.ConnectError("speech service down")
        if request.headers.get("x-speech-token") != SPEECH_TOKEN:
            return self._error(401, "unauthorized")
        route = (request.method, path)
        if route == ("GET", "/v1/capabilities"):
            return httpx.Response(200, json={"profile": "dev", "device": "cpu", "sttEnabled": self.stt,
                                             "sttAvailable": self.stt, "ttsEnabled": self.tts,
                                             "ttsAvailable": self.tts, "ttsDirectEnabled": self.tts,
                                             "ttsLicenseRecorded": False, "transcribeEnabled": self.transcribe,
                                             "adhkarTtsStatus": "draft"})
        if route == ("GET", "/v1/duas"):
            counts = {**DUA_COUNTS, **{f"dhikr-{key}": [2] for key in ADHKAR_TEXT}}
            return httpx.Response(200, json={"items": [
                {"id": key, "version": self.version,
                 "segments": [{"index": index, "wordCount": count} for index, count in enumerate(value)]}
                for key, value in counts.items()]})
        if route == ("GET", "/v1/adhkar"):
            return httpx.Response(200, json={"status": "draft", "items": [
                {"id": key, "textDiacritized": text, "duaId": f"dhikr-{key}", "segment": 0,
                 "audioAvailable": ("adhkar", key) in self.audio, "audioStatus": "draft", "wordTimestamps": []}
                for key, text in self.adhkar_text.items()]})
        if route == ("GET", "/v1/feedback-copy") and self.feedback_copy:
            return httpx.Response(200, json={"version": 1, "items": [
                {"id": key, "text": text, "audioAvailable": ("copy", key) in self.audio,
                 "audioStatus": "draft" if ("copy", key) in self.audio else None} for key, text in FEEDBACK.items()]})
        if request.method == "GET" and path.startswith("/v1/audio/"):
            _empty, _v1, _audio, kind, audio_id = path.split("/")
            if (kind, audio_id) not in self.audio:
                return self._error(404, "audio_not_found")
            body, status = self.audio[(kind, audio_id)]
            return httpx.Response(200, content=body, headers={"Content-Type": "audio/wav", "X-Audio-Status": status})
        if route == ("POST", "/v1/transcribe") and not self.transcribe:
            return httpx.Response(404, json={"detail": "Not Found"})
        if route in {("POST", "/v1/dua-attempts"), ("POST", "/v1/transcribe")}:
            if request.headers.get("content-type") != "audio/wav":
                return self._error(415, "unsupported_content_type")
            if len(request.content) > 1_048_576:
                return self._error(413, "audio_too_large")
            if self.queue_full:
                self.queue_full -= 1
                return self._error(503, "speech_queue_full")
            if path == "/v1/transcribe":
                return httpx.Response(200, json={**self.transcript, "modelVersions": {"stt": "fake"},
                                                 "timingsMs": {"decode": 1, "stt": 1, "total": 2}})
            if self.stale_versions:
                self.stale_versions -= 1
                return self._error(409, "dua_version_mismatch")
            if params.get("version") != self.version:
                return self._error(409, "dua_version_mismatch")
            result = self.attempts.pop(0) if len(self.attempts) > 1 else self.attempts[0]
            return httpx.Response(200, json={"attemptId": str(uuid4()), "duaId": params["duaId"],
                                             "duaVersion": self.version, "segment": int(params["segment"]),
                                             "feedbackAudioRef": None, "feedbackAudioStatus": None,
                                             "modelVersions": {"stt": "fake", "scoring": "fake"},
                                             "timingsMs": {"decode": 1, "stt": 1, "total": 2}, **result})
        if route == ("POST", "/v1/tts/render"):
            if not self.tts:
                return httpx.Response(404, json={"detail": "Not Found"})
            payload = json.loads(request.content)
            assert payload["category"] == "persona" and payload["voiceId"]
            if any(word in payload["textDiacritized"] for word in self.reject):
                return httpx.Response(400, json={"detail": {"error": "dua_registry_match", "detail": "x"}})
            self.rendered.append(payload["textDiacritized"])
            return httpx.Response(200, content=ROBERT_WAV, headers={"Content-Type": "audio/wav"})
        return httpx.Response(404, json={"detail": "Not Found"})

    def calls(self, method: str, path: str) -> list:
        return [request for request in self.requests if request[:2] == (method, path)]


class EchoDiacritizer:
    """Adds a fatha after every Arabic letter: tashkeel that changes no letter. `broken` adds a letter instead."""

    def __init__(self, broken: bool = False):
        self.broken, self.calls = broken, 0

    def diacritize(self, text: str) -> str:
        self.calls += 1
        if self.broken:
            return text + "ا"
        return "".join(char + "\u064e" if "\u0621" <= char <= "\u064a" else char for char in text)


def speech_settings(**overrides) -> Settings:
    values = {"demo_mode": True, "demo_token": DEMO_TOKEN, "speech_enabled": True, "speech_url": SPEECH_URL,
              "speech_token": SPEECH_TOKEN}
    return Settings(**{**values, **overrides})


def speech_app(fake: FakeSpeech, *, diacritizer=None, settings: Settings | None = None, answer_service=None):
    client = SpeechClient(SPEECH_URL, SPEECH_TOKEN, transport=fake.transport, backoff=(0, 0))
    return create_app(settings or speech_settings(), answer_service, speech_client=client,
                      diacritizer=diacritizer if diacritizer is not None else EchoDiacritizer())


def curated_reply(question: str):
    """The curated route's real reply (`AnswerService._curated`) over the competition package's hadith duas, built
    into chunks as a release builds them. Quranic items are left out: they need the mushaf, and their ayat are
    quoted in ﴿…﴾, which textprep drops anyway."""
    content = json.loads(duas.CONTENT.read_text(encoding="utf-8"))
    for group in duas.GROUPS:
        content[group] = [item for item in content[group] if item.get("kind", "hadith_invocation") == "hadith_invocation"]
    entry = {"publisher": "test publisher", "license": "test licence", "sha256": "a" * 64}
    chunks = chunk_documents(parse_document(document, document["id"] + ".json")[0]
                             for document in competition.documents(content, entry, {}))
    service = SimpleNamespace(age_band="7-9", provenance={}, retriever=SimpleNamespace(eligible=lambda **_where: chunks))
    service._result = functools.partial(AnswerService._result, service)
    return AnswerService._curated(service, question, "ar")


class CuratedAnswers:
    """An answer service whose every reply is `result`, through the store's fixed-reply path (`route`)."""
    retriever = SimpleNamespace(include_drafts=True)

    def __init__(self, result):
        self.result = result

    def route(self, _text):
        return self.result
