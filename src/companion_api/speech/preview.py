"""The speech preview as one object per app: its switches, the speech client and what reads from it (ADR 0006).

Learn content degrades gracefully: when the speech service cannot be reached, the adhkar and duas are still
listed, with no audio, no practice and no segments. Practice, transcription and Robert's voice need the service
and answer 503 `speech_unavailable` (or `speech_busy`) without it.
"""
import asyncio
from datetime import datetime
from hashlib import sha256
from typing import Callable

from ..config import Settings
from ..store import DemoStore, DomainError
from . import adhkar, recitation
from .arabic import letters
from .child_copy import FALLBACK_FEEDBACK, is_gentle
from .client import AUDIO_ID, SpeechClient, SpeechConflict, SpeechError, SpeechNotFound, SpeechUnavailable
from .diacritize import Diacritizer, LlmDiacritizer
from .duas import DuaCatalogue
from .game import DhikrGame
from .robert_voice import RobertVoice
from .textprep import recited_phrases

FEATURES = ("recitation", "voiceQuestions", "robertVoice")
MAX_RECORDING_SECONDS = 15


def _speech_duas(data: dict) -> dict[str, tuple[str, list[int]]]:
    """The service's `/v1/duas` as {id: (version, word count per segment in index order)}."""
    found = {}
    try:
        for item in data["items"]:
            segments = sorted(item["segments"], key=lambda segment: segment["index"])
            if [segment["index"] for segment in segments] != list(range(len(segments))):
                continue
            found[str(item["id"])] = (str(item["version"]), [int(segment["wordCount"]) for segment in segments])
    except (KeyError, TypeError, ValueError):
        raise SpeechUnavailable("bad_response") from None
    return found


