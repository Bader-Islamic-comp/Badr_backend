"""The dhikr game: say one of the four adhkar, and a finished round earns one learning star (ADR 0006).

Stars reward practice, not correctness or religious merit. A round is complete when an attempt is `clear` or
after three counted attempts (`Recitation.counts`), so a child who keeps trying always finishes. The star is
appended to the store's append-only ledger once per round (`dhikr-game:<roundId>`), and no more than
`DAILY_STAR_CAP` per UTC day: past the cap a round still completes, just without a star (the app's copy calls it
a lovely practice; nothing is lost). Rounds hold ids and counts only, never audio.
"""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable
from uuid import uuid4

from ..store import DemoStore, DomainError
from .recitation import Recitation

STARS_PER_ROUND = 1
DAILY_STAR_CAP = 10
COUNTED_TO_COMPLETE = 3
MAX_ROUNDS = 256


@dataclass
class _Round:
    round_id: str
    dhikr_id: str
    attempts: int = 0
    counted: int = 0
    complete: bool = False
    star: bool = False

    def view(self) -> dict:
        return {"roundId": self.round_id, "dhikrId": self.dhikr_id, "attempts": self.attempts,
                "countedAttempts": self.counted, "complete": self.complete, "starAwarded": self.star}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DhikrGame:
    def __init__(self, store: DemoStore, now: Callable[[], datetime] = _utc_now, max_rounds: int = MAX_ROUNDS):
        self.store, self._now, self.max_rounds = store, now, max_rounds
        self._rounds: OrderedDict[str, _Round] = OrderedDict()
        self._awarded: dict[str, date] = {}   # roundId -> the UTC day its star was granted

    def _today(self) -> date:
        return self._now().astimezone(timezone.utc).date()

    def _stars_today(self) -> int:
        today = self._today()
        self._awarded = {round_id: day for round_id, day in self._awarded.items() if day == today}
        return len(self._awarded)

    def stars_today(self) -> int:
        with self.store.lock:
            return self._stars_today()

    def create(self, dhikr_id: str) -> dict:
        with self.store.lock:
            if len(self._rounds) >= self.max_rounds:
                finished = next((key for key, value in self._rounds.items() if value.complete), None)
                if finished is None:
                    raise DomainError(503, "demo_capacity_reached")
                del self._rounds[finished]
            game_round = _Round(str(uuid4()), dhikr_id)
            self._rounds[game_round.round_id] = game_round
            return game_round.view()

    def _open(self, round_id: str) -> _Round:
        game_round = self._rounds.get(round_id)
        if game_round is None:
            raise DomainError(404, "round_not_found")
        if game_round.complete:
            raise DomainError(409, "round_complete")
        return game_round

    def next_attempt(self, round_id: str) -> tuple[str, int]:
        """The round's dhikr and the number of the attempt about to be made."""
        with self.store.lock:
            game_round = self._open(round_id)
            return game_round.dhikr_id, game_round.attempts + 1

    def record(self, round_id: str, recitation: Recitation) -> dict:
        with self.store.lock:
            game_round = self._open(round_id)
            game_round.attempts += 1
            if recitation.counts:
                game_round.counted += 1
            if recitation.outcome == "clear" or game_round.counted >= COUNTED_TO_COMPLETE:
                game_round.complete = True
                if self._stars_today() + STARS_PER_ROUND <= DAILY_STAR_CAP and self.store.grant_once(
                        f"dhikr-game:{round_id}", STARS_PER_ROUND):
                    game_round.star = True
                    self._awarded[round_id] = self._today()
            return game_round.view()
