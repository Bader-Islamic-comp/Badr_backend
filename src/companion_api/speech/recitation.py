"""Pronunciation practice: the speech service's attempt result as the app shows it (ADR 0006).

Practice, never a verdict (Dua-a_stt ADR 0001; must-never `worship_verdict`). The service either abstains or
scores each word `clear`, `try_again` or `unsure`; the outcome is `unsure` when it abstained, `clear` when
every word is clear, else `try_again`. Word states are shown only on the first three attempts and never with
an abstention (ADR 0001 rule 5). The service sends no transcript here, and none is kept.
"""
from dataclasses import dataclass

from .client import SpeechUnavailable

OUTCOMES = ("clear", "try_again", "unsure")
WORD_STATES = ("clear", "try_again", "unsure")
SHOW_WORDS_UP_TO = 3
# Abstentions that still count as a dhikr-game attempt: the child spoke, the service was not sure (benefit of
# the doubt). Off-script, audio quality, too long and service unavailable do not count.
COUNTED_ABSTENTIONS = frozenset({"low_confidence"})


@dataclass(frozen=True)
class Recitation:
    outcome: str
    words: tuple[tuple[int, str], ...]
    abstain_reason: str | None
    copy_id: str | None

    @property
    def counts(self) -> bool:
        """Whether a dhikr-game round counts this attempt."""
        return self.outcome != "unsure" or self.abstain_reason in COUNTED_ABSTENTIONS


def read_attempt(data: dict) -> Recitation:
    """The service's `AttemptResponse` (`status`, `abstainReason`, `words`, `feedbackCopyId`)."""
    try:
        status = data["status"]
        reason = data.get("abstainReason")
        copy_id = data.get("feedbackCopyId")
        words = tuple((int(word["index"]), str(word["state"])) for word in data.get("words") or [])
    except (KeyError, TypeError, ValueError):
        raise SpeechUnavailable("bad_response") from None
    reason = reason if isinstance(reason, str) else None
    copy_id = copy_id if isinstance(copy_id, str) else None
    if status == "abstained":
        return Recitation("unsure", (), reason, copy_id)
    if status != "scored" or any(state not in WORD_STATES for _index, state in words):
        raise SpeechUnavailable("bad_response")
    if not words:
        # Scored with nothing to show is not a result: any doubt is a gentle abstention.
        return Recitation("unsure", (), "low_confidence", None)
    outcome = "clear" if all(state == "clear" for _index, state in words) else "try_again"
    return Recitation(outcome, words, None, copy_id)


def response(recitation: Recitation, attempt: int, feedback: dict) -> dict:
    """The API body: `{"outcome", "words", "showWords", "feedback"}`."""
    show = recitation.outcome != "unsure" and attempt <= SHOW_WORDS_UP_TO
    return {"outcome": recitation.outcome,
            "words": [{"index": index, "state": state} for index, state in recitation.words] if show else [],
            "showWords": show, "feedback": feedback}
