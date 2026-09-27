"""Retrieval metrics (corpus tasks Phase 5). Synthetic placeholder data only."""
import json
from pathlib import Path

import pytest

from companion_api.evaluation import retrieval

ROOT = Path(__file__).resolve().parents[1]


def test_metrics_rank_mrr_and_ndcg():
    ranked = retrieval.Ranked(["a#1", "b#1", "c#1"], 1.0)
    scores = retrieval.metrics_for(ranked, ["b#1"])
    assert scores["rank"] == 2 and scores["r1"] == 0 and scores["r5"] == 1 and scores["mrr"] == 0.5
    assert scores["ndcg10"] == pytest.approx(1 / 1.5849625, rel=1e-6)
    miss = retrieval.metrics_for(ranked, ["z#1"])
    assert miss["rank"] is None and miss["mrr"] == 0 and miss["ndcg10"] == 0


def test_abstention_is_measured_out_of_sample():
    positive = [0.9, 0.8, 0.85, 0.95, 0.7, 0.75]
    negative = [0.1, 0.2, 0.15, 0.3, 0.25, 0.05]
    result = retrieval.abstention(positive, negative)
    assert result["balanced_accuracy_2fold"] == 1.0 and 0.3 < result["threshold_all_data"] <= 0.7
    assert retrieval.abstention([], negative) == {}


def test_eval_sets_are_synthetic_pending_and_large_enough():
    gold = [json.loads(line) for line in (ROOT / "corpus/eval/gold.jsonl").open(encoding="utf-8")]
    harmful = [json.loads(line) for line in (ROOT / "corpus/eval/harmful.jsonl").open(encoding="utf-8")]
    assert len(gold) >= 300 and len(harmful) >= 150
    assert all(item["synthetic"] and item["approval_status"] == "pending" for item in gold + harmful)
    assert all(item["expected_chunk_ids"] for item in gold)
    assert {item["expected_route"] for item in harmful} <= {"abstain", "redirect", "safety", "refuse"}
    assert len({item["variant"] for item in gold}) == 7
