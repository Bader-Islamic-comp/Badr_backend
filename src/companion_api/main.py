"""Local demo API factory. Run with one Uvicorn worker and access logs disabled."""
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4
import hmac
import json
import re

from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from . import content, schemas as s
from .config import Settings
from .rag.service import AnswerService, build_answer_service
from .schemas import WriteKey
from .speech import routes as speech_routes
from .speech.client import SpeechClient
from .speech.diacritize import Diacritizer
from .speech.preview import SpeechPreview
from .store import DemoStore, DomainError

EVENT_CURSOR = re.compile(r"^(0|[1-9][0-9]{0,3})$")
BODY_LIMIT = 8192


def error(status, code):
    return JSONResponse({"error": {"code": code}}, status_code=status)


def _audio_upload(scope) -> tuple[str | None, bool]:
    """(the speech switch the route needs, whether the body is declared `audio/wav`) for a POST; else (None, …)."""
    feature = speech_routes.audio_feature(scope["path"]) if scope["method"] == "POST" else None
    content_type = dict(scope["headers"]).get(b"content-type", b"").decode("latin-1")
    return feature, speech_routes.media_type(content_type) == speech_routes.AUDIO_TYPE


def body_limit(scope, audio_allowed: Callable[[dict, str], bool] | None = None) -> int:
    """8 KiB for every request, except a raw `audio/wav` POST to an audio upload route: 1 MiB, and only when
    `audio_allowed(scope, feature)` holds (the feature is on and the demo token is right), so nothing is
    buffered past 8 KiB before authentication."""
    feature, wav = _audio_upload(scope)
    if feature and wav and audio_allowed is not None and audio_allowed(scope, feature):
        return speech_routes.MAX_AUDIO_BYTES
    return BODY_LIMIT


def oversize(scope) -> JSONResponse:
    """413, except on an audio upload route sent anything but `audio/wav`: its type is refused first, 415."""
    feature, wav = _audio_upload(scope)
    if feature and not wav:
        return error(415, "unsupported_media_type")
    return error(413, "request_too_large")


