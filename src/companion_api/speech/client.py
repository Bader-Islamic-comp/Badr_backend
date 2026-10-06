"""The client for the team's speech service, Dua-a_stt (`contracts/speech-v1.openapi.json` there), ADR 0006.

The service must be on this machine or a private network (`require_private_endpoint`), and every call carries
its token (`X-Speech-Token`). What is sent: one push-to-talk recording as raw WAV bytes with the dua id, segment
and attempt number, or the transcription language; Robert's own diacritized sentences for rendering. Never a
name, a profile, a conversation or the child's typed text.

Nothing here logs or keeps a request or response body. Audio passes through and is dropped with the request;
the small JSON lists (capabilities, duas, adhkar, feedback copy) are cached for at most 60 seconds because
they hold no child data. A failed list lookup is not tried again for 15 seconds, and a service that cannot be
reached at all fails every list for that long, so a Learn page answers at once instead of waiting on each list
in turn. Every failure is a `SpeechError` with a fixed code, never content: a service that cannot be reached,
answers 5xx, 401 or something unexpected is `SpeechUnavailable`; a full queue is retried twice after a short wait
and then is `SpeechBusy`.
"""
import asyncio
import json
import re
import time
from typing import Any, Awaitable, Callable

import httpx

from ..rag.endpoints import require_private_endpoint

AUDIO_TYPE = "audio/wav"
CACHE_SECONDS = 60.0
NEGATIVE_CACHE_SECONDS = 15.0      # a failed list lookup is not tried again sooner
_UNREACHABLE = "*"                 # the negative-cache key for a service that does not answer at all
LIST_TIMEOUT = 10.0                # the lists and the recording probe: Learn pages degrade fast without the service
BUSY_BACKOFF = (0.3, 0.6)          # two retries after a full queue, then speech_busy
MAX_JSON_BYTES = 256 * 1024
MAX_AUDIO_BYTES = 8 * 1024 * 1024  # a rendered sentence or a recorded dua; far above either
AUDIO_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_CODE = re.compile(r"^[a-z0-9_]{1,64}$")


class SpeechError(Exception):
    """A speech-service failure. Carries a fixed code only, never request or response content."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SpeechUnavailable(SpeechError):
    """Unreachable, timed out, misconfigured or answered something unexpected."""


class SpeechBusy(SpeechError):
    """The service's queue stayed full after the retries."""


class SpeechNotFound(SpeechError):
    """404: an unknown dua or audio file, or a route the service has switched off."""


class SpeechRejected(SpeechError):
    """400: a TTS guard refused the text (the code is the guard's reason)."""


class SpeechConflict(SpeechError):
    """409: the dua version changed since it was read."""


class SpeechTooLarge(SpeechError):
    """413: the recording is over the service's limit."""


def _code(body: bytes) -> str:
    """The service's error code: `{"detail": {"error": code}}`, or `{"error": code}` from its catch-all."""
    try:
        data = json.loads(body)
    except ValueError:
        return ""
    detail = data.get("detail", data) if isinstance(data, dict) else None
    code = detail.get("error") if isinstance(detail, dict) else None
    return code if isinstance(code, str) and _CODE.fullmatch(code) else ""


