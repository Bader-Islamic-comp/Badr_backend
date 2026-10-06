"""Child-facing speech copy and the check every feedback line passes (ADR 0006).

Pronunciation practice is never a verdict on worship (Dua-a_stt ADR 0001; must-never `worship_verdict`): no
line may say a recitation is wrong, failed, invalid, rejected or does not count, and none may claim it is
correct, valid or accepted. Lines from the speech service are shown only when they pass `is_gentle`; otherwise
the backend's own line for the outcome is used. Every line here is development copy awaiting review.
"""
from ..rag import never
from .arabic import letters

# The owner's list (2026-10-06): never in child-facing speech copy.
BANNED = ("غلط", "خطأ", "فشلت", "ما قُبل", "باطل", "لا يصح", "ما بتنحسب", "مرفوض",
          "wrong", "failed", "invalid", "rejected", "incorrect", "mistake")
_BANNED_FOLDED = tuple(letters(word).casefold() for word in BANNED)

# The backend's line per outcome, under the speech service's copy id for the same words, used when the
# service's copy cannot be read or does not pass the check. Draft, awaiting review.
FALLBACK_FEEDBACK = {
    "clear": ("all_clear_1", "ما شاء الله، أحسنت!"),
    "try_again": ("try_again_first", "لا بأس، جرّب مرة ثانية ببطء."),
    "unsure": ("abstain_generic", "خلّينا نجرّب مرة ثانية."),
}


def is_gentle(text: str) -> bool:
    """No banned word (diacritics and case ignored) and no must-never rule (never-v1) in `text`."""
    folded = letters(text).casefold()
    return bool(folded) and not any(word in folded for word in _BANNED_FOLDED) and not never.violations(text)


def child_facing() -> list[str]:
    """Every child-facing line this package owns, for the copy tests."""
    from .adhkar import ADHKAR
    return [text for _copy_id, text in FALLBACK_FEEDBACK.values()] + [
        value for item in ADHKAR for value in (item["nameAr"], item["nameEn"], item["transliteration"])]
