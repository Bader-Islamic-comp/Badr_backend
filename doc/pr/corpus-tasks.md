# Corpus tasks: verified sources, structure-aware ingestion, governance tooling and retrieval evaluation

## Summary

This branch works through the 15 corpus tasks (ClickUp lists *Corpus · Governance* and *Corpus ·
Pipeline & Evaluation*) on top of the existing development RAG, reusing its release, manifest and
config formats rather than building a parallel system. It adds a source registry with sha256
verification, a canonical Quran/tafsir/hadith layer rebuilt from registered downloads, chunk-v2
ingestion for the full canonical layer and the wave-1 candidate set, immutable releases with
rollback, a hash-chained audit trail, a signed-decision path for every human approval, evaluation
sets, a retrieval dashboard and an embedding comparison.

The aim is to make every remaining step a human decision rather than engineering work. Nothing is
approved, cleared or reviewed by this PR: all content is draft or candidate, every source licence is
`pending_legal`, and approvals can only come from a named person through
`doc/decisions/decisions.yaml`. The automated part of every task is complete (58.7 of 58.7 possible
points); the human part (41.3 points) is packaged in `doc/decisions/` so each owner can decide in
minutes.

## What's included

Evidence paths are relative to the repository root. Rebuild commands: [`doc/SETUP.md`](../SETUP.md).

