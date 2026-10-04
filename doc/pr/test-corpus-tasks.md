# test/corpus-tasks: the review's recommendations, Tafsir Ibn Kathir and a knowledge graph

Branch `test/corpus-tasks` (server, on `corpus-tasks`) and `test/corpus-tasks` (app, 1 commit on
`corpus-tasks`). Git branch names cannot hold ": " or spaces, so "test: corpus-tasks" became
`test/corpus-tasks`. For the team's review; nothing here is approved or child-facing.

## Competition package in the app (2026-10-04)

`corpus-tasks-2`'s package (`corpus/competition-ar`) is built into wave 1 as 43 `comp-*` documents and served by
the app. Review by owner:

| Owner | Look at | Decide |
| --- | --- | --- |
| Scholarly board | the 10 `needs_check` items and the `evidence_status` marks in `corpus/competition-ar/content.json` | Approve the fixed wordings (evening dhikr, «تباركت ذا الجلال», adam-01, isa-01) and replace the mismatched Dorar links |
| Governance owner | `quranpedia-mushaf-hafs` (candidate) | Clearing it lets the 9 Quranic supplications and the three surahs into releases |
| Safeguarding / child editor | `rag/curated.py` cue lists; the verbatim replies | Extend the occasion cues children really use |
| Pipeline owner | `rag/retriever.py` (`hybrid-rrf-v3`), `rag/checks.py` (`checks-v3`), `rag/curated.py` | The 0.9 curated-first ratio; the remaining judge rejections of the Prophet ﷺ story question |

## Reference package (2026-10-02)

The challenge's reference package «المرجعية والحزمة العلمية والبيانات» (20/3/1448) lists the approved sources and
a binding output standard; the organizers allowed participants to use the sources (reported by the product owner,
written confirmation pending). Three agents built this increment in parallel branches, merged here. Everything new
is `candidate`: nothing reaches a release until governance decides.

| Owner | Look at | Decide |
| --- | --- | --- |
| Governance owner | `doc/governance/reference-package.md` (open questions Q1–Q8, the rulings format), `doc/governance/data-request.md`, the Quranpedia and Jamharah rows of `doc/governance/rights-clearance.md` | Send the data request (Dorar is closed to scripts); record the organizers' rulings and the written permission |
| Scholarly board | `corpus/reports/quran_text_comparison.md`; the borderline tafsirs (al-Tabari d. 310 AH, al-Nasa'i, al-Sahih al-Masbur, al-Mukhtasar's English); `scripts/graph_query.py ayah 2:30`; the page-7 terms and `sense: differs/unclear` marks in `corpus/glossary_cross_lingual.yaml`; `corpus/reports/hadith_dorar_check.csv` (verify 100 hadith by hand) | Switch the displayed Quran text to the King Fahd Complex text? Stop showing the opening basmala inside ayah 1 of 112 surahs; the 3 word-division ayat |
| Safeguarding (native speaker) | `DISCLOSURE*` and `QURAN_CORRECTION*` copy in `rag/responses.py`; the Arabizi and disclosure patterns in `rag/arabic_rules.py` | Approve or rewrite the new copy |
| Pipeline owner | `rag/checks.py`, `rag/scene.py`, `rag/ayahs.py`, `rag/data/episodes.json` (our own source-map ranges and labels only), `scripts/replay_checks.py`, `FAITH_SYSTEM_EN` in `rag/prompts.py` | Whether the deterministic checks and their thresholds are right; how English is served (one service is one language today) |

**Results.**
- Replay of the 13 answers released on 2026-10-01: the 3 wrong ones now fail a check (`answered:no_quantity`,
  `addressee:mismatch`, `scene:absent_person`) and the 10 right ones pass.
- No Arabizi gold question reaches casual chat (8 before), and all 10 "are you a person or a sheikh?" questions
  get the disclosure.
- Misquote probes: 0 of 130 exact quotations and 0 of 539 eval questions wrongly corrected; 119 of 130 altered
  quotations caught.
- Tests: 824 passed.
- Real model (Qwen3.5-9B, 2026-10-02):
  - Arabic, the same 145 questions as before: 12 released, 11 right (before: 13 and 10). The three earlier misses
    are withheld; one new wrong answer (yusuf-07-msa).
  - Arabic, 27 new questions: 6 released, 2 right. The wrong ones: yusuf-15 (a number not in the source, now
    withheld by `checks-v2` `numbers`), yusuf-12 (wrong scene), yusuf-13 (meaning inverted), page6-sabr
    (non-answer).
  - English, first time: 8 of 75 released, 5 right, 1 out of order, 2 wrong. It was measured on a scratch
    release; translations stay `candidate`.
  - Safety, both languages: distress 16/16, personal data 15/15, injection 20/20, rulings 24/25 (+1 abstained),
    disclosure 10/10; no fabricated hadith answered.
  - The remaining wrong answers are errors of meaning that only a stronger judge or human review would catch:
    the case for a second-family judge model (doc/governance/reference-package.md, gap 4).

**Known limits.**
- The scene check covers the five Wave 1 stories; the answered check accepts any number, not only the right one;
  misquote detection reads Arabic ayat only.
- English translations keep their footnote markers (e.g. "[582]") inside the text.
- Layer 0 is 2.8 times larger (about 231 MB, 4 minutes to build).
- Gaps of the page-5 standard listed in `doc/governance/reference-package.md`: no grading in returned sources, no
  "scholars differ" reply, no AI notice in answers, no written privacy policy, no route for judging people or
  groups.

```bash
python scripts/fetch_sources.py && python scripts/build_corpus.py && python scripts/build_graph.py
python scripts/check_reference_package.py
python scripts/replay_checks.py <recorded gen_eval jsonl>
python scripts/eval_serving.py releases/<wave1 release>
```

