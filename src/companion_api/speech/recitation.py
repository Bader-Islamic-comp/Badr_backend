"""Pronunciation practice: the speech service's attempt result as the app shows it (ADR 0006).

Practice, never a verdict (Dua-a_stt ADR 0001; must-never `worship_verdict`). The service either abstains or
scores each word `clear`, `try_again` or `unsure`; the outcome is `clear` when every word is clear, `try_again`
when at least one word is to try again, and `unsure` otherwise: an abstention, or scored words that are clear
or unsure with none to try again. Any doubt is a gentle abstention (Dua-a_stt principle 4: the worst error is
telling a child who said it right to try again), and the dhikr game counts that doubt as an attempt, as it counts
`low_confidence`. Word states are shown only on the first three attempts and never with `unsure` (ADR 0001
rule 5). The service sends no transcript here, and none is kept.
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
    if words and all(state == "clear" for _index, state in words):
        return Recitation("clear", words, None, copy_id)
    if any(state == "try_again" for _index, state in words):
        return Recitation("try_again", words, None, copy_id)
    # Scored with nothing to show, or unsure of some words and sure of no mistake: not a result to act on. Any
    # doubt is a gentle abstention, counted like low_confidence; the service's "try these words" line is not used.
    return Recitation("unsure", (), "low_confidence", None)


def response(recitation: Recitation, attempt: int, feedback: dict) -> dict:
    """The API body: `{"outcome", "words", "showWords", "feedback"}`."""
    show = recitation.outcome != "unsure" and attempt <= SHOW_WORDS_UP_TO
    return {"outcome": recitation.outcome,
            "words": [{"index": index, "state": state} for index, state in recitation.words] if show else [],
            "showWords": show, "feedback": feedback}
