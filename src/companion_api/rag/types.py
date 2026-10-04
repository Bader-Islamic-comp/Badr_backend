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
    # chunk-v2 metadata (doc/plan.md component 2). All optional, so chunk-v1 release files still load.
    source_refs: tuple[str, ...] = ()          # machine-readable citations, e.g. "quran:12:4", "bukhari:6018"
    parent_id: str | None = None                # the larger chunk this one is part of (small-to-big)
    cluster_id: str | None = None               # one id for the same hadith across collections
    cluster_refs: tuple[str, ...] = ()          # the other members of the cluster, not indexed separately
    context_header: str = ""                    # one line placed before the text for embedding and search
    tier: int | None = None                     # 0 reference text, 1 scholarly explanation, 2 child content, 3 app help
    prophet_id: str | None = None
    topics: tuple[str, ...] = ()
    madhhab_scope: str | None = None            # "common" or "differs"
    grading: str | None = None
    reviewer: str | None = None
    source_ids: tuple[str, ...] = ()            # registry source_ids the text was copied from
    generated_questions: tuple[str, ...] = ()   # retrieval aids only, generated, never shown to a child
    checksum: str = ""                          # sha256 of `text`
    release_id: str | None = None

    def __post_init__(self):
        if not CHUNK_ID.match(self.id) or not self.id.startswith(self.document_id + "#"):
            raise ValueError(f"invalid chunk id {self.id!r}")
        if self.kind not in ("passage", "answer") or self.review_status not in ("draft", "approved"):
            raise ValueError(f"invalid kind or review status on {self.id!r}")
        if not self.text.strip() or not self.title.strip():
            raise ValueError(f"empty text or title on {self.id!r}")
        if (self.kind == "answer") != bool(self.questions):
            raise ValueError(f"only answer chunks carry questions ({self.id!r})")
        if self.parent_id is not None and not CHUNK_ID.match(self.parent_id):
            raise ValueError(f"invalid parent id on {self.id!r}")
        if self.tier is not None and self.tier not in (0, 1, 2, 3):
            raise ValueError(f"invalid tier on {self.id!r}")
        if self.madhhab_scope not in (None, "common", "differs"):
            raise ValueError(f"invalid madhhab scope on {self.id!r}")

    @property
    def is_child(self) -> bool:
        return self.parent_id is not None and self.parent_id.split("#")[0] == self.document_id

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
    # Every chunk id in the release, written by write_release; empty in releases written before it existed.
    chunk_ids: tuple[str, ...] = ()

    def to_json(self) -> dict:
        data = {_camel(key): getattr(self, key) for key in self.__dataclass_fields__}
        data["corpusIds"] = list(self.corpus_ids)
        data["chunkIds"] = list(self.chunk_ids)
        data["embedder"] = self.embedder.to_json()
        return data

    @classmethod
    def from_json(cls, data: dict) -> "ReleaseManifest":
        values = {_snake(key): value for key, value in data.items()}
        values["corpus_ids"] = tuple(values["corpus_ids"])
        values["chunk_ids"] = tuple(values.get("chunk_ids", ()))
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
