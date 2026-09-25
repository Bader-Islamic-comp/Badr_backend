"""Hybrid retrieval over one loaded release (doc/rag-system.md §6.2).

BM25 and cosine each rank the eligible chunks; reciprocal rank fusion merges
the two lists without having to put their scores on one scale. Two decisions
are made here, before any model is called:

* **Weak evidence.** No lexical hit and a best cosine under the embedder's
  threshold means the release has nothing on the question, so the service
  abstains instead of asking a model to answer from memory.
* **Reviewed answers first.** When an answer-bank entry among the top
  candidates has a reviewed phrasing that matches the question closely (token
  Jaccard >= 0.6), or the top candidate is an answer whose cosine clears the
  reviewed-answer threshold, that reviewed text is returned verbatim and no
  model is called.

Threshold calibration. Cosine scales differ between embedders, so both
thresholds are per embedder and can be overridden at construction:

* `hashing` (offline development embedder): unrelated questions score about
  -0.15..0.13 against the development corpus (random hash collisions), related
  ones 0.27 and up, so weak evidence is < 0.2. A reviewed phrasing asked
  verbatim scores about 0.84 against its answer chunk (questions plus answer
  are embedded together) and a different question about the same subject
  0.5..0.65, so the reviewed-answer threshold is 0.75.
* `openai-compatible` (qwen3-embedding:0.6b): provisional 0.45 and 0.85, from
  the model's usual query-to-document range (unrelated text in the same domain
  scores roughly 0.2..0.4). Re-run `python -m companion_api.rag.evaluate` on a
  real release before trusting them.

Unknown embedders get the stricter values, which abstain more and match
reviewed answers less.
"""
from dataclasses import dataclass
from typing import Sequence

from . import normalize
from .embeddings import cosine
from .lexical import BM25, chunk_tokens
from .release import LoadedRelease
from .types import Chunk, Embedder

RETRIEVER_VERSION = "hybrid-rrf-v1"
RRF_K = 60
BRANCH_K = 20
FINAL_K = 4
REVIEWED_JACCARD = 0.6

# (weak-evidence cosine, reviewed-answer cosine) by EmbedderIdentity.name.
THRESHOLDS = {
    "hashing": (0.2, 0.75),
    "openai-compatible": (0.45, 0.85),
}
STRICT_THRESHOLDS = (max(t[0] for t in THRESHOLDS.values()), max(t[1] for t in THRESHOLDS.values()))


class RetrieverError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    chunk: Chunk
    score: float   # fused RRF score
    cosine: float
    bm25: float


@dataclass(frozen=True)
class Retrieval:
    candidates: tuple[Candidate, ...]
    weak: bool
    # The answer-bank candidate whose reviewed text answers the question, if any.
    reviewed: Candidate | None = None


def jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a and b else 0.0


class HybridRetriever:
    def __init__(self, release: LoadedRelease, embedder: Embedder, *, include_drafts: bool = False,
                 weak_cosine: float | None = None, reviewed_cosine: float | None = None,
                 branch_k: int = BRANCH_K, final_k: int = FINAL_K, rrf_k: int = RRF_K):
        expected, actual = release.manifest.embedder, embedder.identity
        if not actual.compatible_with(expected):
            raise RetrieverError(
                f"release {release.manifest.release_id!r} was embedded with {expected.name}/{expected.model} "
                f"({expected.dimensions} dimensions) but the configured embedder is {actual.name}/{actual.model} "
                f"({actual.dimensions} dimensions); set COMPANION_EMBEDDING_MODEL to match or rebuild the release")
        defaults = THRESHOLDS.get(actual.name, STRICT_THRESHOLDS)
        self.release = release
        self.embedder = embedder
        # Drafts are for adult operators evaluating content; nothing
        # child-facing constructs a retriever with them.
        self.include_drafts = include_drafts
        self.weak_cosine = defaults[0] if weak_cosine is None else weak_cosine
        self.reviewed_cosine = defaults[1] if reviewed_cosine is None else reviewed_cosine
        self.branch_k, self.final_k, self.rrf_k = branch_k, final_k, rrf_k
        self._eligible = [index for index, chunk in enumerate(release.chunks) if include_drafts or chunk.servable]
        self._index = BM25([chunk_tokens(chunk) for chunk in release.chunks])

    def _allowed(self, language: str, age_band: str | None) -> list[int]:
        chunks = self.release.chunks
        return [index for index in self._eligible if chunks[index].language == language
                and (age_band is None or age_band in chunks[index].age_bands)]

    def retrieve(self, question: str, *, language: str = "en", age_band: str | None = None) -> Retrieval:
        allowed = self._allowed(language, age_band)
        if not allowed:
            return Retrieval((), True)
        query_tokens = normalize.content_tokens(question)
        lexical = self._index.top(query_tokens, self.branch_k, allowed)
        vector = self.embedder.embed_query(question)
        cosines = {index: cosine(vector, self.release.vectors[index]) for index in allowed}
        dense = sorted(cosines.items(), key=lambda item: (-item[1], item[0]))[:self.branch_k]
        if not lexical and dense[0][1] < self.weak_cosine:
            return Retrieval((), True)

        fused: dict[int, float] = {}
        for ranking in (lexical, dense):
            for rank, (index, _score) in enumerate(ranking, start=1):
                fused[index] = fused.get(index, 0.0) + 1.0 / (self.rrf_k + rank)
        bm25 = dict(lexical)
        order = sorted(fused, key=lambda index: (-fused[index], index))[:self.final_k]
        candidates = tuple(Candidate(self.release.chunks[index], fused[index], cosines[index], bm25.get(index, 0.0))
                           for index in order)
        return Retrieval(candidates, False, self._reviewed(question, candidates))

    def _reviewed(self, question: str, candidates: Sequence[Candidate]) -> Candidate | None:
        """The answer-bank candidate whose reviewed text answers the question, if any.

        A reviewed phrasing that matches word for word wins first, from any
        answer in the top candidates: a sibling answer that repeats the subject
        ("Robert") can outrank the entry holding the child's exact question, and
        can even clear the cosine threshold, because one repeated word dominates
        both vectors. The cosine criterion therefore only applies to the best
        candidate, and only when no phrasing matched.
        """
        tokens = normalize.content_tokens(question)
        for candidate in candidates:
            if candidate.chunk.kind == "answer" and any(
                    jaccard(tokens, normalize.content_tokens(phrasing)) >= REVIEWED_JACCARD
                    for phrasing in candidate.chunk.questions):
                return candidate
        best = candidates[0]
        return best if best.chunk.kind == "answer" and best.cosine >= self.reviewed_cosine else None
