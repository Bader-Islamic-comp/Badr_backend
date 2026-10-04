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

Small-to-big (`hybrid-rrf-v2`). A chunk-v2 release holds parent chunks and
their child chunks (one per verbatim part of a long unit, or per unit of a
multi-unit chunk). Both are ranked, so a child can match a question its parent
dilutes, but a hit on a child serves its parent: the parent appears once, at
the best rank any of its members reached, carrying that member's scores. The
model sees the whole unit in context and cites the parent id, and one passage
never fills several of the final slots. Releases without children rank as
under v1.

Passages first, commentary after its passage (`hybrid-rrf-v3`, doc/rag-system.md
§17). On a release with the tafsirs, commentary outnumbers the Quran passages it
explains by about five to one and its narrations repeat the question's words, so
under v2 four al-Tabari chunks filled the prompt for a Yusuf question with no
ayah among them. v3 ranks passages, not chunks:

* A tafsir chunk (`tafsir`, `tafsir_translation`) is evidence for the passage its
  `parentChunk` names, like a child for its parent: the parent when it is
  eligible for this query, else (an English service) an eligible translation of
  the meanings of that passage. Commentary with no such passage never serves.
* Each branch ranks passages, at the best rank any of their members reached
  (own children and commentary), and keeps 20 passages; RRF fuses the two lists.
  A passage named by its own words in one branch and by its commentary in the
  other gets both.
* The prompt gets the best four passages in order. A commentary chunk enters
  only right after its own passage, as an addition that never takes a passage's
  place: the best-ranked chunk of a book not yet used, at most one in all
  (`MAX_COMMENTARY`), so the prompt holds at most five sources.
* Curated child content (`story`, `dua`, `lesson`, tier 2) about as relevant as
  the best passage (fused score at least `CURATED_RATIO` of it) is put first.
* The lexical branch also scores the header phrases (`lexical.phrases`): a pair
  of a function word and a content word of the question found in a chunk's
  context header ("بعد الصلاة"), scored by BM25 over headers and added to the
  text's BM25 score.

Threshold calibration. Cosine scales differ between embedders, so both
thresholds are per embedder and can be overridden at construction:

* `hashing` (offline development embedder): unrelated questions score about
  -0.15..0.13 against the development corpus (random hash collisions), related
  ones 0.27 and up, so weak evidence is < 0.2. A reviewed phrasing asked
  verbatim scores about 0.84 against its answer chunk (questions plus answer
  are embedded together) and a different question about the same subject
  0.5..0.65, so the reviewed-answer threshold is 0.75.
