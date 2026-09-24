"""Bounded single-process synthetic state; replace with PostgreSQL before real use."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import secrets
from threading import RLock
from uuid import uuid4

from .content import CATALOGUE
from .safety import route_input


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
    def __init__(self):
        self.lock = RLock()
        self.max_conversations = 128
        self.max_turns = 512
        self.max_replays = 1024
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

    def create_turn(self, conversation_id, text):
        with self.lock:
            if conversation_id not in self.conversations:
                raise DomainError(404, "not_found")
            if len(self.turns) >= self.max_turns:
                raise DomainError(503, "demo_capacity_reached")
            answer = route_input(text)
            identifier = str(uuid4())
            self.turns[identifier] = {"conversationId": conversation_id, "turnId": identifier,
                                      "status": "completed", "text": answer, "citations": []}
            return {"turnId": identifier, "status": "completed"}

    def get_turn(self, identifier):
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
