"""The answer runtime: route, retrieve, generate, verify (doc/rag-system.md §6).

`AnswerService.answer` never raises. Every failure (an unreachable model, an
embedding error, a verification failure, a bug) becomes the same gentle
abstention, because a child should never see an error where an answer was
expected, and a failure must never fall through to an unverified answer.

Provenance (release, model, prompt, retriever, verifier and embedder versions)
travels with every result and is logged once per answer on `companion_api.rag`.
The question, the passages and the answer are never logged.
"""
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import NamedTuple

from . import normalize, router
from .embeddings import embedder_for
from .generator import OpenAICompatibleGenerator
from .grounding import MAX_CHARS, VERIFIER_VERSION, Segment, verify
from .prompts import PROMPT_VERSION, build_messages
from .release import ReleaseError, load_release
from .responses import ABSTAIN, INJECTION, PERSONAL_DATA, RULING, SAFETY
from .retriever import RETRIEVER_VERSION, HybridRetriever, Retrieval, RetrieverError
from .types import Chunk, Generator

logger = logging.getLogger("companion_api.rag")

# Route category -> (answer type, fixed reply).
FIXED = {
    "safety": ("safety", SAFETY),
    "personal_data": ("redirected", PERSONAL_DATA),
    "ruling": ("redirected", RULING),
    "injection": ("redirected", INJECTION),
}


class Source(NamedTuple):
    id: str
    title: str
    reference: str

    @classmethod
    def of(cls, chunk: Chunk) -> "Source":
        return cls(chunk.id, chunk.title, chunk.source_label)


@dataclass(frozen=True)
class AnswerResult:
    answer_type: str
    text: str
    segments: tuple[Segment, ...]
    sources: tuple[Source, ...]
    provenance: dict = field(default_factory=dict)
    # How the answer was reached, as a fixed code for evaluation: "route:<category>",
    # "weak_evidence", "reviewed_match", "grounded", "grounding:<failure>", "error:<type>".
    reason: str = ""

    @property
    def citations(self) -> tuple[str, ...]:
        return tuple(source.id for source in self.sources)


