"""Robert's voice: an answer read aloud on request, part by part (ADR 0006, owner decision D-C).

`start` takes a completed turn of a spoken answer type, prepares its parts (`textprep.speakable_parts`) and
runs one asyncio task in the API process: for each part in order, the model adds tashkeel (`diacritize`), the
part is kept only when no letter changed (`arabic.same_letters`), and the speech service renders it
(`/v1/tts/render`, category `persona`). A part the check or a speech guard refuses is dropped; the app plays the
ready parts in index order as they arrive. One job renders at a time, because the speech service has one GPU.

Audio lives in this process's memory only: at most `MAX_TURNS` turns, each for `TTL_SECONDS`, dropped at once
when its conversation is deleted. Every call checks that the turn still exists (`turn_exists`), so a deletion
that races a request never leaves audio reachable. Jobs are touched on the event loop only. Nothing here is
logged; the sentence text is let go once its part is done.
"""
import asyncio
from dataclasses import dataclass, field
import time
from typing import Callable

from ..store import DomainError
from .arabic import same_letters
from .client import SpeechClient, SpeechError, SpeechRejected
from .diacritize import Diacritizer
from .textprep import speakable_parts

# conversation-policy answer types that are Robert's own words; never `safety` or `unavailable`.
SPOKEN_TYPES = frozenset({"chat", "grounded", "reviewed_answer", "abstained", "redirected"})
TTL_SECONDS = 15 * 60
MAX_TURNS = 16
# Why nothing will be spoken (`reason`, only with status `unavailable`).
NOT_SPOKEN = "answer_type_not_spoken"
NOTHING_TO_SPEAK = "nothing_to_speak"
SPEECH_UNAVAILABLE = "speech_unavailable"
NO_PART_READY = "no_part_ready"


@dataclass
class _Part:
    index: int
    text: str | None          # Robert's sentence until the part is rendered or dropped
    audio: bytes | None = None
    dropped: bool = False


@dataclass
class _Job:
    turn_id: str
    conversation_id: str
    created: float
    parts: list[_Part]
    done: bool = False
    reason: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def view(self) -> dict:
        parts = [{"index": part.index, "ready": part.audio is not None} for part in self.parts if not part.dropped]
        if not self.done:
            return {"status": "pending", "parts": parts, "reason": None}
        if any(part["ready"] for part in parts):
            return {"status": "ready", "parts": parts, "reason": None}
        return {"status": "unavailable", "parts": [], "reason": self.reason or NO_PART_READY}


class RobertVoice:
    def __init__(self, client: SpeechClient, diacritizer: Diacritizer, voice_id: str, *,
                 clock: Callable[[], float] = time.monotonic, ttl: float = TTL_SECONDS, max_turns: int = MAX_TURNS,
                 turn_exists: Callable[[str], bool] = lambda _turn_id: True):
        self.client, self.diacritizer, self.voice_id = client, diacritizer, voice_id
        self._clock, self.ttl, self.max_turns = clock, ttl, max_turns
        self._turn_exists = turn_exists
        self._jobs: dict[str, _Job] = {}
        self._render_lock: asyncio.Lock | None = None

    def _purge(self):
        now = self._clock()
        for turn_id in [key for key, job in self._jobs.items() if now - job.created >= self.ttl]:
            self._drop(turn_id)

    def _drop(self, turn_id: str):
        job = self._jobs.pop(turn_id, None)
        if job is not None and job.task is not None and not job.task.done():
            job.task.cancel()

    def _make_room(self):
        while len(self._jobs) >= self.max_turns:
            finished = next((key for key, job in self._jobs.items() if job.done), None)
            if finished is None:
                raise DomainError(503, "speech_busy")
            self._drop(finished)

    def _job(self, turn_id: str) -> _Job | None:
        """The turn's job; none once it expired or its turn is gone (the job is then dropped at once)."""
        self._purge()
        if not self._turn_exists(turn_id):
            self._drop(turn_id)
            raise DomainError(404, "not_found")
        return self._jobs.get(turn_id)

    def start(self, turn: dict) -> dict:
        """Starts reading `turn` aloud, or reports the job already running for it. Needs a running loop."""
        existing = self._job(turn["turnId"])
        if existing is not None and not (existing.done and existing.reason == SPEECH_UNAVAILABLE):
            return existing.view()
        if turn["status"] != "completed":
            raise DomainError(409, "turn_pending")
        self._drop(turn["turnId"])
        self._make_room()
        texts = speakable_parts(turn["text"]) if turn["answerType"] in SPOKEN_TYPES else []
        job = _Job(turn["turnId"], turn["conversationId"], self._clock(),
                   [_Part(index, text) for index, text in enumerate(texts)])
        self._jobs[job.turn_id] = job
        if not texts:
            job.done, job.reason = True, NOT_SPOKEN if turn["answerType"] not in SPOKEN_TYPES else NOTHING_TO_SPEAK
        else:
            job.task = asyncio.get_running_loop().create_task(self._run(job))
        return job.view()

    def status(self, turn_id: str) -> dict:
        job = self._job(turn_id)
        if job is None:
            raise DomainError(404, "not_found")
        return job.view()

    def part(self, turn_id: str, index: int) -> bytes:
        job = self._job(turn_id)
        if job is None:
            raise DomainError(404, "not_found")
        audio = next((part.audio for part in job.parts if part.index == index and part.audio is not None), None)
        if audio is None:
            raise DomainError(404, "audio_not_found")
        return audio

    def drop_conversation(self, conversation_id: str):
        for turn_id in [key for key, job in self._jobs.items() if job.conversation_id == conversation_id]:
            self._drop(turn_id)

    async def aclose(self):
        tasks = [job.task for job in self._jobs.values() if job.task is not None and not job.task.done()]
        self._jobs.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _current(self, job: _Job) -> bool:
        return self._jobs.get(job.turn_id) is job

    async def _run(self, job: _Job):
        if self._render_lock is None:
            self._render_lock = asyncio.Lock()
        try:
            async with self._render_lock:
                for part in job.parts:
                    if not self._current(job):
                        return  # deleted or expired while waiting: drop everything
                    if not await self._render(part):
                        job.reason = SPEECH_UNAVAILABLE
                        for rest in job.parts:
                            if rest.audio is None:
                                rest.dropped, rest.text = True, None
                        break
        except asyncio.CancelledError:
            raise
        except Exception:  # never surfaces content; the job just ends with what is ready
            job.reason = job.reason or SPEECH_UNAVAILABLE
        finally:
            for part in job.parts:
                part.text = None
                if part.audio is None:
                    part.dropped = True
            job.done = True

    async def _render(self, part: _Part) -> bool:
        """Renders one part, or drops it. False when the tashkeel model or the speech service is unavailable: the
        job then ends `speech_unavailable`, and a repeated request starts it again."""
        text, part.text = part.text, None
        try:
            diacritized = await asyncio.to_thread(self.diacritizer.diacritize, text)
        except Exception:  # an adapter that raises instead of returning None: the model is out all the same
            diacritized = None
        if diacritized is None:
            part.dropped = True
            return False
        if not same_letters(text, diacritized):
            part.dropped = True  # the model changed a letter (or said nothing): skip this part
            return True
        try:
            part.audio = await self.client.render(diacritized, self.voice_id)
        except SpeechRejected:
            part.dropped = True  # a guard refused it (religious text, too few marks): skip this part
        except SpeechError:
            part.dropped = True
            return False
        return True