class RequestBoundary:
    """Bound actual bytes, including chunked bodies, before JSON parsing. Bodies are held in memory only.

    Push-to-talk recordings (ADR 0006) may be one raw `audio/wav` body of up to 1 MiB on the three audio upload
    routes, when `audio_allowed` says the request may be read (`body_limit`); everything else keeps 8 KiB.
    """
    def __init__(self, app, audio_allowed: Callable[[dict, str], bool] | None = None):
        self.app = app
        self.audio_allowed = audio_allowed

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        correlation_id = str(uuid4()).encode()

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                message["headers"] += [(b"x-correlation-id", correlation_id), (b"cache-control", b"no-store")]
            await send(message)

        limit = body_limit(scope, self.audio_allowed)
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            return await oversize(scope)(scope, receive, guarded_send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await oversize(scope)(scope, receive, guarded_send)
            if not message.get("more_body", False):
                break

        async def buffered_receive():
            nonlocal body
            value = bytes(body)
            body.clear()
            return {"type": "http.request", "body": value, "more_body": False}

        await self.app(scope, buffered_receive, guarded_send)


def create_app(settings: Settings | None = None, answer_service: AnswerService | None = None, *,
               speech_client: SpeechClient | None = None, diacritizer: Diacritizer | None = None) -> FastAPI:
    """The API. Grounded answers run only with an injected service or `COMPANION_RAG_ENABLED=true`.

    Enabled answers fail closed at startup: a missing or altered release, a
    public endpoint, an unlisted model or a mismatched embedder stops the app
    here rather than degrading at request time. So does an enabled speech
    preview (`COMPANION_SPEECH_ENABLED=true`, ADR 0006) with a public address,
    no token or a malformed switch; its client and tashkeel model may be
    injected for tests.
    """
    settings = settings or Settings.from_environment()
    settings.require_demo()
    if settings.speech_enabled:
        settings.require_speech()
    if answer_service is None and settings.rag_enabled:
        answer_service = build_answer_service(settings)
    store = DemoStore(answer_service)
    speech = SpeechPreview(settings, store, client=speech_client, diacritizer=diacritizer,
                           generator=getattr(answer_service, "generator", None))

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            store.close()
            await speech.aclose()

    def audio_allowed(scope, feature: str) -> bool:
        """A recording may be read past 8 KiB only with its speech switch on and the right demo token, compared
        in constant time as `authenticate` does."""
        token = dict(scope["headers"]).get(b"x-demo-token", b"")
        return speech.switches.get(feature) is True and hmac.compare_digest(token, settings.demo_token.encode())

    app = FastAPI(title="Companion synthetic development API", version="0.1.0", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(RequestBoundary, audio_allowed=audio_allowed)
    app.state.store = store
    app.state.speech = speech

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exception):
        return error(422, "invalid_request")

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exception):
        return error(exception.status, exception.code)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exception):
        return error(exception.status_code, "not_found" if exception.status_code == 404 else "request_rejected")

    @app.get("/health/live")
    def health():
        return {"status": "ok"}

    def authenticate(x_demo_token: Annotated[str, Header()] = ""):
        if not hmac.compare_digest(x_demo_token.encode(), settings.demo_token.encode()):
            raise DomainError(401, "unauthorized")

    router = APIRouter(
        prefix="/v1",
        dependencies=[Depends(authenticate)],
        responses={status: {"model": s.ErrorEnvelope} for status in (401, 403, 404, 409, 413, 422, 503)},
    )

    @router.get("/bootstrap", response_model=s.Bootstrap)
    def bootstrap():
        drafts = answer_service is not None and answer_service.retriever.include_drafts
        return s.Bootstrap(features=s.Features(generativeAnswers=answer_service is not None,
                                               speech=s.SpeechFeatures(**speech.features())),
                           contentStatus="unreviewed_drafts" if drafts else "awaiting_review")

    @router.get("/lessons", response_model=s.LessonList)
    def lesson_list():
        return content.lessons()

    @router.post("/lessons/demo-learning/complete", response_model=s.Completion)
    def complete(body: s.EmptyRequest, key: WriteKey):
        return store.execute(key, "complete-lesson", body.model_dump(), store.complete_lesson)

    @router.get("/challenges/today", response_model=s.ChallengeList)
    def challenge_list():
        return content.challenges(store.completed_any_lesson)

    @router.get("/rewards", response_model=s.Rewards)
    def rewards():
        return {"balance": store.balance, "unit": "learning_stars"}

    @router.get("/inventory", response_model=s.Inventory)
    def inventory():
        return store.inventory()

    @router.post("/cosmetics/claim", response_model=s.Claimed)
    def claim(body: s.CosmeticRequest, key: WriteKey):
        return store.execute(key, "claim", body.model_dump(), lambda: store.claim(body.cosmeticId))

    @router.put("/equipped-cosmetics", response_model=s.Equipped)
    def equip(body: s.CosmeticRequest, key: WriteKey):
        return store.execute(key, "equip", body.model_dump(), lambda: store.equip(body.cosmeticId))

    @router.post("/conversations", response_model=s.ConversationCreated)
    def create_conversation(body: s.EmptyRequest, key: WriteKey):
        return store.execute(key, "create-conversation", body.model_dump(), store.create_conversation)

    @router.post("/conversations/{conversation_id}/turns", response_model=s.TurnCreated)
    def create_turn(conversation_id: UUID, body: s.TurnRequest, key: WriteKey):
        cid = str(conversation_id)
        return store.execute(key, "turn:" + cid, body.model_dump(), lambda: store.create_turn(cid, body.text), cid)

    @router.get("/turns/{turn_id}", response_model=s.Turn)
    def get_turn(turn_id: UUID):
        return store.get_turn(str(turn_id))

    @router.get("/turns/{turn_id}/events", response_class=Response,
                responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}})
    def turn_events(turn_id: UUID, last_event_id: Annotated[str, Header(alias="Last-Event-ID")] = "0"):
        if not EVENT_CURSOR.match(last_event_id):
            raise DomainError(422, "invalid_request")
        cursor = int(last_event_id)
        turn = store.turn_events(str(turn_id))
        headers = {"X-Accel-Buffering": "no"}
        if turn["status"] == "pending":
            # Nothing has been sent yet, so the only valid cursor is 0; the
            # client reconnects after the retry interval and asks again.
            if cursor != 0:
                raise DomainError(422, "invalid_request")
            return Response("retry: 1000\n\n", media_type="text/event-stream", headers=headers)
        # Verified complete sentences only; never token-by-token generation.
        segments = turn["segments"]
        if cursor > len(segments) + 1:
            raise DomainError(422, "invalid_request")
        events = [(number, "segment", segment) for number, segment in enumerate(segments, start=1)]
        events.append((len(segments) + 1, "completed", {"turnId": str(turn_id), "answerType": turn["answerType"]}))
        data = "".join(f"id: {identifier}\nevent: {name}\ndata: {json.dumps(payload)}\n\n"
                       for identifier, name, payload in events if identifier > cursor)
        return Response(data, media_type="text/event-stream", headers=headers)

    @router.delete("/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: UUID, key: WriteKey):
        cid = str(conversation_id)
        store.execute(key, "delete:" + cid, {}, lambda: store.delete_conversation(cid), deleting_id=cid)
        speech.drop_conversation(cid)  # Robert's voice for its turns goes with it
        return Response(status_code=204)

    speech_routes.register(router, speech, store)
    app.include_router(router)
    return app