## What to review, by owner

| Owner | Look at | Why |
| --- | --- | --- |
| Safeguarding (native Arabic speaker) | `src/companion_api/rag/arabic_rules.py`, the Arabic copy in `src/companion_api/rag/responses.py` | Every Arabic and Arabizi safety pattern and every Arabic reply is a draft by the developer |
| Scholarly board | `doc/knowledge-graph.md`, `corpus/reports/knowledge_graph.md`, `scripts/graph_query.py` | The graph's links between ayat, Ibn Kathir, hadith and prophets; `STORY_IN` comes from the source maps under review |
| Governance owner (Mousa al-Rashdan) | `corpus/governance/signers.yaml`, `.github/CODEOWNERS`, `doc/decisions/README.md`, the Ibn Kathir rows of `doc/governance/rights-clearance.md` | Signed decisions need the deciders' keys and a code-owner rule; Ibn Kathir's licence is unknown (`candidate`) |
| Pipeline owner (Momen Alhamza) | `rag/prompts.py` (`FAITH_SYSTEM`), `rag/grounding.py` (v3), `rag/judge.py`, `rag/arabizi.py`, `corpus/glossary_cross_lingual.yaml` | The answer path for religious passages; the glossary is model-proposed |

## Changes

1. **norm-v3** (`a0c3422`): the Uthmani rasm map applies to Quran text only, so شعير (barley) and شعائر
   (rituals), ثلث (a third) and ثلاث (three) are no longer merged in questions, hadith and app help.
2. **Arabic answering** (`0cb5063`): router `dev-patterns-v2` (Arabic and Arabizi safety, personal data,
   rulings, injection), replies in the child's language, `SAFETY_ABUSE` that never sends a child back to a
   parent, the faith prompt `rag-answer-v3`, `grounding-v3` (verbatim quotations, no first person in a faith
   answer, Arabic-aware word matching), the faith judge `faith-judge-v1`, and Arabizi search.
3. **Signed decisions and audit anchors** (`20b770b`): a decision applies only from a commit SSH-signed by the
   person it names; the audit trails are checked against anchors outside them.
4. **Tafsir Ibn Kathir** (`2547efc`): 114 files registered as `candidate`, 1,911 sections over all 6,236 ayat
   in the canonical layer and layer 0; never in a release.
5. **Knowledge graph** (`fee0383`): `kg-v1`, 26,490 nodes and 24,541 edges, each with its method and
   status (`doc/knowledge-graph.md`).
6. **Serving evaluation** (`scripts/eval_serving.py`): the gold and harmful sets through the server's own
   routing and retriever.
7. **App** (`aa3c1c0`): verse ranges keep their order inside Arabic text.

## Results

Measured 2026-10-01 on release `wave1-preview-3` (wave 1, draft, `hashing` embedder) and local
Qwen3.5-9B. All questions are synthetic and pending review; "right" below is the developer's reading, not a
scholar's.

**Safety and routing, real model, all 151 harmful questions** (the 2026-09-30 run in parentheses):

| Category | Result |
| --- | --- |
| Distress (16) | 16 safeguarding replies (Arabic: 0 of 11; one self-harm message got a greeting) |
| Personal data (15) | 15 redirected (3 of 10) |
| Prompt injection (20) | 20 redirected, none followed (1 of 9) |
| Rulings (25) | 24 redirected, 1 abstained (5 of 18) |
| Fabricated hadith (15), prophet mix-ups (20) | no answer released |
| Out-of-corpus religious (25), out of scope (15) | abstained, or the Arabic "puzzled" line with no faith content |

**Gold questions, real model** (MSA, Gulf and Arabizi, 145): 13 answers released, 10 of them right by the
developer's reading: four quote the Quran word for word, six are hadith. 3 were wrong and passed the judge: a
quote from the wrong scene of Yusuf's story, Ibrahim's prayer presented as said to his father, and a non-answer
about how long Nuh called his people. On the same 83 MSA and Gulf questions the 2026-09-30 run released 4, one of
them right, and two narrated as Allah or Yusuf; no answer now speaks in the first person. Before release the
judge withheld 13 answers and the quotation check 5. Median answer time 1.3 s.

**Serving path, no model** (`scripts/eval_serving.py`, 310 gold questions): an expected passage reaches the
top four for 77 of 186 Arabic-script questions (78 before), and for 29 of 62 Arabizi questions (none before;
47 now reach the corpus at all). English questions still abstain: the corpus has no English text.

**Tests:** server 703 passed (647 before), app 137 passed (135 before).

## How to check

```bash
.venv/Scripts/python.exe -m pytest -q                                   # server
python scripts/fetch_sources.py && python scripts/build_corpus.py       # Ibn Kathir: 86 MB more on first run
python scripts/build_graph.py && python scripts/graph_query.py prophet yusuf
python scripts/build_release.py corpus/wave1 --release-id wave1-review-1 --actor "Your Name" --embedding-model hashing
python scripts/eval_serving.py releases/wave1-review-1
python scripts/apply_decisions.py --check && python scripts/verify_audit.py
flutter analyze && flutter test                                          # app
```

## Open questions for the team

- May the Ibn Kathir text (QUL resource 22, no stated licence) be used for the development index and the
  graph, and on what terms for a release?
- Who writes and reviews the Arabic safeguarding replies; and the grammatical gender of the Arabic copy?
- English questions to the Arabic corpus abstain: is licensed, reviewed English content in scope?
- The judge is the same model that writes the answers: is a second model, or a human sample, required before
  any child sees an answer?

🤖 Generated with [Claude Code](https://claude.com/claude-code)
