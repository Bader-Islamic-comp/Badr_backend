"""The shapes the pipeline writes and the runtime reads.

A `Chunk` is the unit of retrieval and of citation: its `id` is what an answer
cites and what the client receives as a resolvable source id. Canonical `text`
is shown; `search_text` is only matched. Field names serialize in camelCase so
release files read the same as the API.
"""
from dataclasses import asdict, dataclass, field
import re
from typing import Literal, Protocol, Sequence

SCHEMA_VERSION = 1
CHUNK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}#[1-9][0-9]{0,3}$")
RELEASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

Kind = Literal["passage", "answer"]
ReviewStatus = Literal["draft", "approved"]
Channel = Literal["development", "published"]


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    kind: Kind
    title: str
    language: str
    age_bands: tuple[str, ...]
    content_type: str
    madhhab: tuple[str, ...]
    review_status: ReviewStatus
    synthetic: bool
    text: str
    search_text: str
    references: tuple[str, ...]
    source_label: str
    unit_ids: tuple[str, ...]
    # Answer-bank entries only: the reviewed question phrasings `text` answers.
    questions: tuple[str, ...] = ()

    def __post_init__(self):
        if not CHUNK_ID.match(self.id) or not self.id.startswith(self.document_id + "#"):
            raise ValueError(f"invalid chunk id {self.id!r}")
        if self.kind not in ("passage", "answer") or self.review_status not in ("draft", "approved"):
            raise ValueError(f"invalid kind or review status on {self.id!r}")
        if not self.text.strip() or not self.title.strip():
            raise ValueError(f"empty text or title on {self.id!r}")
        if (self.kind == "answer") != bool(self.questions):
            raise ValueError(f"only answer chunks carry questions ({self.id!r})")

    @property
    def servable(self) -> bool:
        """Served to the app only when approved, or synthetic development copy.

        Real content that is still a draft can be built and evaluated by an adult
        operator, but never reaches a child-facing route.
        """
        return self.review_status == "approved" or self.synthetic

    def to_json(self) -> dict:
        return {_camel(key): list(value) if isinstance(value, tuple) else value
                for key, value in asdict(self).items()}

    @classmethod
    def from_json(cls, data: dict) -> "Chunk":
        values = {_snake(key): tuple(value) if isinstance(value, list) else value for key, value in data.items()}
        return cls(**values)


@dataclass(frozen=True)
class EmbedderIdentity:
    """Which embedder produced a release's vectors. Queries must use the same one."""
    name: str
    model: str
    dimensions: int
    query_instruction: str = ""

    def to_json(self) -> dict:
        return {_camel(key): value for key, value in asdict(self).items()}

    @classmethod
    def from_json(cls, data: dict) -> "EmbedderIdentity":
        return cls(**{_snake(key): value for key, value in data.items()})

    def compatible_with(self, other: "EmbedderIdentity") -> bool:
        return (self.name, self.model, self.dimensions, self.query_instruction) == (
            other.name, other.model, other.dimensions, other.query_instruction)


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    created_at: str
    channel: Channel
    corpus_ids: tuple[str, ...]
    document_count: int
    chunk_count: int
    embedder: EmbedderIdentity
    pipeline: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)
    checksums: dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_json(self) -> dict:
        data = {_camel(key): getattr(self, key) for key in self.__dataclass_fields__}
        data["corpusIds"] = list(self.corpus_ids)
        data["embedder"] = self.embedder.to_json()
        return data

    @classmethod
    def from_json(cls, data: dict) -> "ReleaseManifest":
        values = {_snake(key): value for key, value in data.items()}
        values["corpus_ids"] = tuple(values["corpus_ids"])
        values["embedder"] = EmbedderIdentity.from_json(values["embedder"])
        return cls(**values)


class Embedder(Protocol):
    """Documents and queries are embedded differently by instruction-tuned models."""

    @property
    def identity(self) -> EmbedderIdentity: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class Generator(Protocol):
    """A chat model behind an application-owned interface.

    `complete` returns only the final answer text, never reasoning traces, and
    raises on transport failure so the caller can fall back to a fixed reply.
    `json_mode` asks for one JSON object (the persona call); `temperature`
    overrides the adapter's default for this call only.
    """
    model: str

    def complete(self, messages: Sequence[dict], *, max_tokens: int, json_mode: bool = False,
                 temperature: float | None = None) -> str: ...
