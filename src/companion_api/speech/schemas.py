"""The speech preview's API shapes (ADR 0006). No field carries audio; only `Transcription.text` carries words
the child said, returned once and never kept."""
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import EmptyRequest

DhikrId = Literal["takbeer", "tasbeeh", "tahmeed", "istighfar"]
Outcome = Literal["clear", "try_again", "unsure"]
ReviewStatus = Literal["draft", "approved"]


class Dhikr(BaseModel):
    id: DhikrId
    nameAr: str
    nameEn: str
    transliteration: str
    # Fully voweled, as the speech service's allowlist holds it.
    text: str
    # A pre-rendered recording can be fetched from /v1/audio/adhkar/{id}.
    audio: bool
    # Pronunciation practice is available (/v1/recitations/attempts).
    practice: bool


class AdhkarList(BaseModel):
    items: list[Dhikr]
    reviewStatus: ReviewStatus = "draft"


class DuaSegment(BaseModel):
    index: int
    text: str


class Dua(BaseModel):
    id: str
    group: Literal["adhkar", "daily_duas"]
    kind: Literal["hadith_invocation", "quran_recitation"]
    title: str
    childNote: str
    repeat: int
    occasions: list[str]
    # "recorded": a human recording can be fetched from /v1/audio/duas/{id}.
    audio: Literal["recorded"] | None
    # Practice segments, only where they match the speech service exactly; always empty for Quranic items.
    segments: list[DuaSegment]


class DuaList(BaseModel):
    items: list[Dua]
    reviewStatus: ReviewStatus = "draft"


class WordResult(BaseModel):
    index: int
    state: Outcome


class Feedback(BaseModel):
    copyId: str
    text: str
    # A recording of this line can be fetched from /v1/audio/feedback/{copyId}.
    audio: bool


class Attempt(BaseModel):
    """Practice feedback, never a verdict: `clear`, `try_again` or `unsure`."""
    outcome: Outcome
    words: list[WordResult]
    showWords: bool
    feedback: Feedback


class GameDhikr(BaseModel):
    id: DhikrId
    nameAr: str
    nameEn: str
    text: str
    audio: bool
    practice: bool


class DhikrGame(BaseModel):
    items: list[GameDhikr]
    starsPerRound: Literal[1] = 1
    dailyStarCap: Literal[10] = 10
    starsToday: int


class RoundRequest(EmptyRequest):
    dhikrId: DhikrId


class Round(BaseModel):
    roundId: str
    dhikrId: DhikrId
    attempts: int
    countedAttempts: int
    complete: bool
    starAwarded: bool


class RoundAttempt(BaseModel):
    attempt: Attempt
    round: Round
    balance: int


class Transcription(BaseModel):
    """For the composer: the child checks it and sends it as an ordinary turn. Never stored."""
    status: Literal["transcribed", "unsure"]
    text: str | None = Field(default=None, max_length=1000)


class SpeechPart(BaseModel):
    index: int
    ready: bool


class RobertSpeech(BaseModel):
    """Robert's voice for one answer: play the ready parts in index order; a dropped part leaves the list."""
    status: Literal["pending", "ready", "unavailable"]
    parts: list[SpeechPart]
    reason: str | None = None
