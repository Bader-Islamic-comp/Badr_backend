"""The speech preview's `/v1` routes (ADR 0006), on the app's authenticated router.

Every route answers 404 `speech_disabled` while its switch is off. Recordings arrive as one raw `audio/wav`
body of at most 1 MiB (`RequestBoundary`), are read into memory, passed to the speech service and dropped with
the request: never written, logged or cached. Writes that carry a recording keep a replay of their result,
which holds no audio and no transcript; a transcription keeps nothing at all.
"""
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response

from ..schemas import ErrorEnvelope, WriteKey
from ..store import DemoStore, DomainError
from . import adhkar, schemas as ss
from .client import SpeechBusy, SpeechError, SpeechTooLarge
from .preview import SpeechPreview, audio_digest

AUDIO_TYPE = "audio/wav"
MAX_AUDIO_BYTES = 1_048_576
MAX_TRANSCRIPT_CHARS = 1000
AUDIO_ROUTES = r"/v1/(?:recitations/attempts|speech/transcriptions|games/dhikr/rounds/[^/]+/attempts)"
_WAV = {"type": "string", "format": "binary"}
AUDIO_BODY = {"requestBody": {"required": True, "content": {AUDIO_TYPE: {"schema": _WAV}}}}
AUDIO_ERRORS = {415: {"model": ErrorEnvelope}}
WAV_RESPONSE = {200: {"description": "WAV audio, from memory", "content": {AUDIO_TYPE: {"schema": _WAV}}}}
ItemId = Annotated[str, Query(alias="itemId", pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


def media_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


@contextmanager
def speech_errors():
    """A speech failure as the API's fixed codes: never the service's own detail."""
    try:
        yield
    except SpeechBusy:
        raise DomainError(503, "speech_busy") from None
    except SpeechTooLarge:
        raise DomainError(413, "request_too_large") from None
    except SpeechError:
        raise DomainError(503, "speech_unavailable") from None


async def recording(request: Request) -> bytes:
    """The request's WAV body, in memory. Anything else is 415; an empty or non-RIFF/WAVE body is 422."""
    if media_type(request.headers.get("content-type")) != AUDIO_TYPE:
        raise DomainError(415, "unsupported_media_type")
    audio = await request.body()
    if len(audio) > MAX_AUDIO_BYTES:
        raise DomainError(413, "request_too_large")
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise DomainError(422, "invalid_request")
    return audio


def transcription(data: dict) -> dict:
    """The service's `TranscribeResponse` for the composer: trimmed text, or `unsure` with none."""
    text = data.get("text") if data.get("status") == "transcribed" else None
    if isinstance(text, str):
        text = text.strip()[:MAX_TRANSCRIPT_CHARS].strip()
        if text:
            return {"status": "transcribed", "text": text}
    return {"status": "unsure", "text": None}


def register(router: APIRouter, preview: SpeechPreview, store: DemoStore):
    def wav(audio: bytes, status: str | None = None) -> Response:
        headers = {"X-Audio-Status": status} if status else None
        return Response(audio, media_type=AUDIO_TYPE, headers=headers)

    async def proxied(kind: str, audio_id: str) -> Response:
        with speech_errors():
            audio, status = await preview.audio(kind, audio_id)
        return wav(audio, status)

    # Learn content -----------------------------------------------------------------------------------------

    @router.get("/adhkar", response_model=ss.AdhkarList)
    async def adhkar_list():
        preview.require()
        return {"items": await preview.adhkar(), "reviewStatus": adhkar.REVIEW_STATUS}

    @router.get("/duas", response_model=ss.DuaList)
    async def dua_list():
        preview.require()
        return await preview.duas()

    @router.get("/audio/adhkar/{audio_id}", response_class=Response, responses=WAV_RESPONSE)
    async def adhkar_audio(audio_id: str):
        preview.require()
        if audio_id not in adhkar.BY_ID:
            raise DomainError(404, "audio_not_found")
        return await proxied("adhkar", audio_id)

    @router.get("/audio/duas/{audio_id}", response_class=Response, responses=WAV_RESPONSE)
    async def dua_audio(audio_id: str):
        preview.require()
        if preview.catalogue.get(audio_id) is None:
            raise DomainError(404, "audio_not_found")
        return await proxied("recorded", audio_id)

    @router.get("/audio/feedback/{copy_id}", response_class=Response, responses=WAV_RESPONSE)
    async def feedback_audio(copy_id: str):
        preview.require()
        return await proxied("copy", copy_id)

    # Practice (no stars) ---------------------------------------------------------------------------------

    @router.post("/recitations/attempts", response_model=ss.Attempt, openapi_extra=AUDIO_BODY,
                 responses=AUDIO_ERRORS)
    async def recitation_attempt(request: Request, key: WriteKey, item_id: ItemId,
                                 segment: Annotated[int, Query(ge=0, le=63)],
                                 attempt: Annotated[int, Query(ge=1, le=10)]):
        preview.require("recitation")
        audio = await recording(request)
        payload = {"itemId": item_id, "segment": segment, "attempt": attempt, "audio": audio_digest(audio)}
        reservation = store.begin(key, "recitation-attempt", payload)
        if reservation.result is not None:
            return reservation.result
        try:
            with speech_errors():
                dua_id = await preview.resolve(item_id, segment)
                _result, body = await preview.recite(dua_id, segment, attempt, audio)
        except BaseException:
            store.abandon(reservation)
            raise
        store.finish(reservation, body)
        return body

    # The dhikr game (stars) --------------------------------------------------------------------------------

    @router.get("/games/dhikr", response_model=ss.DhikrGame)
    async def dhikr_game():
        preview.require("recitation")
        items = [{key: item[key] for key in ("id", "nameAr", "nameEn", "text", "audio", "practice")}
                 for item in await preview.adhkar()]
        return {"items": items, "starsPerRound": 1, "dailyStarCap": 10, "starsToday": preview.game.stars_today()}

    @router.post("/games/dhikr/rounds", response_model=ss.Round)
    def new_round(body: ss.RoundRequest, key: WriteKey):
        preview.require("recitation")
        return store.execute(key, "dhikr-round", body.model_dump(), lambda: preview.game.create(body.dhikrId))

    @router.post("/games/dhikr/rounds/{round_id}/attempts", response_model=ss.RoundAttempt,
                 openapi_extra=AUDIO_BODY, responses=AUDIO_ERRORS)
    async def round_attempt(round_id: UUID, request: Request, key: WriteKey):
        preview.require("recitation")
        audio = await recording(request)
        rid = str(round_id)
        reservation = store.begin(key, "dhikr-attempt", {"roundId": rid, "audio": audio_digest(audio)})
        if reservation.result is not None:
            return reservation.result
        try:
            dhikr_id, number = preview.game.next_attempt(rid)
            with speech_errors():
                result, attempt_body = await preview.recite(adhkar.dua_id(dhikr_id), 0, number, audio)
            game_round = preview.game.record(rid, result)
            body = {"attempt": attempt_body, "round": game_round, "balance": store.balance}
        except BaseException:
            store.abandon(reservation)
            raise
        store.finish(reservation, body)
        return body

    # Voice questions: a transcript for the composer, kept nowhere --------------------------------------------

    @router.post("/speech/transcriptions", response_model=ss.Transcription, openapi_extra=AUDIO_BODY,
                 responses=AUDIO_ERRORS)
    async def transcribe(request: Request, language: Annotated[Literal["ar", "en"], Query()] = "ar"):
        # Deliberately not idempotent: a replay cache would have to keep the transcript.
        preview.require("voiceQuestions")
        audio = await recording(request)
        with speech_errors():
            data = await preview.client.transcribe(audio, language)
        del audio
        return transcription(data)

    # Robert's voice ------------------------------------------------------------------------------------------

    @router.post("/turns/{turn_id}/speech", status_code=202, response_model=ss.RobertSpeech)
    async def start_speech(turn_id: UUID, key: WriteKey):
        # Idempotent by turn: a second request reports the job the first one started.
        preview.require("robertVoice")
        return preview.voice.start(store.spoken_turn(str(turn_id)))

    @router.get("/turns/{turn_id}/speech", response_model=ss.RobertSpeech)
    async def speech_status(turn_id: UUID):
        preview.require("robertVoice")
        return preview.voice.status(str(turn_id))

    @router.get("/turns/{turn_id}/speech/parts/{index}", response_class=Response, responses=WAV_RESPONSE)
    async def speech_part(turn_id: UUID, index: Annotated[int, Path(ge=0, le=5)]):
        preview.require("robertVoice")
        return wav(preview.voice.part(str(turn_id), index))
