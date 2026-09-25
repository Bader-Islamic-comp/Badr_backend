# Preparing corpus data

A **corpus** is a folder of documents that Robert may answer from. The pipeline
checks it, cuts it into small searchable pieces (chunks) and writes a
**release**: a sealed folder the server loads. Nothing in a corpus reaches the
app until it has been built into a release. The full contract is
[`doc/rag-system.md`](../doc/rag-system.md), sections 3 to 5 and 8.

## Synthetic and real content

- **Synthetic** documents (`"synthetic": true`) are invented text for
  development. They may **only** be `app_help` or `orientation`: how to use the
  app, never religious teaching. The validator refuses anything else, because
  invented religious text must never look like a source.
- **Real** religious content (`quran`, `hadith`, `tafsir`, `fiqh`, `dua`,
  `lesson`, `story`) must be non-synthetic, with full source details (work,
  edition, publisher, licence; a grading for hadith; a reference on every
  Qur'an unit). It is only served to children once it is **approved** by the
  scholarly board (`review.status: approved`, with the reviewer and the date).
  Drafts can be built and tested by adults but are never shown in the app.

`dev-app-help/` is the synthetic development corpus. It is not reviewed and not
for children.

## Folder layout

```
corpus/<corpus-id>/
  corpus.json        {"schemaVersion": 1, "id": "<corpus-id>", "title": "...", "description": "..."}
  documents/         one document per file: <document-id>.json or <document-id>.md
  eval.json          optional test questions (see the end of this page)
```

Name each file after its document id. Keep a document in **one** form only: if
you convert `looks.md` to `looks.json`, delete or move the `.md` file.

## A document in JSON

```json
{
  "schemaVersion": 1,
  "id": "app-help-stars",
  "kind": "passage",
  "title": "How learning stars work",
  "language": "en",
  "ageBands": ["7-9", "10-11"],
  "contentType": "app_help",
  "madhhab": [],
  "curriculumPolicy": "dev-synthetic",
  "synthetic": true,
  "source": {"work": "Robert's guide", "edition": "dev-1", "publisher": "Companion development team",
             "translator": null, "license": "internal", "checksum": null},
  "grading": null,
  "review": {"status": "draft", "reviewer": null, "approvedOn": null, "supersedes": null},
  "units": [
    {"id": "u1", "text": "You earn learning stars by finishing lessons.", "reference": "part 1",
     "section": "Earning stars", "keepWithNext": false}
  ]
}
```

- `kind` is `passage` (a text made of **units**) or `answer` (a reviewed
  answer: `questions`, 1 to 12 ways a child might ask, and one `answer`,
  instead of `units`).
- A **unit** is one paragraph, verse, narration, or ruling with its
  qualification. Units are never cut in half. `keepWithNext: true` keeps a unit
  in the same chunk as the one after it (for example a question and its
  answer). A chunk never mixes two `section`s.
- `language`: `en` or `ar`. `ageBands`: any of `5-6`, `7-9`, `10-11`, `12-14`.
- Text is kept exactly as written; only spaces at the start and end are
  removed.

## The same kind of document in Markdown

```markdown
---
schemaVersion: 1
id: app-help-looks
kind: passage
title: Choosing a look for Robert
language: en
ageBands: 7-9, 10-11
contentType: app_help
curriculumPolicy: dev-synthetic
synthetic: true
source.work: Robert's guide
source.edition: dev-1
source.publisher: Companion development team
source.license: internal
review.status: draft
---

## The looks

Open the Style tab to see the looks Robert can wear. {ref: looks 1}

When you have enough stars, choose a look and wear it. {ref: looks 2} {keep-with-next}

A new look changes Robert's colours. His face stays the same. {ref: looks 3}
```

- Between the `---` lines: one `key: value` per line, no quotes. Lists are
  separated by commas. `source.work:` fills `work` inside `source`. Leave a
  value empty (or write `null`) when it is unknown.
- `## Heading` starts a section. Other headings (`#`, `###`) and bullet lists
  are not allowed.
- Each paragraph (separated by a blank line) is one unit. Lines of one
  paragraph are joined with spaces. `{ref: ...}` and `{keep-with-next}` go at
  the **end** of a paragraph.
- An answer document has `kind: answer`, a line like
  `questions: How do I earn stars? | How can I get more stars?`, and the answer
  as the text below. It has no headings or markers.

Errors in a Markdown file give the line number. To turn Markdown into JSON:

```powershell
.venv/Scripts/python.exe -m companion_api.rag.pipeline import-markdown corpus/my-corpus/drafts corpus/my-corpus/documents
```

It writes nothing if any file has an error, and never overwrites a file unless
you add `--overwrite`.

## What the validator checks

**Errors** stop a build; **warnings** are advice.

1. Every required field is present and has the right type; ids use lowercase
   letters, digits and `-`; no two documents share an id; no two units in a
   document share an id; no text is empty; a passage has units and an answer
   has questions and an answer. Misspelled field names are errors, with a
   suggestion.
2. Synthetic documents are only `app_help` or `orientation`.
3. Real documents name the work, edition, publisher and licence. Hadith have a
   grading. Every Qur'an unit has a reference.
4. An approved document names its reviewer and an approval date like
   `2026-09-25`.
5. Two units or answers with the same text (ignoring case and punctuation) are
   an error; nearly the same text is a warning. The same question in two
   answer documents is an error.
6. A unit longer than the chunk budget (180 words by default) is a warning: it
   becomes one large chunk rather than being cut.

Also: a reviewed answer can be at most 1200 characters (the app shows it as it
is), `keepWithNext` may not point into a new section, and text that looks like
another language than the document's `language` is a warning.

Each line of the report reads `severity  file[:line] [document] field: message`.
`units[u3]` means the unit with id `u3`; `questions[#2]` means the second
question. The report names fields but never repeats your text.

## Running the pipeline (PowerShell, from the `comp-server` folder)

```powershell
# Check a corpus. Exit code 1 means there are errors. Add --json for a machine-readable report.
.venv/Scripts/python.exe -m companion_api.rag.pipeline validate corpus/dev-app-help

# Build a release offline, without a model server (development only).
.venv/Scripts/python.exe -m companion_api.rag.pipeline build corpus/dev-app-help --out releases --embedding-model hashing

# Build with the real embedding model: Ollama running on this machine with qwen3-embedding:0.6b available.
.venv/Scripts/python.exe -m companion_api.rag.pipeline build corpus/dev-app-help --out releases

# Check a release and show what is in it.
.venv/Scripts/python.exe -m companion_api.rag.pipeline verify releases/<release-id>
.venv/Scripts/python.exe -m companion_api.rag.pipeline stats releases/<release-id>
```

- The release id defaults to `<corpus-id>-<UTC date and time>`; choose one with
  `--release-id`. A release is never overwritten: a rebuild needs a new id.
- `--embedding-model hashing` needs no model server. It is for development: the
  server must then run with `COMPANION_EMBEDDING_MODEL=hashing` too, because a
  release can only be searched with the embedder that built it.
- The embedding server defaults to `COMPANION_EMBEDDING_BASE_URL`, then
  `COMPANION_LLM_BASE_URL`, then `http://127.0.0.1:11434/v1`. Only this machine
  or a private network address is accepted.
- `--channel published` is refused unless every document is approved and not
  synthetic.
- `releases/` is not stored in git. The build prints counts and ids, never
  document text.

## Test questions (`eval.json`)

```json
{"schemaVersion": 1, "cases": [
  {"id": "stars-1", "question": "How do I earn stars?",
   "expect": {"answerTypes": ["grounded", "reviewed_answer"], "documents": ["app-help-stars"]}},
  {"id": "outside-1", "question": "What is the capital of France?", "expect": {"answerTypes": ["abstained"]}}
]}
```

`answerTypes` lists the acceptable kinds of reply: `grounded`,
`reviewed_answer`, `abstained`, `redirected`, `safety`, `chat` (Robert's casual reply,
with no documents) or `unavailable`.
`documents` lists the documents a good answer should come from; they must
exist in the corpus, and `validate` checks this. Keep questions short,
realistic for a child, and never graphic.
