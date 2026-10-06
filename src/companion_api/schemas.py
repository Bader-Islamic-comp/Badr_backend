from typing import Annotated, Literal

from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Every client write carries one (README "API behavior").
WriteKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[\x21-\x7e]+$")]

# doc/rag-system.md §7. `unavailable` is the only type while grounded answers are off. `chat` is
# Robert's checked casual reply, with no citations or sources (doc/conversation-policy.md §9).
AnswerType = Literal["unavailable", "grounded", "reviewed_answer", "abstained", "redirected", "safety", "chat"]


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorCode(BaseModel):
    code: str


class ErrorEnvelope(BaseModel):
    error: ErrorCode


class TurnRequest(EmptyRequest):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("invalid_request")
        return value


class CosmeticRequest(EmptyRequest):
    cosmeticId: str = Field(min_length=1, max_length=64)


class SpeechFeatures(BaseModel):
    """The speech preview for adult operators (ADR 0006): never the release gate's `voice` switch.

    `preview` is the master switch and is true only in development mode; each feature is true only with it.
    """
    preview: bool = False
    recitation: bool = False
    voiceQuestions: bool = False
    robertVoice: bool = False
    # The app's push-to-talk bound; the server also bounds every recording to 1 MiB.
    maxRecordingSeconds: Literal[15] = 15

    @model_validator(mode="after")
    def features_need_the_preview(self):
        if not self.preview and (self.recitation or self.voiceQuestions or self.robertVoice):
            raise ValueError("a speech feature is on without the preview")
        return self


class Features(BaseModel):
    # The release gate's switch (doc/governance/release-gate.md): push-to-talk for children. Stays false.
    voice: Literal[False] = False
    # True only when this process started with a verified release and model.
    generativeAnswers: bool = False
    unity: Literal[False] = False
    speech: SpeechFeatures = Field(default_factory=SpeechFeatures)


class Bootstrap(BaseModel):
    mode: Literal["development"] = "development"
    characterId: Literal["robert"] = "robert"
    profileId: Literal["demo-child"] = "demo-child"
    features: Features = Field(default_factory=Features)
    # "unreviewed_drafts": an adult operator's corpus preview serves draft religious content
    # (doc/rag-system.md §9.1). Never a child-facing setting.
    contentStatus: Literal["awaiting_review", "unreviewed_drafts"] = "awaiting_review"

    @model_validator(mode="after")
    def speech_preview_is_development_only(self):
        # ADR 0006: the preview serves adult operators in development mode, never a child-facing mode.
        if self.features.speech.preview and self.mode != "development":
            raise ValueError("the speech preview is development only")
        return self


class Lesson(BaseModel):
    id: str
    title: str
    summary: str
    kind: Literal["orientation"]
    steps: list[str]
    reward: int


class LessonList(BaseModel):
    items: list[Lesson]


class Completion(BaseModel):
    lessonId: str
    completed: bool
    earned: int
    balance: int


class Challenge(BaseModel):
    id: str
    title: str
    description: str
    completed: bool
    verification: Literal["lesson_completion"]


class ChallengeList(BaseModel):
    items: list[Challenge]


class Rewards(BaseModel):
    balance: int
    unit: Literal["learning_stars"] = "learning_stars"


class Cosmetic(BaseModel):
    id: str
    characterId: str
    name: str
    description: str
    cost: int
    owned: bool
    equipped: bool


class Inventory(BaseModel):
    items: list[Cosmetic]


class Equipped(BaseModel):
    cosmeticId: str
    characterId: str


class Claimed(BaseModel):
    cosmeticId: str
    owned: bool
    spent: int
    balance: int


class ConversationCreated(BaseModel):
    conversationId: str


class TurnCreated(BaseModel):
    turnId: str
    status: Literal["pending", "completed"]


class Source(BaseModel):
    """A cited reviewed passage: `id` resolves to one chunk of the serving release."""
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}#[1-9][0-9]{0,3}$")
    # The Flutter client refuses a whole reply outside these bounds; the pipeline enforces them at build.
    title: str = Field(min_length=1, max_length=120)
    reference: str = Field(min_length=1, max_length=160)


class Turn(TurnCreated):
    """`answerType` is null and `text` empty while pending; completed text is 1-1200 characters.

    `citations` and `sources` are empty for every type except `grounded` and `reviewed_answer`.
    """
    answerType: AnswerType | None
    text: str = Field(max_length=1200)
    citations: list[str] = Field(max_length=4)
    sources: list[Source] = Field(max_length=4)
