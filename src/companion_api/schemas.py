from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

# doc/rag-system.md §7. `unavailable` is the only type while grounded answers are off.
AnswerType = Literal["unavailable", "grounded", "reviewed_answer", "abstained", "redirected", "safety"]


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


class Features(BaseModel):
    voice: Literal[False] = False
    # True only when this process started with a verified release and model.
    generativeAnswers: bool = False
    unity: Literal[False] = False


class Bootstrap(BaseModel):
    mode: Literal["development"] = "development"
    characterId: Literal["robert"] = "robert"
    profileId: Literal["demo-child"] = "demo-child"
    features: Features = Field(default_factory=Features)
    contentStatus: Literal["awaiting_review"] = "awaiting_review"


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
    title: str = Field(min_length=1, max_length=500)
    reference: str = Field(max_length=500)


class Turn(TurnCreated):
    """`answerType` is null and `text` empty while pending; completed text is 1-1200 characters."""
    answerType: AnswerType | None
    text: str = Field(max_length=1200)
    citations: list[str] = Field(max_length=4)
    sources: list[Source] = Field(max_length=4)