async def _read(response: httpx.Response, limit: int) -> bytes:
    chunks, total = [], 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise SpeechUnavailable("response_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


class SpeechClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0, tts_timeout: float = 240.0,
                 transport: httpx.AsyncBaseTransport | None = None, cache_seconds: float = CACHE_SECONDS,
                 clock: Callable[[], float] = time.monotonic, backoff: tuple[float, ...] = BUSY_BACKOFF,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 negative_seconds: float = NEGATIVE_CACHE_SECONDS):
        self.base_url = require_private_endpoint(base_url)
        self._token = token
        self.timeout, self.tts_timeout = timeout, tts_timeout
        self.list_timeout = min(timeout, LIST_TIMEOUT)
        self._transport = transport
        self._cache_seconds, self._clock = cache_seconds, clock
        self._backoff, self._sleep = backoff, sleep
        self._http: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._negative_seconds = negative_seconds
        self._failed: dict[str, tuple[float, SpeechError]] = {}

    def __repr__(self):
        return f"SpeechClient({self.base_url!r})"

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            # trust_env=False: HTTP_PROXY and the like must never route the token or a recording through a
            # proxy; the service is called directly at the private address `require_private_endpoint` checked.
            self._http = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self._transport,
                                           follow_redirects=False, trust_env=False,
                                           headers={"X-Speech-Token": self._token})
        return self._http

    async def aclose(self):
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _call(self, method: str, path: str, *, limit: int = MAX_JSON_BYTES, timeout: float | None = None,
                    **request) -> tuple[bytes, httpx.Headers]:
        """One request: the body on 200, else the matching `SpeechError`."""
        try:
            async with self._client().stream(method, path, timeout=timeout or self.timeout, **request) as response:
                if response.status_code != 200:
                    body = await _read(response, MAX_JSON_BYTES)
                    raise self._error(response.status_code, _code(body))
                return await _read(response, limit), response.headers
        except httpx.HTTPError as exception:
            raise SpeechUnavailable(f"unreachable_{type(exception).__name__}") from None

    @staticmethod
    def _error(status: int, code: str) -> SpeechError:
        if status == 503 and code == "speech_queue_full":
            return SpeechBusy(code)
        if status == 404:
            return SpeechNotFound(code or "not_found")
        if status == 400:
            return SpeechRejected(code or "rejected")
        if status == 409:
            return SpeechConflict(code or "conflict")
        if status == 413:
            return SpeechTooLarge(code or "audio_too_large")
        return SpeechUnavailable(f"http_{status}")

    async def _retrying(self, call: Callable[[], Awaitable[Any]]) -> Any:
        """Retries a full queue after each `backoff` wait, then gives up with `SpeechBusy`."""
        for wait in (*self._backoff, None):
            try:
                return await call()
            except SpeechBusy:
                if wait is None:
                    raise
                await self._sleep(wait)

    async def _json(self, method: str, path: str, **request) -> dict:
        body, _headers = await self._call(method, path, **request)
        try:
            data = json.loads(body)
        except ValueError:
            raise SpeechUnavailable("bad_response") from None
        if not isinstance(data, dict):
            raise SpeechUnavailable("bad_response")
        return data

    async def _cached(self, path: str) -> dict:
        now = self._clock()
        hit = self._cache.get(path)
        if hit is not None and now - hit[0] < self._cache_seconds:
            return hit[1]
        for key in (path, _UNREACHABLE):
            failed = self._failed.get(key)
            if failed is not None and now - failed[0] < self._negative_seconds:
                raise type(failed[1])(failed[1].code)
        try:
            data = await self._json("GET", path, timeout=self.list_timeout)
        except SpeechError as error:
            # No answer at all fails every list for a while; any other failure (an older service's 404) only this one.
            self._failed[_UNREACHABLE if error.code.startswith("unreachable_") else path] = (self._clock(), error)
            raise
        self._failed.pop(path, None)
        self._failed.pop(_UNREACHABLE, None)
        self._cache[path] = (now, data)
        return data

    def cached(self, path: str) -> dict | None:
        """A list's cached answer while it is fresh, else None. Never a request: for the bootstrap."""
        hit = self._cache.get(path)
        return hit[1] if hit is not None and self._clock() - hit[0] < self._cache_seconds else None

    def forget(self, path: str):
        """Drops one cached list, e.g. `/v1/duas` after a version conflict."""
        self._cache.pop(path, None)
        self._failed.pop(path, None)

    # The lists: no child data, cached ---------------------------------------------------------------------

    async def capabilities(self) -> dict:
        return await self._cached("/v1/capabilities")

    async def duas(self) -> dict:
        return await self._cached("/v1/duas")

    async def adhkar(self) -> dict:
        return await self._cached("/v1/adhkar")

    async def feedback_copy(self) -> dict:
        return await self._cached("/v1/feedback-copy")

    # Child audio: in memory for this call only, never cached --------------------------------------------

    async def attempt(self, dua_id: str, version: str, segment: int, attempt: int, audio: bytes) -> dict:
        params = {"duaId": dua_id, "version": version, "segment": segment, "attempt": attempt}
        return await self._retrying(lambda: self._json(
            "POST", "/v1/dua-attempts", params=params, content=audio, headers={"Content-Type": AUDIO_TYPE}))

    async def transcribe(self, audio: bytes, language: str) -> dict:
        return await self._retrying(lambda: self._json(
            "POST", "/v1/transcribe", params={"language": language}, content=audio,
            headers={"Content-Type": AUDIO_TYPE}))

    # Robert's voice and recorded audio -------------------------------------------------------------------

    async def render(self, text_diacritized: str, voice_id: str) -> bytes:
        """Robert's own sentence as WAV (`category: persona`); a guard refusal is `SpeechRejected`."""
        payload = {"textDiacritized": text_diacritized, "voiceId": voice_id, "category": "persona"}

        async def call():
            body, _headers = await self._call("POST", "/v1/tts/render", json=payload, limit=MAX_AUDIO_BYTES,
                                              timeout=self.tts_timeout)
            return body
        return await self._retrying(call)

    async def audio(self, kind: str, audio_id: str) -> tuple[bytes, str | None]:
        """A listed file's WAV bytes and its `X-Audio-Status` (`draft` or `approved`)."""
        if not AUDIO_ID.fullmatch(audio_id):
            raise SpeechNotFound("audio_not_found")
        body, headers = await self._call("GET", f"/v1/audio/{kind}/{audio_id}", limit=MAX_AUDIO_BYTES)
        status = headers.get("x-audio-status")
        return body, status if status in ("draft", "approved") else None

    async def has_audio(self, kind: str, audio_id: str) -> bool:
        """Whether the service lists a file, read from the status line alone (the body is never downloaded)."""
        if not AUDIO_ID.fullmatch(audio_id):
            return False
        try:
            async with self._client().stream("GET", f"/v1/audio/{kind}/{audio_id}",
                                             timeout=self.list_timeout) as response:
                return response.status_code == 200
        except httpx.HTTPError:
            return False