class AnswerService:
    def __init__(self, retriever: HybridRetriever, generator: Generator, *, language: str = "en",
                 max_tokens: int = 320, age_band: str | None = None,
                 classifiers: tuple[router.SafetyClassifier, ...] = ()):
        self.retriever, self.generator = retriever, generator
        self.language, self.max_tokens, self.age_band = language, max_tokens, age_band
        self.classifiers = classifiers
        identity = retriever.embedder.identity
        self.provenance = {
            "releaseId": retriever.release.manifest.release_id,
            "model": generator.model,
            "promptVersion": PROMPT_VERSION,
            "retriever": RETRIEVER_VERSION,
            "verifier": VERIFIER_VERSION,
            "embedder": f"{identity.name}/{identity.model}",
        }

    def _result(self, answer_type: str, text: str, reason: str, segments: tuple[Segment, ...] | None = None,
                sources: tuple[Source, ...] = ()) -> AnswerResult:
        return AnswerResult(answer_type, text, segments or (Segment(text, ()),), sources, dict(self.provenance), reason)

    def _abstain(self, reason: str) -> AnswerResult:
        return self._result("abstained", ABSTAIN, reason)

    def _route(self, text: str) -> AnswerResult | None:
        found = router.route(text, self.classifiers)
        if found.category == "retrieve":
            return None
        answer_type, reply = FIXED[found.category]
        return self._result(answer_type, reply, "route:" + found.category)

    def route(self, text: str) -> AnswerResult | None:
        """A fixed reply, or None when the question needs retrieval. Cheap and deterministic."""
        started = perf_counter()
        try:
            result = self._route(text)
        except Exception as exception:  # fail closed: a broken rule must not let a question through
            logger.warning("rag_route_error type=%s", type(exception).__name__)
            result = self._abstain("error:" + type(exception).__name__)
        if result is not None:
            self._log(result, 0, started)
        return result

    def prepare(self, text: str) -> tuple[AnswerResult | None, Retrieval | None]:
        """Everything before the model: an answer that needs no model, or None and the evidence to generate from.

        The evaluator calls this directly, so offline results follow exactly
        the path the API takes.
        """
        fixed = self._route(text)
        if fixed is not None:
            return fixed, None
        if normalize.detect_language(text) != self.language:
            # The router's patterns only read this service's language.
            return self._abstain("language_mismatch"), None
        retrieval = self.retriever.retrieve(text, language=self.language, age_band=self.age_band)
        if retrieval.weak:
            return self._abstain("weak_evidence"), retrieval
        if retrieval.reviewed is not None and len(retrieval.reviewed.chunk.text) <= MAX_CHARS:
            chunk = retrieval.reviewed.chunk
            return self._result("reviewed_answer", chunk.text, "reviewed_match",
                                (Segment(chunk.text, (chunk.id,)),), (Source.of(chunk),)), retrieval
        return None, retrieval

    def answer(self, text: str) -> AnswerResult:
        """The full path. Never raises."""
        started, passages = perf_counter(), 0
        try:
            result, retrieval = self.prepare(text)
            if result is None:
                passages = len(retrieval.candidates)
                result = self._generate(text, [candidate.chunk for candidate in retrieval.candidates])
            elif result.answer_type == "reviewed_answer":
                passages = 1
        except Exception as exception:
            # The type only: messages from lower layers are written to carry no
            # content, but an unexpected exception's message might.
            logger.warning("rag_answer_error type=%s", type(exception).__name__)
            result = self._abstain("error:" + type(exception).__name__)
        self._log(result, passages, started)
        return result

    def _generate(self, text: str, passages: list[Chunk]) -> AnswerResult:
        output = self.generator.complete(build_messages(text, passages), max_tokens=self.max_tokens)
        grounding = verify(output, passages)
        if not grounding.ok:
            return self._abstain("grounding:" + str(grounding.failure))
        by_id = {chunk.id: chunk for chunk in passages}
        cited = list(dict.fromkeys(chunk_id for segment in grounding.segments for chunk_id in segment.citations))
        return self._result("grounded", " ".join(segment.text for segment in grounding.segments), "grounded",
                            grounding.segments, tuple(Source.of(by_id[chunk_id]) for chunk_id in cited))

    def _log(self, result: AnswerResult, passages: int, started: float):
        fields = {
            "answer_type": result.answer_type,
            "release_id": self.provenance["releaseId"],
            "model": self.provenance["model"],
            "prompt_version": self.provenance["promptVersion"],
            "retriever": self.provenance["retriever"],
            "verifier": self.provenance["verifier"],
            "embedder": self.provenance["embedder"],
            "passages": passages,
            "latency_ms": round((perf_counter() - started) * 1000),
        }
        # Which fixed route fired is already implied by the answer type and is
        # not repeated; other outcomes are fixed codes that help operators.
        if not result.reason.startswith("route:"):
            fields["outcome"] = result.reason
        logger.info("rag_answer %s", json.dumps(fields, sort_keys=True), extra={"rag": fields})


def assemble(settings, release_dir: str | Path, *, include_drafts: bool = False) -> AnswerService:
    """An `AnswerService` over one release, from the server's settings.

    The server, the evaluator and the operator console all build through here,
    so they cannot disagree about embedder, model or endpoints.
    """
    try:
        loaded = load_release(Path(release_dir))
    except ReleaseError as exception:
        raise RuntimeError(f"Release {release_dir} failed verification: {exception}") from None
    try:
        embedder = embedder_for(settings.embedding_model, settings.embedding_endpoint)
        retriever = HybridRetriever(loaded, embedder, include_drafts=include_drafts)
        generator = OpenAICompatibleGenerator(settings.llm_base_url, settings.llm_model,
                                              settings.llm_timeout_seconds)
    except (RetrieverError, ValueError) as exception:
        raise RuntimeError(f"Grounded answers cannot start: {exception}") from None
    return AnswerService(retriever, generator)


def _record_provenance():
    """Uvicorn configures only its own loggers, so without a handler the one
    provenance line per answer would be dropped. The line carries versions,
    counts and timings only, never the question, passages or answer."""
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def build_answer_service(settings) -> AnswerService:
    """The API's answer service. Fails closed: any configuration problem stops startup."""
    settings.require_rag()
    service = assemble(settings, settings.rag_release)
    _record_provenance()
    return service