class SpeechPreview:
    def __init__(self, settings: Settings, store: DemoStore, *, client: SpeechClient | None = None,
                 diacritizer: Diacritizer | None = None, generator=None, catalogue: DuaCatalogue | None = None,
                 now: Callable[[], datetime] | None = None):
        self.enabled = settings.speech_enabled
        self.store = store
        self.client = client
        if self.enabled and client is None:
            self.client = SpeechClient(settings.speech_url, settings.speech_token,
                                       timeout=settings.speech_timeout_seconds,
                                       tts_timeout=settings.speech_tts_timeout_seconds)
        self.switches = {"recitation": self.enabled and settings.speech_recitation is True,
                         "voiceQuestions": self.enabled and settings.speech_voice_questions is True,
                         "robertVoice": self.enabled and settings.speech_robert_voice is True}
        self.catalogue = catalogue or DuaCatalogue()
        self.game = DhikrGame(store, now) if now else DhikrGame(store)
        # Robert's voice needs a model for the tashkeel: the answer model's adapter, so it is on only with
        # grounded answers on (`COMPANION_RAG_ENABLED`, whose settings `require_rag` has checked) or an injected one.
        if diacritizer is None and generator is not None:
            diacritizer = LlmDiacritizer(generator)
        self.voice = None
        if self.switches["robertVoice"] and diacritizer is not None:
            # Never spoken, quoted or not: the package's duas (and their clauses) and the four adhkar.
            recited = recited_phrases([*self.catalogue.recited_texts(), *(entry["text"] for entry in adhkar.ADHKAR)])
            self.voice = RobertVoice(self.client, diacritizer, settings.robert_voice_id, turn_exists=store.has_turn,
                                     recited=recited)
        self.switches["robertVoice"] = self.voice is not None
        self._recorded: tuple[float, frozenset[str]] | None = None

    # Switches --------------------------------------------------------------------------------------------

    def features(self) -> dict:
        """The bootstrap's `features.speech`. It never waits on the speech service: voice questions also need the
        service's transcription on, read from its cached capabilities when there are any (else the switch alone)."""
        switches = dict(self.switches)
        if switches["voiceQuestions"]:
            capabilities = self.client.cached("/v1/capabilities")
            if capabilities is not None:
                switches["voiceQuestions"] = capabilities.get("transcribeEnabled") is True
        return {"preview": self.enabled, **{name: switches[name] for name in FEATURES},
                "maxRecordingSeconds": MAX_RECORDING_SECONDS}

    def require(self, feature: str | None = None):
        if not self.enabled or (feature is not None and not self.switches[feature]):
            raise DomainError(404, "speech_disabled")

    async def aclose(self):
        if self.voice is not None:
            await self.voice.aclose()
        if self.client is not None:
            await self.client.aclose()

    def drop_conversation(self, conversation_id: str):
        if self.voice is not None:
            self.voice.drop_conversation(conversation_id)

    # Learn content ---------------------------------------------------------------------------------------

    async def _duas_or_empty(self) -> dict[str, tuple[str, list[int]]]:
        try:
            return _speech_duas(await self.client.duas())
        except SpeechError:
            return {}

    async def _practice_ready(self) -> bool:
        if not self.switches["recitation"]:
            return False
        try:
            capabilities = await self.client.capabilities()
        except SpeechError:
            return False
        return capabilities.get("sttEnabled") is True and capabilities.get("sttAvailable") is True

    async def adhkar(self) -> list[dict]:
        """The four adhkar with `audio` and `practice` read from the speech service (cached for 60 s)."""
        audio = {}
        try:
            listing = await self.client.adhkar()
            for item in listing.get("items") or []:
                entry = adhkar.BY_ID.get(item.get("id")) if isinstance(item, dict) else None
                # The recording must say the words shown: same letters as the backend's text.
                if entry and isinstance(item.get("textDiacritized"), str) and \
                        letters(item["textDiacritized"]) == letters(entry["text"]):
                    audio[entry["id"]] = item.get("audioAvailable") is True
        except SpeechError:
            pass
        practice = {}
        if await self._practice_ready():
            speech = await self._duas_or_empty()
            for entry in adhkar.ADHKAR:
                found = speech.get(adhkar.dua_id(entry["id"]))
                practice[entry["id"]] = found is not None and found[1] == [len(letters(entry["text"]).split())]
        return [{**entry, "audio": audio.get(entry["id"], False), "practice": practice.get(entry["id"], False)}
                for entry in adhkar.ADHKAR]

    async def _recorded_ids(self, ids: list[str]) -> frozenset[str]:
        """Duas with a human recording on the service, probed by status line; cached like the lists."""
        now = asyncio.get_running_loop().time()
        if self._recorded is not None and now - self._recorded[0] < 60:
            return self._recorded[1]
        found = await asyncio.gather(*(self.client.has_audio("recorded", dua_id) for dua_id in ids))
        recorded = frozenset(dua_id for dua_id, present in zip(ids, found) if present)
        self._recorded = (now, recorded)
        return recorded

    async def duas(self) -> dict:
        items = self.catalogue.items()
        speech = await self._duas_or_empty()
        # An unreachable service has no recordings to offer: do not wait on one probe per dua as well.
        recorded = await self._recorded_ids([item.id for item in items]) if speech else frozenset()
        return {"items": [{"id": item.id, "group": item.group, "kind": item.kind, "title": item.title,
                           "childNote": item.child_note, "repeat": item.repeat, "occasions": list(item.occasions),
                           "audio": "recorded" if item.id in recorded else None,
                           "segments": [{"index": index, "text": text} for index, text in enumerate(
                               item.verified_segments(speech.get(item.id, (None, None))[1]))]}
                          for item in items],
                "reviewStatus": self.catalogue.status}

    async def audio(self, kind: str, audio_id: str) -> tuple[bytes, str | None]:
        """`kind` is the speech service's (`adhkar`, `recorded`, `copy`); unknown ids are 404 `audio_not_found`."""
        if not AUDIO_ID.fullmatch(audio_id):
            raise DomainError(404, "audio_not_found")
        try:
            return await self.client.audio(kind, audio_id)
        except SpeechNotFound:
            raise DomainError(404, "audio_not_found") from None

    # Practice ---------------------------------------------------------------------------------------------

    async def resolve(self, item_id: str, segment: int) -> str:
        """The speech service's dua id for a practice item: an adhkar id (segment 0) or a dua with segments."""
        if item_id in adhkar.BY_ID:
            if segment != 0:
                raise DomainError(404, "item_not_found")
            return adhkar.dua_id(item_id)
        dua = self.catalogue.get(item_id)
        if dua is None or dua.kind != "hadith_invocation":
            raise DomainError(404, "item_not_found")
        speech = _speech_duas(await self.client.duas())
        if segment >= len(dua.verified_segments(speech.get(item_id, (None, None))[1])):
            raise DomainError(404, "item_not_found")
        return item_id

    async def _feedback(self, copy_id: str | None, outcome: str) -> dict:
        fallback_id, fallback_text = FALLBACK_FEEDBACK[outcome]
        try:
            listing = {item.get("id"): item for item in (await self.client.feedback_copy()).get("items") or []
                       if isinstance(item, dict)}
        except SpeechError:
            listing = {}
        entry = listing.get(copy_id) if copy_id and AUDIO_ID.fullmatch(copy_id) else None
        if entry and isinstance(entry.get("text"), str) and is_gentle(entry["text"]):
            return {"copyId": copy_id, "text": entry["text"], "audio": entry.get("audioAvailable") is True}
        own = listing.get(fallback_id) or {}
        return {"copyId": fallback_id, "text": fallback_text,
                "audio": own.get("audioAvailable") is True and own.get("text") == fallback_text}

    async def recite(self, dua_id: str, segment: int, attempt: int, audio: bytes) -> tuple[recitation.Recitation, dict]:
        """Scores one recording; the bytes are only passed on. Returns the result and its API body."""
        for retry in (True, False):
            speech = _speech_duas(await self.client.duas())
            if dua_id not in speech:
                raise DomainError(404, "item_not_found")
            try:
                data = await self.client.attempt(dua_id, speech[dua_id][0], segment, attempt, audio)
                break
            except SpeechConflict:
                self.client.forget("/v1/duas")  # the version moved: read it again, once
                if not retry:
                    raise SpeechUnavailable("dua_version_mismatch") from None
            except SpeechNotFound:
                raise DomainError(404, "item_not_found") from None
        result = recitation.read_attempt(data)
        feedback = await self._feedback(result.copy_id, result.outcome)
        return result, recitation.response(result, attempt, feedback)


def audio_digest(audio: bytes) -> str:
    """The recording's place in a write fingerprint: the store keeps only a keyed digest of it, never the bytes."""
    return sha256(audio).hexdigest()
