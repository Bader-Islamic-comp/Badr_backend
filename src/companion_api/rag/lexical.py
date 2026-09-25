"""BM25 over chunk search text (doc/rag-system.md §6.2).

Lexical matching is the half of hybrid retrieval that cannot hallucinate
similarity: a hit means the question and the passage share a meaningful word.
That is also why "no lexical hit" is half of the weak-evidence test.
"""
from collections import Counter, defaultdict
import math
from typing import Iterable, Sequence

from . import normalize
from .types import Chunk

K1 = 1.5
B = 0.75


def chunk_tokens(chunk: Chunk) -> list[str]:
    """What a chunk is indexed under.

    Answer-bank chunks are also found by their reviewed question phrasings.
    The pipeline's search text already covers them (§4); a phrasing it does
    not cover is added, and one it does is not counted twice.
    """
    tokens = normalize.content_tokens(chunk.search_text)
    for question in chunk.questions:
        if normalize.search_text(question) not in chunk.search_text:
            tokens.extend(normalize.content_tokens(question))
    return tokens


class BM25:
    """Okapi BM25 with a Lucene-style non-negative IDF."""

    def __init__(self, documents: Sequence[Sequence[str]], k1: float = K1, b: float = B):
        self.k1, self.b = k1, b
        self._frequencies = [Counter(document) for document in documents]
        self._lengths = [len(document) for document in documents]
        self._average = (sum(self._lengths) / len(documents)) if documents and sum(self._lengths) else 1.0
        self._postings: dict[str, list[int]] = defaultdict(list)
        for index, frequencies in enumerate(self._frequencies):
            for token in frequencies:
                self._postings[token].append(index)
        count = len(documents)
        self._idf = {token: math.log(1 + (count - len(rows) + 0.5) / (len(rows) + 0.5))
                     for token, rows in self._postings.items()}

    def __len__(self) -> int:
        return len(self._frequencies)

    def scores(self, query: Iterable[str]) -> dict[int, float]:
        """Scores for every document sharing at least one query token."""
        scores: dict[int, float] = defaultdict(float)
        for token in set(query):
            idf = self._idf.get(token)
            if idf is None:
                continue
            for index in self._postings[token]:
                frequency = self._frequencies[index][token]
                norm = self.k1 * (1 - self.b + self.b * self._lengths[index] / self._average)
                scores[index] += idf * frequency * (self.k1 + 1) / (frequency + norm)
        return dict(scores)

    def top(self, query: Iterable[str], k: int, allowed: Iterable[int] | None = None) -> list[tuple[int, float]]:
        """The best `k` positive-scoring documents, highest first, ties by index."""
        scores = self.scores(query)
        if allowed is not None:
            permitted = set(allowed)
            scores = {index: score for index, score in scores.items() if index in permitted}
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [(index, score) for index, score in ranked[:k] if score > 0]