* `openai-compatible` (qwen3-embedding:0.6b): measured on the development
  corpus (2026-09-25, release dev-app-help-qwen-1). Questions it answers score
  0.685..0.856 against their best chunk; unrelated ones 0.245..0.462 ("What is
  the weather today?" is the 0.462). So weak evidence is < 0.55, with margin on
  both sides. Questions naming Robert but unanswerable from the corpus ("Can
  Robert fly?") score about 0.63: those are the model's to decline with
  NOT_IN_SOURCES, not the threshold's. A reviewed answer by cosine needs 0.85,
  about what a near-verbatim reviewed phrasing scores. Recalibrate with
  `python -m companion_api.rag.evaluate` whenever the corpus changes materially.

Unknown embedders get the stricter values, which abstain more and match
reviewed answers less.
"""
from dataclasses import dataclass
from typing import Sequence

from . import normalize
from .embeddings import cosine
from .lexical import BM25, chunk_tokens, header_phrases, phrases
from .release import LoadedRelease
from .types import Chunk, Embedder

RETRIEVER_VERSION = "hybrid-rrf-v3"
RRF_K = 60
BRANCH_K = 20
FINAL_K = 4
REVIEWED_JACCARD = 0.6
# Commentary on a passage: served only after that passage (v3).
COMMENTARY_CONTENT = frozenset({"tafsir", "tafsir_translation"})
TRANSLATION_OF_PASSAGE = "quran_translation"
MAX_COMMENTARY = 1
# Curated child content (tier 2): first when its fused score is at least this share of the best passage's.
CURATED_CONTENT = frozenset({"story", "dua", "lesson"})
CURATED_RATIO = 0.9

# (weak-evidence cosine, reviewed-answer cosine) by EmbedderIdentity.name.
THRESHOLDS = {
    "hashing": (0.2, 0.75),
    "openai-compatible": (0.55, 0.85),
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
        self._headers = BM25([header_phrases(chunk) for chunk in release.chunks])
        # Where each chunk's hit is served: itself, or for a chunk-v2 child its parent (small-to-big).
        positions = {chunk.id: index for index, chunk in enumerate(release.chunks)}
        self._serves: list[int] = []
        for index, chunk in enumerate(release.chunks):
            parent = positions.get(chunk.parent_id) if chunk.is_child else index
            if parent is None or release.chunks[parent].is_child:
                raise RetrieverError(f"release {release.manifest.release_id!r}: child chunk {chunk.id} names a "
                                     "parent that is not a parent chunk in the release")
            self._serves.append(parent)
        # Commentary (v3): the passage its unit's parentChunk names in another document, and the translations
        # of the meanings of each passage, for a service that cannot serve the passage itself.
        self._commented: dict[int, int] = {}
        self._translations: dict[str, list[int]] = {}
        for index, chunk in enumerate(release.chunks):
            unit = release.chunks[self._serves[index]]
            target = positions.get(unit.parent_id) if unit.parent_id and not unit.is_child else None
            if target is None:
                continue
            if chunk.content_type in COMMENTARY_CONTENT:
                self._commented[index] = self._serves[target]
            elif chunk.content_type == TRANSLATION_OF_PASSAGE and not chunk.is_child:
                self._translations.setdefault(release.chunks[target].id, []).append(index)
        # Reviewed phrasings by their full search text, stopwords included. A
        # child asking one word for word gets its reviewed answer even when the
        # question is all stopwords ("What can you do?"), which leaves nothing
        # for BM25 or the Jaccard match and would otherwise read as weak evidence.
        self._phrasings: dict[str, int] = {}
        for index in self._eligible:
            for phrasing in release.chunks[index].questions:
                self._phrasings.setdefault(normalize.search_text(phrasing), index)

    def _allowed(self, language: str, age_band: str | None) -> list[int]:
        chunks = self.release.chunks
        return [index for index in self._eligible if chunks[index].language == language
                and (age_band is None or age_band in chunks[index].age_bands)]

    def eligible(self, *, language: str = "en", age_band: str | None = None) -> list[Chunk]:
        """The chunks this retriever may serve in `language` (and `age_band`), in release order."""
        return [self.release.chunks[index] for index in self._allowed(language, age_band)]

    def exact(self, question: str, *, language: str = "en", age_band: str | None = None) -> Candidate | None:
        """The eligible answer chunk holding this exact reviewed phrasing, stopwords included, if any.

        The service asks this before small talk (doc/conversation-policy.md §2),
        so "Who are you?" gets its reviewed answer rather than a chat reply.
        """
        index = self._phrasings.get(normalize.search_text(question))
        if index is None:
            return None
        chunk = self.release.chunks[index]
        if chunk.language != language or (age_band is not None and age_band not in chunk.age_bands):
            return None
        # Nominal scores: an exact reviewed phrasing needs no ranking.
        return Candidate(chunk, 1.0, 1.0, 0.0)

    def retrieve(self, question: str, *, language: str = "en", age_band: str | None = None,
                 prophet_ids: tuple[str, ...] = ()) -> Retrieval:
        """`prophet_ids` (an Arabizi question that names prophets, `arabizi.expand`) narrows the search to
        their passages, when the release has any; otherwise it is ignored."""
        allowed = self._allowed(language, age_band)
        if prophet_ids:
            narrowed = [index for index in allowed if self.release.chunks[index].prophet_id in prophet_ids]
            allowed = narrowed or allowed
        # Where each eligible chunk's hit is served: its passage. Commentary without one never serves.
        units = self._units(allowed)
        if not units:
            return Retrieval((), True)
        exact = self.exact(question, language=language, age_band=age_band)
        if exact is not None:
            return Retrieval((exact,), False, exact)
        bm25 = self._lexical(question, units)
        lexical = sorted(bm25.items(), key=lambda item: (-item[1], item[0]))
        vector = self.embedder.embed_query(question)
        cosines = {index: cosine(vector, self.release.vectors[index]) for index in units}
        dense = sorted(cosines.items(), key=lambda item: (-item[1], item[0]))
        if not lexical and dense[0][1] < self.weak_cosine:
            return Retrieval((), True)

        # Each branch ranks passages at the best rank any of their members reached; RRF fuses the two lists.
        fused: dict[int, float] = {}
        members: dict[int, int] = {}       # passage -> its best-ranked member (for its scores)
        commentary: dict[int, float] = {}  # commentary chunk -> its own fused score, for choosing among them
        for ranking in (lexical, dense):
            ranked: dict[int, int] = {}
            for position, (index, _score) in enumerate(ranking, start=1):
                unit = units[index]
                if unit not in ranked:
                    if len(ranked) == self.branch_k:
                        break
                    ranked[unit] = len(ranked) + 1
                    members.setdefault(unit, index)
                if index in self._commented:
                    commentary[index] = commentary.get(index, 0.0) + 1.0 / (self.rrf_k + position)
            for unit, rank in ranked.items():
                fused[unit] = fused.get(unit, 0.0) + 1.0 / (self.rrf_k + rank)
        order = sorted(fused, key=lambda unit: (-fused[unit], unit))
        order = self._curated_first(order, fused)
        by_unit: dict[int, list[int]] = {}
        for index in sorted(commentary, key=lambda index: (-commentary[index], index)):
            by_unit.setdefault(units[index], []).append(self._serves[index])

        def candidate(served: int, member: int, score: float) -> Candidate:
            return Candidate(self.release.chunks[served], score, cosines[member], bm25.get(member, 0.0))

        # The best `final_k` passages; commentary only right after its own passage, the best-ranked chunk of a
        # book not yet used, at most MAX_COMMENTARY in all. It adds to the passages, never takes their place.
        chosen: list[Candidate] = []
        books: set[tuple[str, ...]] = set()
        for unit in order[:self.final_k]:
            chosen.append(candidate(unit, members[unit], fused[unit]))
            for served in dict.fromkeys(by_unit.get(unit, ())):
                book = self._book(self.release.chunks[served])
                if len(books) < MAX_COMMENTARY and book not in books:
                    books.add(book)
                    chosen.append(candidate(served, served if served in cosines else members[unit], fused[unit]))
                    break
        candidates = tuple(chosen)
        return Retrieval(candidates, False, self._reviewed(question, candidates))

    def _units(self, allowed: Sequence[int]) -> dict[int, int]:
        """Eligible chunk -> the passage its hit serves: its parent (small-to-big), or for commentary the passage
        it explains when that passage is eligible, else an eligible translation of its meanings; none, none."""
        permitted, chunks = set(allowed), self.release.chunks
        units = {}
        for index in allowed:
            if chunks[index].content_type not in COMMENTARY_CONTENT:
                units[index] = self._serves[index]
                continue
            passage = self._commented.get(index)
            if passage is None:  # commentary that names no passage in the release
                continue
            if passage not in permitted:
                passage = next((translation for translation in self._translations.get(chunks[passage].id, ())
                                if translation in permitted), None)
            if passage is not None:
                units[index] = passage
        return units

    def _lexical(self, question: str, units: dict[int, int]) -> dict[int, float]:
        """BM25 over the search text plus BM25 over the header phrases, for chunks that can serve."""
        scores = self._index.scores(normalize.content_tokens(question))
        for index, score in self._headers.scores(phrases(question)).items():
            scores[index] = scores.get(index, 0.0) + score
        return {index: score for index, score in scores.items() if index in units and score > 0}

    def _curated_first(self, order: list[int], fused: dict[int, float]) -> list[int]:
        """Curated child content about as relevant as the best passage goes first, in its own order."""
        best = fused[order[0]]
        curated = [unit for unit in order if self.release.chunks[unit].content_type in CURATED_CONTENT
                   and fused[unit] >= CURATED_RATIO * best]
        return curated + [unit for unit in order if unit not in curated]

    @staticmethod
    def _book(chunk: Chunk) -> tuple[str, ...]:
        return chunk.source_ids or (chunk.document_id,)

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
