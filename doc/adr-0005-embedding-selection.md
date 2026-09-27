# ADR 0005: Embedding model selection for Arabic and transliterated questions

Status: **proposed** (2026-09-27). No model is selected by this ADR. Owner: Momen Alhamza.
Task: [Embedding model selection, evaluated on Arabic and transliteration](https://app.clickup.com/t/z8q7hbct4k).

## Context

Children ask in dialect, with spelling mistakes, in Arabizi and in English with transliterated names,
while the corpus is classical Arabic (doc/plan.md components 2, 3 and 9). The development release uses
`qwen3-embedding:0.6b` (`doc/rag-system.md` §6.7), chosen before any Arabic measurement existed. plan.md
asks for the decision to be made on numbers: BM25 alone, BGE-M3, multilingual-e5-large, Qwen3-Embedding
and hybrid RRF (k = 60), with and without a reranker.

## Method

`python scripts/eval_retrieval.py [--ollama MODEL]` over `corpus/wave1` (1106 chunks: 184 parents and their
children, small-to-big collapsed to parents), with 310 synthetic gold questions (`corpus/eval/gold.jsonl`,
62 intents × 5 phrasings) and 60 unanswerable questions from `corpus/eval/harmful.jsonl` (outside the
corpus, fabricated-hadith requests, prophet mix-ups). Metrics: Recall@1/5/10, MRR, nDCG@10, by variant;
abstention = balanced accuracy of a top-score threshold, tuned on one half and measured on the other.
History and dashboard: `reports/retrieval/history.jsonl`, `reports/retrieval/index.html`.
**The questions are synthetic and pending review, so all numbers are provisional.**

## Results (run of 2026-09-27)

| method | R@1 | R@5 | R@10 | MRR | nDCG@10 | abstain (2-fold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 (norm-v2, headers) | 0.142 | 0.287 | 0.355 | 0.210 | 0.201 | 0.474 |
| dense: hashing (dev baseline) | 0.084 | 0.219 | 0.374 | 0.167 | 0.159 | 0.509 |
| hybrid RRF: bm25 + hashing | 0.113 | 0.306 | 0.413 | 0.206 | 0.201 | 0.509 |
| dense: nomic-embed-text (local, English-centric; not a candidate) | 0.013 | 0.052 | 0.161 | 0.060 | 0.050 | 0.493 |
| hybrid RRF: bm25 + nomic | 0.087 | 0.265 | 0.352 | 0.179 | 0.173 | 0.493 |

Recall@5 by variant, bm25: msa 0.516, misspelled 0.500, levantine 0.476, egyptian 0.400, gulf 0.381,
**arabizi 0.000, english_transliteration 0.000**.

## Not measured (blocked)

| candidate | why | needs |
| --- | --- | --- |
| BGE-M3 | disk 100% full (2.2 GB free) | `ollama pull bge-m3` (~1.2 GB) |
| Qwen3-Embedding-0.6B | same | `ollama pull qwen3-embedding:0.6b` (~0.6-1.2 GB) |
| multilingual-e5-large | not in the Ollama library; sentence-transformers not installed | ~2.2 GB + the library |
| bge-reranker-v2-m3 (with/without) | cross-encoder; sentence-transformers not installed | ~2.3 GB + the library |

Estimated time once ~8 GB are free: downloads 5-30 minutes depending on the link; on this CPU (12 cores,
no usable GPU) about 10-15 minutes per ~0.6B embedder (nomic-137M took 3 minutes), and 10-15 minutes for
the reranker over 370 questions × 30 candidates: **about 45-60 minutes of compute in total**. The harness
already supports `--ollama bge-m3` and `--ollama qwen3-embedding:0.6b`.

## Findings so far

1. Lexical retrieval cannot reach Arabizi or English questions at all (0.000), and those are 40% of the
   gold set. A multilingual dense model is required, so BM25 alone is ruled out.
2. An English-centric embedder (nomic) is near chance on Arabic; model choice matters more than fusion.
3. No configuration measured here gives a usable abstention threshold (balanced accuracy ≤ 0.51): the
   sufficiency gate cannot rely on these scores. It needs a multilingual model, a reranker, or both.
4. Hybrid RRF (k = 60) never hurts BM25's MSA recall and helps dialects when the dense branch is
   Arabic-aware (hashing: gulf 0.381 → 0.524).

## Decision (proposed)

Keep hybrid RRF k = 60 as the retrieval shape. **Do not select an embedding model yet.** Measure BGE-M3,
Qwen3-Embedding-0.6B, multilingual-e5-large and the reranker with this harness once the disk space is
available, and pick the best by MRR and Recall@5, weighted to Arabizi, English transliteration and
abstention. Any change of model means a new corpus release (`doc/governance/re-review-policy.md`,
`embedding_changed`).

## Consequences

The development default `qwen3-embedding:0.6b` stays unmeasured on Arabic until then. The gold set must
be reviewed (approval_status: pending) before any number here is used for a decision.
