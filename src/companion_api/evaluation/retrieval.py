"""Retrieval metrics over a corpus folder: BM25, dense embedders and hybrid RRF (k = 60).

A ranked list is collapsed to parent chunks (a child hit counts for its parent,
small-to-big), then scored against each gold question's expected parent ids:
Recall@1/5/10 (any expected id in the top k), MRR and nDCG@10 with binary
relevance. The abstention threshold is chosen on the top retrieval score to
separate gold questions (answerable) from harmful questions whose expected
route is `abstain`; it is tuned on one half and measured on the other (2-fold),
so the reported accuracy is not only in-sample.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Callable, Sequence

from ..rag import normalize
from ..rag.chunking import embedding_text
from ..rag.embeddings import cosine
from ..rag.lexical import BM25
from ..rag.types import Chunk

RRF_K = 60
BRANCH_K = 50
DEPTH = 100
ABSTAIN_CATEGORIES = ("out_of_corpus_religious", "fabricated_hadith_request", "prophet_mixup")


@dataclass
class Ranked:
    parents: list[str]   # parent ids, best first, deduplicated
    top_score: float     # the confidence used for abstention


def parent_of(chunk: Chunk) -> str:
    return chunk.parent_id if chunk.is_child else chunk.id


def bm25_index(chunks: Sequence[Chunk]) -> BM25:
    return BM25([normalize.content_tokens(chunk.context_header + " " + chunk.search_text) for chunk in chunks])


def _collapse(chunks: Sequence[Chunk], order: list[tuple[int, float]]) -> list[str]:
    seen, parents = set(), []
    for position, _ in order:
        parent = parent_of(chunks[position])
        if parent not in seen:
            seen.add(parent)
            parents.append(parent)
    return parents[:DEPTH]


class Method:
    """One retrieval configuration: `rank(question) -> Ranked`."""

    def __init__(self, name: str, chunks: Sequence[Chunk], *, bm25: BM25 | None = None,
                 vectors: list[list[float]] | None = None, embed_query: Callable[[str], list[float]] | None = None):
        self.name, self.chunks, self.bm25, self.vectors, self.embed_query = name, chunks, bm25, vectors, embed_query

    def _lexical(self, question: str) -> list[tuple[int, float]]:
        return self.bm25.top(normalize.content_tokens(question), BRANCH_K * 4)

    def _dense(self, question: str) -> list[tuple[int, float]]:
        query = self.embed_query(question)
        scored = sorted(((position, cosine(query, vector)) for position, vector in enumerate(self.vectors)),
                        key=lambda item: (-item[1], item[0]))
        return scored[:BRANCH_K * 4]

    def rank(self, question: str) -> Ranked:
        lexical = self._lexical(question) if self.bm25 is not None else None
        dense = self._dense(question) if self.vectors is not None else None
        if lexical is not None and dense is not None:
            fused: dict[int, float] = {}
            for branch in (lexical[:BRANCH_K], dense[:BRANCH_K]):
                for rank, (position, _) in enumerate(branch, 1):
                    fused[position] = fused.get(position, 0.0) + 1 / (RRF_K + rank)
            order = sorted(fused.items(), key=lambda item: (-item[1], item[0]))
            return Ranked(_collapse(self.chunks, order), dense[0][1] if dense else 0.0)
        order = lexical if lexical is not None else dense
        return Ranked(_collapse(self.chunks, order), order[0][1] if order else 0.0)


def metrics_for(ranked: Ranked, expected: Sequence[str]) -> dict:
    expected = set(expected)
    first = next((rank for rank, parent in enumerate(ranked.parents, 1) if parent in expected), None)
    gains = [1.0 if parent in expected else 0.0 for parent in ranked.parents[:10]]
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, 1))
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(expected), 10) + 1))
    return {"rank": first, "r1": float(first == 1), "r5": float(bool(first and first <= 5)),
            "r10": float(bool(first and first <= 10)), "mrr": 1 / first if first else 0.0,
            "ndcg10": dcg / ideal if ideal else 0.0}


def _mean(rows: list[dict], key: str) -> float:
    return round(sum(row[key] for row in rows) / len(rows), 4) if rows else 0.0


def summarize(rows: list[dict]) -> dict:
    return {key: _mean(rows, key) for key in ("r1", "r5", "r10", "mrr", "ndcg10")} | {"n": len(rows)}


def _best_threshold(positive: list[float], negative: list[float]) -> tuple[float, float]:
    scores = sorted(set(positive) | set(negative))
    # Midpoints between neighbouring scores, so the threshold does not sit on a tuning sample.
    candidates = [scores[0] - 1e-9] + [(a + b) / 2 for a, b in zip(scores, scores[1:])] + [scores[-1] + 1e-9]
    best = (candidates[0], 0.0)
    for threshold in candidates:
        tpr = sum(score >= threshold for score in positive) / len(positive)
        tnr = sum(score < threshold for score in negative) / len(negative)
        balanced = (tpr + tnr) / 2
        if balanced > best[1]:
            best = (threshold, balanced)
    return best


def abstention(positive: list[float], negative: list[float]) -> dict:
    """Balanced accuracy of `answer if top score >= t`, t tuned on one half and applied to the other."""
    if not positive or not negative:
        return {}
    folds = []
    for fold in (0, 1):
        tune_p, test_p = positive[fold::2], positive[1 - fold::2]
        tune_n, test_n = negative[fold::2], negative[1 - fold::2]
        threshold, _ = _best_threshold(tune_p, tune_n)
        answered = sum(score >= threshold for score in test_p) / len(test_p)
        abstained = sum(score < threshold for score in test_n) / len(test_n)
        folds.append({"threshold": threshold, "answered_answerable": answered, "abstained_unanswerable": abstained,
                      "balanced_accuracy": (answered + abstained) / 2})
    threshold, in_sample = _best_threshold(positive, negative)
    return {"threshold_all_data": round(threshold, 4), "balanced_accuracy_in_sample": round(in_sample, 4),
            "balanced_accuracy_2fold": round(sum(f["balanced_accuracy"] for f in folds) / 2, 4),
            "answered_answerable_2fold": round(sum(f["answered_answerable"] for f in folds) / 2, 4),
            "abstained_unanswerable_2fold": round(sum(f["abstained_unanswerable"] for f in folds) / 2, 4)}


def evaluate(method: Method, gold: list[dict], harmful: list[dict]) -> dict:
    per_question, positive = [], []
    for item in gold:
        ranked = method.rank(item["question"])
        scores = metrics_for(ranked, item["expected_chunk_ids"])
        per_question.append({"id": item["id"], "variant": item["variant"], **scores})
        positive.append(ranked.top_score)
    negative = [method.rank(item["question"]).top_score for item in harmful
                if item["category"] in ABSTAIN_CATEGORIES]
    variants = sorted({row["variant"] for row in per_question})
    return {"overall": summarize(per_question),
            "by_variant": {variant: summarize([r for r in per_question if r["variant"] == variant])
                           for variant in variants},
            "abstention": abstention(positive, negative), "per_question": per_question}


def cached_vectors(cache: Path, name: str, texts: list[str], embed: Callable[[list[str]], list[list[float]]]):
    """Document vectors for `texts`, cached by model name and text digest (the corpus is re-embedded only on change)."""
    digest = sha256("\x1f".join(texts).encode("utf-8")).hexdigest()[:16]
    path = cache / f"{name}-{digest}.json"
    if path.is_file():
        return json.loads(path.read_text())
    vectors = embed(texts)
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vectors))
    return vectors


def document_texts(chunks: Sequence[Chunk]) -> list[str]:
    return [embedding_text(chunk) for chunk in chunks]
