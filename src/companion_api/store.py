"""Bounded single-process synthetic state; replace with PostgreSQL before real use.

With grounded answers on, retrieval and generation run on one background
thread (one GPU) with a bounded queue (doc/rag-system.md §6.5). The question
text is passed to that job and nowhere else: turns store only the finished
answer, replays only keyed fingerprints. A job whose conversation was deleted
while it ran finds no turn to write to, so its answer is dropped.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import logging
import secrets
from threading import RLock
from uuid import uuid4

from .content import CATALOGUE
from .rag.responses import ABSTAIN
from .safety import route_input

logger = logging.getLogger("companion_api.rag")


class DomainError(Exception):
    def __init__(self, status: int, code: str):
        self.status, self.code = status, code
        super().__init__(code)


@dataclass(frozen=True)
class Grant:
    source: str
    amount: int


@dataclass(frozen=True)
class Replay:
    fingerprint: bytes
    result: dict
    conversation_id: str | None


class DemoStore:
    def __init__(self, answers=None, max_pending: int = 8):
        self.lock = RLock()
        self.max_conversations = 128
        self.max_turns = 512
        self.max_replays = 1024
        # An AnswerService, or None while grounded answers are off.
        self.answers = answers
        self.max_pending = max_pending
        self._pending = 0
        self._executor = (ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-answer")
                          if answers is not None else None)
        self.conversations: set[str] = set()
        self.turns: dict[str, dict] = {}
        self.replays: dict[bytes, Replay] = {}
        self._ledger: list[Grant] = []
        # Ownership and equipment live here, not on the device: a look is worn
        # only after this process has recorded that it was earned.
        self._owned: set[str] = {"default"}
        self._equipped = "default"
        self._completed_lessons: set[str] = set()
        self._fingerprint_secret = secrets.token_bytes(32)

    @property
    def ledger(self):
        with self.lock:
            return tuple(self._ledger)

    @property
    def balance(self):
        with self.lock:
            return sum(grant.amount for grant in self._ledger)

    def _digest(self, value):
        return hmac.new(self._fingerprint_secret, value.encode("utf-8"), sha256).digest()

    def execute(self, key, operation, payload, callback, conversation_id=None, deleting_id=None):
        # Keyed digests prevent retaining text, arbitrary header values or
        # guessable unkeyed fingerprints. Secret lives only in this process.
        key_digest = self._digest(key)
        fingerprint = self._digest(json.dumps([operation, payload], sort_keys=True, separators=(",", ":")))
        with self.lock:
            existing = self.replays.get(key_digest)
            if existing:
                if not hmac.compare_digest(existing.fingerprint, fingerprint):
                    raise DomainError(409, "idempotency_conflict")
                return deepcopy(existing.result)
            releases_slot = deleting_id is not None and any(
                replay.conversation_id == deleting_id for replay in self.replays.values()
            )
            if len(self.replays) >= self.max_replays and not releases_slot:
                raise DomainError(503, "demo_capacity_reached")
            result = callback()
            reference = conversation_id or result.get("conversationId")
            self.replays[key_digest] = Replay(fingerprint, deepcopy(result), reference)
            return result

    def complete_lesson(self):
        with self.lock:
            earned = 0
            # Completion, not ledger emptiness, decides whether this grants:
            # spending stars on a look also writes to the ledger.
            if "demo-learning" not in self._completed_lessons:
                self._completed_lessons.add("demo-learning")
                self._ledger.append(Grant("demo-learning", 5))
                earned = 5
            return {"lessonId": "demo-learning", "completed": True, "earned": earned, "balance": self.balance}

    @property
    def completed_any_lesson(self):
        with self.lock:
            return bool(self._completed_lessons)

    def inventory(self):
        with self.lock:
            return {"items": [{"id": item["id"], "characterId": "robert", "name": item["name"],
                               "description": item["description"], "cost": item["cost"],
                               "owned": item["id"] in self._owned,
                               "equipped": item["id"] == self._equipped}
                              for item in CATALOGUE.values()]}

    def claim(self, cosmetic_id):
        """Spends earned stars on a look. The balance is the ledger, never a client claim."""
        item = CATALOGUE.get(cosmetic_id)
        if item is None:
            raise DomainError(404, "not_found")
        with self.lock:
            if cosmetic_id in self._owned:
                # Already earned. Idempotent by nature, so a lost response or a
                # second key both settle on the same answer instead of charging
                # twice.
                return {"cosmeticId": cosmetic_id, "owned": True, "spent": 0, "balance": self.balance}
            cost = item["cost"]
            if cost > self.balance:
                raise DomainError(403, "insufficient_stars")
            if cost:
                self._ledger.append(Grant("cosmetic:" + cosmetic_id, -cost))
            self._owned.add(cosmetic_id)
            return {"cosmeticId": cosmetic_id, "owned": True, "spent": cost, "balance": self.balance}

    def equip(self, cosmetic_id):
        with self.lock:
            if cosmetic_id not in CATALOGUE or cosmetic_id not in self._owned:
                raise DomainError(403, "cosmetic_not_owned")
            self._equipped = cosmetic_id
            return {"cosmeticId": cosmetic_id, "characterId": "robert"}

    def create_conversation(self):
        with self.lock:
            if len(self.conversations) >= self.max_conversations:
                raise DomainError(503, "demo_capacity_reached")
            identifier = str(uuid4())
            self.conversations.add(identifier)
            return {"conversationId": identifier}

    @staticmethod
    def _answer_fields(result):
        return {"status": "completed", "answerType": result.answer_type, "text": result.text,
                "citations": [source.id for source in result.sources],
                "sources": [{"id": source.id, "title": source.title, "reference": source.reference}
                            for source in result.sources],
                "segments": [{"text": segment.text, "citations": list(segment.citations)}
                             for segment in result.segments]}

    def create_turn(self, conversation_id, text):
        with self.lock:
            if conversation_id not in self.conversations:
                raise DomainError(404, "not_found")
            if len(self.turns) >= self.max_turns:
                raise DomainError(503, "demo_capacity_reached")
            identifier = str(uuid4())
            turn = {"conversationId": conversation_id, "turnId": identifier}
            if self.answers is None:
                answer = route_input(text)
                self.turns[identifier] = {**turn, "status": "completed", "answerType": "unavailable", "text": answer,
                                          "citations": [], "sources": [],
                                          "segments": [{"text": answer, "citations": []}]}
                return {"turnId": identifier, "status": "completed"}
            fixed = self.answers.route(text)
            if fixed is not None:
                self.turns[identifier] = {**turn, **self._answer_fields(fixed)}
                return {"turnId": identifier, "status": "completed"}
            if self._pending >= self.max_pending:
                raise DomainError(503, "answer_queue_full")
            self.turns[identifier] = {**turn, "status": "pending", "answerType": None, "text": "",
                                      "citations": [], "sources": [], "segments": []}
            self._pending += 1
            try:
                self._executor.submit(self._answer, identifier, text)
            except RuntimeError:  # shutting down
                self._pending -= 1
                del self.turns[identifier]
                raise DomainError(503, "answer_queue_full") from None
            return {"turnId": identifier, "status": "pending"}

    def _answer(self, identifier, text):
        try:
            result = self.answers.answer(text)
        except Exception as exception:  # answer() never raises; this is a backstop
            logger.warning("rag_answer_job_error type=%s", type(exception).__name__)
            result = None
        del text
        with self.lock:
            self._pending -= 1
            turn = self.turns.get(identifier)
            if turn is None:
                return  # the conversation was deleted while this ran
            if result is None:
                turn.update(status="completed", answerType="abstained", text=ABSTAIN,
                            segments=[{"text": ABSTAIN, "citations": []}])
            else:
                turn.update(self._answer_fields(result))

    def close(self):
        """Stops the answer worker. Queued jobs are cancelled; a running one finishes and is discarded."""
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def get_turn(self, identifier):
        with self.lock:
            turn = self.turns.get(identifier)
            if turn is None:
                raise DomainError(404, "not_found")
            return {key: deepcopy(value) for key, value in turn.items() if key not in {"conversationId", "segments"}}

    def turn_events(self, identifier):
        """The turn including its verified segments, for the event stream."""
        with self.lock:
            turn = self.turns.get(identifier)
            if turn is None:
                raise DomainError(404, "not_found")
            return {key: deepcopy(value) for key, value in turn.items() if key != "conversationId"}

    def delete_conversation(self, identifier):
        with self.lock:
            self.conversations.discard(identifier)
            self.turns = {key: value for key, value in self.turns.items() if value["conversationId"] != identifier}
            self.replays = {key: value for key, value in self.replays.items() if value.conversation_id != identifier}
            return {}