1. **[Define corpus scope and an explicit out-of-scope list](https://app.clickup.com/t/z8q7hbct49)** —
   scope and out-of-scope draft. `doc/governance/scope.md`.
2. **[Source selection and provenance policy](https://app.clickup.com/t/z8q7hbct4a)** — 15 registered
   sources with sha256, verified fetch, policy draft. `corpus/sources/registry.yaml`,
   `scripts/fetch_sources.py`, `doc/governance/source-policy.md`, `tests/test_corpusprep.py`.
3. **[Rights clearance for every candidate source](https://app.clickup.com/t/z8q7hbct4b)** — rights
   table with the terms verbatim, a licensing package with five draft permission emails (none sent).
   `doc/governance/rights-clearance.md`, `scripts/rights_table.py`, `doc/decisions/01-licensing.md`.
4. **[Reviewer qualification and conflict-of-interest policy](https://app.clickup.com/t/z8q7hbct4c)** —
   policy draft enforced in code; reviewer list intentionally empty. `doc/governance/reviewer-policy.md`,
   `corpus/governance/reviewers.yaml`, `doc/decisions/02-reviewers.md`.
5. **[Immutable corpus releases with rollback](https://app.clickup.com/t/z8q7hbct4d)** — read-only
   releases, `current_release` pointer, one-step rollback, quarantine; the published channel needs
   every source `cleared`. `scripts/build_release.py`, `scripts/rollback.py`,
   `src/companion_api/governance/releases.py`, `doc/governance/releases.md`.
6. **[Review workflow tooling and admin UI](https://app.clickup.com/t/z8q7hbct4e)** — review CLI and
   signed-decision application; the admin interface is documented, not built. `scripts/review.py`,
   `scripts/apply_decisions.py`, `doc/governance/review-workflow.md`, `tests/test_decisions.py`.
7. **[Audit trail for every approval](https://app.clickup.com/t/z8q7hbct4f)** — hash-chained,
   append-only logs that detect edits, deletions and reordering. `src/companion_api/governance/audit.py`,
   `scripts/verify_audit.py`.
8. **[Re-review cadence and change triggers](https://app.clickup.com/t/z8q7hbct4h)** — policy draft and a
   tool that lists what is due and why. `doc/governance/re-review-policy.md`, `scripts/due_for_review.py`.
9. **[Structure-aware ingestion and chunking](https://app.clickup.com/t/z8q7hbct4g)** — schema v2,
   chunk-v2, norm-v2 with a rasm map; layer 0 and wave 1; aliases, prophet source maps, the 40-hadith
   selection, 552 generated retrieval questions. `scripts/build_corpus.py`,
   `corpus/reports/ingest_summary.json`, `corpus/aliases.yaml`, `corpus/candidate/`.
10. **[Age-band adaptation, human-written and reviewed](https://app.clickup.com/t/z8q7hbct4j)** — schema,
    99 empty templates, checker, writing guide; no child text. `corpus/drafts/age_band/`, `scripts/age_band.py`.
11. **[Embedding model selection, evaluated on Arabic and transliteration](https://app.clickup.com/t/z8q7hbct4k)** —
    four models and the reranker measured by variant; ADR proposed with two options.
    `doc/adr-0005-embedding-selection.md`, `scripts/eval_retrieval.py`.
12. **[Gold question set with approved answers and expected citations](https://app.clickup.com/t/z8q7hbct4m)** —
    310 synthetic questions with resolved expected chunks, pending review. `corpus/eval/gold.jsonl`,
    `scripts/build_eval.py`.
13. **[Harmful and out-of-scope question set](https://app.clickup.com/t/z8q7hbct4n)** — 151 questions in
    eight categories with expected routes, pending review. `corpus/eval/harmful.jsonl`.
14. **[Retrieval quality metrics dashboard](https://app.clickup.com/t/z8q7hbct4q)** — offline page with
    history, variants, worst 20 and the progress score. `reports/retrieval/index.html`,
    `reports/retrieval/history.jsonl`.
15. **[Enforce: no child content in the vector store](https://app.clickup.com/t/z8q7hbct4r)** — single
    writer gate, schema refusal, conversation-indexing test, index scan. `src/companion_api/rag/release.py`,
    `scripts/scan_index.py`, `tests/test_no_child_content.py`.

## Key numbers

| | |
| --- | --- |
| Quran | 114 surahs, 6,236 ayat; verified against two references |
| Hadith records | Bukhari 7,580 · Muslim 7,360 · Nawawi 42 · Riyad as-Salihin 1,896 · al-Adab al-Mufrad 1,326 |
| Cross-check (match / contained / text differs / not matched) | Bukhari 6,848 / 532 / 133 / 67 · Muslim 3,806 / 3,491 / 54 / 9 · Nawawi 38 / 0 / 4 / 0; Riyad and Adab single-source |
| Eligible for wave 1 | Bukhari 7,380 · Muslim 7,297 |
| Chunks | layer 0: 16,220 documents, 28,560 chunks · wave 1: 184 documents, 1,106 chunks |
| Tests | 634 passed (539 before) |
| `progress_score.py` | **58.7 / 100** — automated 58.7 of 58.7, human 0 of 41.3 |
| `check_progress.py` | 0 conflicts |

Retrieval (310 synthetic gold questions, Recall@5 / MRR):

| method | R@5 | MRR |
| --- | ---: | ---: |
| BM25 | 0.287 | 0.210 |
| hybrid RRF: BM25 + Qwen3-Embedding-0.6B | 0.610 | 0.437 |
| hybrid + bge-reranker-v2-m3 (top 10), Qwen3 | **0.661** | **0.538** |
| hybrid RRF: BM25 + BGE-M3 | 0.568 | 0.417 |
| hybrid RRF: BM25 + multilingual-e5-large | 0.506 | 0.345 |
| dense BGE-M3 **+q** (with generated retrieval questions) | 0.884 | 0.746 |

**The "+q" numbers are probably inflated:** the retrieval questions and the gold questions were written
by the same author, so they share phrasing. The rows without "+q" are the fair comparison. BM25 scores
0.000 on Arabizi and English questions (40% of the set). Details by variant: ADR 0005.

## Design decisions

- **Layers.** Layer 0 is the full canonical text, verified by sha256 and rebuilt by script; wave 1 is
  the first child-facing candidate set; age-band text is a separate, human-written layer.
- **Quote by reference.** Git holds references (`quran:2:255`, `bukhari:13`), numbers and sha256, not
  copied passages; verbatim text lives only in the rebuilt `corpus/canonical` and releases. The only
  exceptions are short: the 5–6 word search anchors in `hadith_selection.yaml` and the attributed
  word-level rasm map (`src/companion_api/rag/data/rasm_map.tsv`, from Tanzil). A history-wide scan
  found no run of 8 or more canonical words anywhere in the branch. Child
  drafts are checked for embedded Quran or hadith text.
- **`ai_prereview` is not an approval.** An independent reviewer agent with no shared context writes
  pass/flag/fail to its own folder; it unlocks nothing.
- **Signed human decisions only.** `approved`/`cleared` are written only by `apply_decisions.py` from a
  named, dated entry in `decisions.yaml`, checked against the reviewer list and role.
- **Immutable releases.** A release directory never changes; serving moves a pointer; rollback is one
  step and quarantine is permanent.
- **Hash-chained audit.** Every review event and release change is appended to a chain that
  `verify_audit.py` checks end to end.

## What is intentionally NOT in this PR

- **Licensed and sacred text** (`corpus/raw`, `corpus/canonical/**/*.jsonl`, `corpus/layer0`,
  `corpus/wave1`, `releases/`, `doc/decisions/04-content-review.md`): every licence is `pending_legal`
  and the repository is public. All of it is rebuilt from registered downloads with `fetch_sources.py`,
  `build_corpus.py`, `build_release.py` and `build_decision_packages.py`.
- **Children's text:** age-band versions must be written and reviewed by people (task 10).
- **The admin UI:** a CLI and a documented interface only; building the UI is a product decision.
- Model caches and embedding vectors (`reports/retrieval/cache/`).

## How to verify

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[test]' -c constraints-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/fetch_sources.py
.venv/bin/python scripts/build_corpus.py
git status                                   # only timing fields in corpus/reports/ingest_summary.json
.venv/bin/python scripts/build_release.py corpus/wave1 --release-id wave1-dev-1 --actor "Your Name" --embedding-model hashing --promote
.venv/bin/python scripts/scan_index.py releases/current_release
.venv/bin/python scripts/verify_audit.py
.venv/bin/python scripts/eval_retrieval.py
.venv/bin/python scripts/apply_decisions.py --check
.venv/bin/python scripts/check_progress.py
.venv/bin/python scripts/progress_score.py
```

## Human decisions required

| who | what | package |
| --- | --- | --- |
| Mousa al-Rashdan | licences for the 15 sources (and whether to send the draft emails) | `doc/decisions/01-licensing.md` |
| Mousa al-Rashdan | name and approve the reviewers | `doc/decisions/02-reviewers.md` |
| Mousa al-Rashdan | approve the seven policy drafts | `doc/decisions/03-policies.md` |
| Scholarly board | hadith, prophet source maps and the 40-hadith selection (fail first) | `doc/decisions/04-content-review.md` (generated locally) |
| Momen Alhamza | approve or reject the gold and harmful questions | `doc/decisions/05-eval-review.md` |
| Momen Alhamza | accept ADR 0005: option A (Qwen3 + reranker) or B (BGE-M3) | `doc/adr-0005-embedding-selection.md` |
| Product owner | §18 decisions: age, market, curriculum, madhhab scope | `doc/decisions/06-section18.md` |

## Known issues

- Reviewer B fails, still open pending the scholarly decision: `quran:2:259` sits in Ibrahim's source
  map but is not about him; the gold questions on "removing harm from the road is charity" expect a
  chunk (the short version of Bukhari 2707) that does not mention the road (5 fails); the harmful set
  describes the fifty-prayers hadith as fabricated although it is authentic.
- The reranker ran in a reduced setting (top 10, three methods): the full setting is ~7 hours on CPU.
- All evaluation questions are synthetic and pending review; the "+q" gain is not yet trustworthy.
- Wave-1 search anchors in `corpus/candidate/hadith_selection.yaml` are short verbatim phrases (5–6
  words) used to locate each hadith.

## Risks and follow-ups

- No release can be published until the licences are cleared and reviewers are named.
- An independently written gold set is needed before choosing the embedding model.
- The reranker needs a latency budget (GPU or a smaller k) before it serves children.
- The release format is file-based; pgvector remains a separate task.
- Follow-ups: fix the reviewer B items once decided, run the evaluation in CI, and build the admin UI
  if the product owner decides to.
