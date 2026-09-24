from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    generativeAnswers: Literal[False] = False
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
    status: Literal["completed"]


class Turn(TurnCreated):
    text: str
    citations: list[str]
