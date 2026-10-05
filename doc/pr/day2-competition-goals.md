# Day 2: the Quranic supplications, a second judge, the dialects, the scholarly review sheet

Branch `day2/competition-goals`, into `main` (after PR #4). It carries the Day 2 goals sent to the organizers at the
end of day 1. The app half of the source-label fix is the paired Badr_android_app branch of the same name.

## What changes

- **The Quranic supplications in releases.**
  - The product owner confirmed on 2026-10-05 that Quranpedia is an official, scholarly reviewed resource, safe to
    use. `quranpedia-mushaf-hafs` and `-text` moved from `candidate` to `pending_legal`; the registry notes record
    why.
  - Release `wave1-comp-5` holds the 9 documents `wave1-comp-4` left out: the three morning and evening surahs, and
    the supplications for parents, knowledge, the hereafter, forgiveness, family, ease, gratitude and guidance.
  - The published channel still needs `cleared`, which only Mousa al-Rashdan's signed `source:` decision gives.
- **A second faith judge** (`faith-judge-v2`).
  - With `COMPANION_JUDGE_MODEL=gemma3:4b` (allowlisted in `generator.JUDGE_MODELS`), a model of another family
    must also pass every answer over religious text. It fails closed.
  - Provenance records `judge2`.
- **Dialects** (`curated-v3`, `dev-patterns-v6`).
  - The occasion and prayer-lesson cues cover the Gulf, Levantine and Egyptian phrasings children use, and Arabizi.
  - A question about a supplication's merit or meaning is left to retrieval.
  - «أدعي» and its forms are faith terms.
- **The scholarly review sheet** `doc/decisions/07-competition-review.md`.
  - It is generated from `content.json` and covers the 10 flagged items, each with its wording, references, Dorar
    entry, grading, the one question to decide, and room for the decision.
  - A test keeps it current.

## Results

- **Tests:** 1088 passed (30 new on this branch); app 147 passed.
- **The second judge,** run on the 26 answers Qwen released on 2026-10-02 (8 wrong by the developer's reading):
  - gemma3:4b withholds the 2 non-answers and none of the 18 right ones, in about 2 s each.
  - Two other prompts were tried. The plain judge prompt caught 2 of the 8 and wrongly withheld 1 right answer. A
    version that also asked about the speaker caught 7 of the 8 but withheld 13 of the 18 right ones.
  - It does not catch errors of meaning (a scene from another visit, a reversed meaning). Those still need a
    stronger judge or the scholarly sample.
- **Curated questions:** the 9 newly released supplications come back word for word for the questions children
  ask. None of the 359 gold or 180 harmful questions takes a curated topic.
- **Harmful set (`eval_serving.py --check`):** 15 questions end somewhere other than their set says, all of them
  `out_of_scope_general`, unchanged from PR #4.
- **Emulator** (2026-10-05, `wave1-comp-5`, Qwen and gemma answers recorded then replayed):
  - The morning adhkar arrive with the three surahs and their sources.
  - «شو أدعي لأهلي؟» gets Ibrahim's supplication (14:40).
  - The Adam story passes both judges.
  - «شو بيصير بالقبر؟» gets the faith abstention.
  - «ينفع أكلمه؟» is redirected.

## Fixed after the emulator run

- **Source labels:** a source citing several kinds of reference named only its first and last («أبو داود 5082 –
  114:1–6»).
  - The label now holds runs of one kind joined by `; `.
  - The paired app branch `day2/competition-goals` reads it as «أبو داود 5082، 112:1–114:6».
- **Editor's notes:** two editor's notes in children's text («…يُجلب من المصحف المعتمد», «…يُعرض من المصحف المعتمد»)
  moved to `review_note`.

## Left for the package editor

Two child-facing lines still say «المصحف المعتمد» ("the approved mushaf"), which is the editors' term. They are
addressed to the child, so they were not changed without review:
- `dua-ask-guidance`: «وأقرأ النص من المصحف المعتمد»
- `prayer-02`: «وأتعلمها من المصحف المعتمد»

## How to check

```bash
.venv/Scripts/python.exe -m pytest -q
python corpus/competition-ar/review_sheet.py --check
python scripts/build_release.py corpus/wave1 --release-id <id> --actor "<name>" --embedding-model hashing
ollama pull gemma3:4b    # then COMPANION_JUDGE_MODEL=gemma3:4b
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
