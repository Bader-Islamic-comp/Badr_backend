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

## Results (run of 2026-09-27T22:15Z, commit 3deca79 + working tree)

All four requested models ran locally: `qwen3-embedding:0.6b` through Ollama; BGE-M3 and multilingual-e5-large
through transformers (float32, CLS pooling for BGE-M3; Ollama's BGE-M3 returns NaN on this text). Passages
are clipped to 350 words for embedding. "+q" = the entry also carries the parent's retrieval questions
(`corpus/candidate/retrieval_questions.json`, 552, `generated: true`).

| method | R@1 | R@5 | R@10 | MRR | nDCG@10 | abstain (2-fold) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 | 0.142 | 0.287 | 0.355 | 0.210 | 0.201 | 0.474 |
| hybrid RRF: bm25 + hashing (dev baseline) | 0.113 | 0.306 | 0.413 | 0.206 | 0.201 | 0.509 |
| dense: qwen3-embedding:0.6b | 0.303 | **0.616** | **0.745** | **0.445** | **0.440** | **0.625** |
| hybrid: qwen3-embedding:0.6b | 0.293 | 0.610 | 0.739 | 0.437 | 0.432 | 0.625 |
| dense: bge-m3 | 0.255 | 0.513 | 0.687 | 0.379 | 0.360 | 0.604 |
| hybrid: bge-m3 | 0.290 | 0.568 | 0.690 | 0.417 | 0.394 | 0.604 |
| dense: multilingual-e5-large | 0.181 | 0.410 | 0.555 | 0.292 | 0.271 | 0.513 |
| hybrid: multilingual-e5-large | 0.210 | 0.506 | 0.655 | 0.345 | 0.336 | 0.513 |
| bm25 +q | 0.439 | 0.671 | 0.758 | 0.549 | 0.492 | 0.627 |
| dense: qwen3 +q | 0.435 | 0.752 | 0.865 | 0.572 | 0.543 | 0.702 |
| hybrid: qwen3 +q | 0.481 | 0.797 | 0.897 | 0.617 | 0.579 | 0.702 |
| dense: bge-m3 +q | **0.639** | **0.884** | 0.919 | **0.746** | **0.676** | **0.768** |
| hybrid: bge-m3 +q | 0.613 | 0.861 | **0.929** | 0.726 | 0.648 | 0.768 |
| dense: e5-large +q | 0.581 | 0.797 | 0.868 | 0.685 | 0.619 | 0.652 |
| hybrid: e5-large +q | 0.571 | 0.823 | 0.906 | 0.683 | 0.614 | 0.652 |

Recall@5 by variant (n: msa, misspelled, arabizi, english 62 each; egyptian 20, gulf 21, levantine 21 —
the dialect rows are small, read them as direction only):

| method | msa | misspelled | egyptian | gulf | levantine | arabizi | english translit. |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 | 0.516 | 0.500 | 0.400 | 0.381 | 0.476 | 0.000 | 0.000 |
| hybrid: qwen3 | 0.758 | 0.726 | 0.650 | 0.619 | 0.667 | 0.290 | 0.629 |
| hybrid: bge-m3 | 0.645 | 0.661 | 0.600 | 0.524 | 0.619 | 0.339 | 0.613 |
| hybrid: e5-large | 0.629 | 0.645 | 0.500 | 0.619 | 0.619 | 0.258 | 0.419 |
| bm25 +q | 0.806 | 0.839 | 0.650 | 0.809 | 0.762 | 0.726 | 0.242 |
| hybrid: qwen3 +q | 0.855 | 0.806 | 0.850 | 0.857 | 0.857 | 0.806 | 0.661 |
| dense: bge-m3 +q | 0.952 | 0.952 | 0.900 | 1.000 | 0.857 | 0.710 | 0.887 |
| hybrid: bge-m3 +q | 0.935 | 0.903 | 0.950 | 0.857 | 0.857 | 0.758 | 0.823 |

MRR by variant is in `reports/retrieval/history.jsonl` and on the dashboard.

### Reranker (bge-reranker-v2-m3)

Run of 2026-09-28T00:43Z. The cross-encoder rescores the **top 10** parents (`--rerank-k 10`), max 384
tokens, on three hybrid methods only (`--rerank-on`). The full setting (top 30 on all 8 methods = 24,394
pairs) measured 0.96 pairs/s on this CPU (i5-10500H, no GPU, float32), about 7 hours, so it was cut to
this. Reranking the top 10 cannot change R@10.

| method | R@1 | R@5 | MRR | nDCG@10 | abstain (2-fold) |
| --- | ---: | ---: | ---: | ---: | ---: |
| hybrid: qwen3 | 0.293 | 0.610 | 0.437 | 0.432 | 0.625 |
| hybrid: qwen3 + rerank | **0.429** | **0.661** | **0.538** | **0.494** | **0.679** |
| hybrid: bge-m3 | 0.290 | 0.568 | 0.417 | 0.394 | 0.604 |
| hybrid: bge-m3 + rerank | 0.384 | 0.584 | 0.484 | 0.435 | 0.658 |
| hybrid: bge-m3 +q | 0.613 | 0.861 | 0.726 | 0.648 | 0.768 |
| hybrid: bge-m3 +q + rerank | 0.558 | 0.836 | 0.678 | 0.618 | 0.660 |

Recall@5 by variant (msa / misspelled / egyptian / gulf / levantine / arabizi / english):
hybrid: qwen3 + rerank 0.823 / 0.726 / 0.550 / 0.762 / 0.762 / 0.371 / 0.694;
hybrid: bge-m3 + rerank 0.742 / 0.629 / 0.600 / 0.619 / 0.667 / 0.339 / 0.581;
hybrid: bge-m3 +q + rerank 0.935 / 0.887 / 0.800 / 1.000 / 0.905 / 0.694 / 0.758.

## Caveats that limit these numbers

1. **Leakage in "+q".** The retrieval questions and the gold questions were written by the same author
   (the agent), so "+q" rows are likely optimistic: bm25 jumps 0.287 → 0.671 R@5 from them alone. The
   rows without "+q" are the fair comparison of the embedders. An independently written gold set (or the
   human-reviewed one) is needed before the "+q" gain is trusted.
2. All questions are synthetic and `approval_status: pending`; the corpus is a draft wave-1 release.
3. The dialect variants have 20–21 questions each.

## Findings

1. A multilingual dense model is required: BM25 cannot reach Arabizi or English questions (0.000), 40% of
   the gold set. All three candidates lift overall R@5 from 0.29 to 0.51–0.62 without "+q".
2. **Without "+q", Qwen3-Embedding-0.6B is the strongest embedder** (MRR 0.445 dense, 0.437 hybrid), ahead
   of BGE-M3 (0.379 / 0.417) and e5-large (0.292 / 0.345), and it is also the smallest and already the
   development default.
3. **With "+q", BGE-M3 is strongest** (dense MRR 0.746, R@5 0.884) — but see caveat 1.
4. Hybrid RRF helps weaker dense branches (BGE-M3, e5) and is neutral for Qwen3 without "+q"; it never
   hurts much, and it keeps exact-phrase matches for MSA.
5. Arabizi stays the weakest variant for every embedder (0.26–0.34 without "+q"); retrieval questions in
   Arabizi are what lift it (0.71–0.81).
6. The reranker helps where first-stage ranking is weak: without "+q" it lifts MRR by 0.07–0.10 and
   R@1 by 0.09–0.14 (best fair configuration: **hybrid qwen3 + rerank, MRR 0.538, R@5 0.661**). On top of
   "+q" it slightly hurts (MRR 0.726 → 0.678), and it costs ~1 s per pair on CPU.
7. Abstention is still weak: best 2-fold balanced accuracy 0.768 (bge-m3 +q), 0.625 without "+q". The
   sufficiency gate cannot rely on a top-score threshold alone.

## Decision (proposed)

Keep hybrid RRF k = 60 as the retrieval shape and keep generating retrieval questions. **No model is
selected by this ADR**; the owner decides (decision `adr-0005` in `doc/decisions/decisions.yaml`). The
numbers point to two options:

- **A. Qwen3-Embedding-0.6B + bge-reranker-v2-m3 on the top 10** (current development default embedder):
  best on the fair comparison, smallest, no release change; the reranker needs a latency budget (GPU or
  a smaller k) before it serves children.
- **B. BGE-M3**: best with retrieval questions, especially English transliteration; a model change means a
  new corpus release (`embedding_changed`) and 2.3 GB served through transformers, not Ollama.

Recommendation: re-run this harness on the reviewed or independently written gold set first; if the
"+q" advantage of BGE-M3 survives, choose B, otherwise A.

## Consequences

Any change of model means a new corpus release (`doc/governance/re-review-policy.md`, `embedding_changed`).
The gold set must be reviewed before any number here is used for a final decision.
