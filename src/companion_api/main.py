"""Local demo API factory. Run with one Uvicorn worker and access logs disabled."""
from typing import Annotated
from uuid import UUID, uuid4
import hmac
import json

from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from . import content, schemas as s
from .config import Settings
from .store import DemoStore, DomainError

WriteKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[\x21-\x7e]+$")]


def error(status, code):
    return JSONResponse({"error": {"code": code}}, status_code=status)


class RequestBoundary:
    """Bound actual bytes, including chunked bodies, before JSON parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        correlation_id = str(uuid4()).encode()

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                message["headers"] += [(b"x-correlation-id", correlation_id), (b"cache-control", b"no-store")]
            await send(message)

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 8192:
                return await error(413, "request_too_large")(scope, receive, guarded_send)
            if not message.get("more_body", False):
                break

        async def buffered_receive():
            nonlocal body
            value = bytes(body)
            body.clear()
            return {"type": "http.request", "body": value, "more_body": False}

        await self.app(scope, buffered_receive, guarded_send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    settings.require_demo()
    app = FastAPI(title="Companion synthetic development API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestBoundary)
    store = DemoStore()
    app.state.store = store

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
        return s.Bootstrap()

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
        if last_event_id not in {"0", "1", "2"}:
            raise DomainError(422, "invalid_request")
        turn = store.get_turn(str(turn_id))
        # Complete fixed semantic response only; never token-by-token generation.
        events = [(1, "segment", {"text": turn["text"], "citations": []}),
                  (2, "completed", {"turnId": str(turn_id)})]
        data = "".join(f"id: {identifier}\nevent: {name}\ndata: {json.dumps(payload)}\n\n"
                       for identifier, name, payload in events if identifier > int(last_event_id))
        return Response(data, media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @router.delete("/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: UUID, key: WriteKey):
        cid = str(conversation_id)
        store.execute(key, "delete:" + cid, {}, lambda: store.delete_conversation(cid), deleting_id=cid)
        return Response(status_code=204)

    app.include_router(router)
    return app
