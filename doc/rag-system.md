# RAG system and data pipeline

Status: implemented as a development increment on synthetic data (branch
`feature/rag-system-and-data-pipeline`, 2026-09-25). Nothing here is approved for
children. The scholarly, safeguarding, privacy and legal gates in
[`development-boundary.md`](development-boundary.md) are still open, and
[ADR 0003](adr-0003-grounded-answers-development.md) records the boundary for
this work and what still gates any child use;
[ADR 0004](adr-0004-casual-conversation.md) does the same for casual chat and
the faith-only rule ([`conversation-policy.md`](conversation-policy.md)). This
builds the machinery those gates will review, and it is **off by default**.

This document is the contract between the data pipeline, the answer runtime and
the Flutter client. Section numbers are referenced from code comments, so they
stay stable; later additions are new subsections or new sections at the end.
Where the implementation settled a detail the first draft left open, or
departed from it, the text below says what the code does and §12 records the
change and why.

## 1. Shape

```mermaid
flowchart LR
    subgraph Pipeline["Data pipeline (offline CLI)"]
        SRC["corpus/<name>/\ncorpus.json + documents/*.json"] --> VAL["validate"]
        VAL --> NORM["normalize\ncanonical ≠ search text"]
        NORM --> CHUNK["chunk by atomic units"]
        CHUNK --> EMB["embed\nqwen3-embedding:0.6b"]
        EMB --> REL["immutable release\nmanifest + chunks + vectors"]
    end
    subgraph Runtime["Answer runtime (API process)"]
        Q["child question"] --> ROUTE["router\n(safety, personal data,\nrulings, injection)"]
        ROUTE -- fixed reply --> OUT
        ROUTE -- other language --> ABST
        ROUTE -- retrieve --> RET["hybrid retrieval\nBM25 + dense, RRF"]
        RET -- reviewed answer match --> OUT
        RET -- weak evidence --> ABST["abstain"] --> OUT
        RET --> GEN["Qwen3.5-9B\ngrounded prompt"]
        GEN --> VER["grounding + output checks"]
        VER -- fail --> ABST
        VER --> OUT["turn: text, citations, sources"]
    end
    REL --> RET
```

Model inference is self-hosted: an OpenAI-compatible server (Ollama by default,
llama.cpp or vLLM also work) on this machine or a private network serves
`qwen3.5:9b` for generation and `qwen3-embedding:0.6b` for embeddings.
`rag/endpoints.py` refuses any other host, because sending a child's question to
a third-party provider is what the provider due-diligence gate decides.

## 2. Package layout

`src/companion_api/rag/`

| Module | Owner | Purpose |
|---|---|---|
| `types.py` | shared | `Chunk`, `ReleaseManifest`, `EmbedderIdentity`, `Embedder` and `Generator` protocols |
| `normalize.py` | shared | canonical vs search text, tokens, language detection, Arabic light stems (`norm-v3`) |
| `embeddings.py` | shared | `HashingEmbedder` (offline, deterministic), `OpenAICompatibleEmbedder` |
| `endpoints.py` | shared | private-endpoint guard |
| `release.py` | shared | write/load/verify immutable releases |
| `corpus.py` | pipeline | document schema, loading, validation report |
| `markdown.py` | pipeline | Markdown authoring format → document JSON |
| `chunking.py` | pipeline | unit-preserving chunker (`chunk-v1`) |
| `pipeline.py` | pipeline | `python -m companion_api.rag.pipeline` CLI |
| `lexical.py` | runtime | BM25 over search text |
| `retriever.py` | runtime | hybrid retrieval, filters, fusion, thresholds |
| `router.py` | runtime | deterministic input routing (development rules) |
| `responses.py` | runtime | fixed replies (development copy, awaiting review) |
| `prompts.py` | runtime | versioned grounded-answer prompt |
| `chat.py` | runtime | Robert's persona prompt and chat output checks ([conversation policy](conversation-policy.md)) |
| `generator.py` | runtime | OpenAI-compatible chat adapter for Qwen3.5-9B |
| `grounding.py` | runtime | citation parsing, support check, output safety |
| `service.py` | runtime | `AnswerService`: route → retrieve → generate → verify, and casual chat |
| `evaluate.py` | runtime | `python -m companion_api.rag.evaluate` eval harness |
| `ask.py` | runtime | `python -m companion_api.rag.ask` operator console |
| `checks.py` | runtime | the post-generation checks on faith answers, in order, judge last (§16) |
| `scene.py` | runtime | the scene check over the Wave 1 episode map, `data/episodes.json` (§16) |
| `ayahs.py` | runtime | a release's ayahs one by one; questions quoting an ayah with altered words (§16) |

Outside the package: `config.py` reads the §9 settings and `require_rag`
validates them; `store.py` holds the §6.5 queue and turn states; `schemas.py`
and `main.py` carry the §7 shapes and routes. `service.assemble` is the one
place a release, an embedder, a retriever and a generator are put together, so
the server, the evaluator and the operator console cannot disagree about them.

## 3. Corpus authoring format (schema v1)

A corpus is a directory:

```
corpus/<corpus-id>/
  corpus.json          {"schemaVersion": 1, "id": "<corpus-id>", "title": "...", "description": "..."}
  documents/*.json     one document per file (canonical form)
  documents/*.md       optional Markdown authoring form (§3.3), converted on load
  eval.json            optional evaluation cases (§8)
```

### 3.1 Document

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
  "source": {
    "work": "Robert's guide", "edition": "dev-1", "publisher": "Companion team",
    "translator": null, "license": "internal", "checksum": null
  },
  "grading": null,
  "review": {"status": "draft", "reviewer": null, "approvedOn": null, "supersedes": null},
  "units": [
    {"id": "u1", "text": "…", "reference": "part 1", "section": "Earning", "keepWithNext": false}
  ]
}
```

- `id`: `^[a-z0-9][a-z0-9-]{1,63}$`, unique across the corpus.
- `kind`: `passage` (units are retrieved and cited) or `answer` (reviewed
  answer-bank entry: `questions` — 1–12 phrasings — and `answer` replace
  `units`).
- `language`: `en` or `ar` for now. `ageBands`: any of `5-6`, `7-9`, `10-11`, `12-14`.
- `contentType`: `app_help`, `orientation`, `lesson`, `story`, `quran`,
  `tafsir`, `hadith`, `dua`, `fiqh`, `quran_translation` (an English translation
  of the meanings) and `tafsir_translation` (a translated tafsir); the last two
  are never `quran`, so the rasm map does not apply to them.
- **Units are atomic.** A unit is a verse, a narration, a ruling with its
  qualification, or a paragraph. The chunker never splits one, never crosses a
  `section` boundary, and never separates a unit marked `keepWithNext` from the
  unit after it.

### 3.2 Validation rules (errors fail the build)

1. Schema: required fields, types, id patterns, unique document ids, unique
   unit ids within a document, non-empty text, `units` xor `questions`+`answer`.
2. **Synthetic content is never religious.** `synthetic: true` requires
   `contentType` of `app_help` or `orientation`. Invented religious text is the
   one thing this pipeline must not make easy.
3. Non-synthetic documents require `source.work`, `source.edition`,
   `source.publisher` and `source.license`. `hadith` requires `grading`.
   `quran` requires a `reference` on every unit.
4. `review.status: "approved"` requires `review.reviewer` and an ISO
   `review.approvedOn`.
5. Duplicate detection: two units (or answers) whose search text is identical
   are an error; near-duplicates (token Jaccard ≥ 0.9) are a warning.
6. Oversized units (more than the chunk budget) are a warning, not a split.

The validation report lists `file`, `document`, `field`, `severity`, `message`
(and a `line` for Markdown and JSON syntax errors). It reports every problem in
one pass and names fields and ids but never quotes document text, so it can be
pasted into a ticket. Canonical text is never rewritten, only NFC-composed and
trimmed.

The pipeline also checks what the rules above leave implicit:

- **Errors:** an unknown field (with the closest allowed name, so a misspelling
  is caught instead of silently ignored); a key repeated in one JSON object; a
  file that is not UTF-8 or not valid JSON (with line and column); an item listed
  twice in a list; an empty `ageBands`; a `review.approvedOn` that is not an ISO
  date, whatever the status; `keepWithNext` on a unit whose next unit starts a
  new section; a reviewed answer over 1200 characters (it is returned verbatim
  as the turn text, §7); the same question phrasing twice in one answer or in two
  answer documents (each phrasing belongs to one reviewed answer); a document id
  used by two files, such as the `.md` and `.json` form of one document; a
  missing `corpus.json` or `documents/` folder, or no documents; and in
  `eval.json`, a duplicate or malformed case id, a question over the API's 2000
  characters, an unknown answer type, or an expected document that is not in
  the corpus.
- **Warnings:** text that looks like another language than the document's
  `language` (retrieval filters by language, so it would never be found);
  `keepWithNext` on the last unit; a `keepWithNext` group over the chunk budget;
  a synthetic document without `source.work` (citations then show the title); a
  file name that does not match the document id; a file in `documents/` that is
  not `.json` or `.md` (ignored); `expect.documents` on a case that expects
  neither `grounded` nor `reviewed_answer` (it is not checked there).

### 3.3 Markdown authoring form

For people writing content by hand. Front matter is flat `key: value` lines
between `---` fences; lists are comma-separated; dotted keys fill nested
objects (`source.work: Robert's guide`). `## Heading` starts a `section`. Each
blank-line-separated paragraph is one unit; a trailing `{ref: part 1}` sets its
reference and `{keep-with-next}` sets `keepWithNext`. Answer documents use
`kind: answer`, a `questions:` list (separated by ` | `) and the body as the answer.
`python -m companion_api.rag.pipeline import-markdown <in> <out>` writes the
canonical JSON; loading also accepts `.md` directly.

## 4. Chunking (`chunk-v1`)

- Passage documents: group consecutive units of one section until the next unit
  would exceed `maxChunkWords` (default 180). A single unit over the budget is
  its own chunk. `keepWithNext` pairs are one group.
- Answer documents: exactly one chunk; `text` is the answer, `questions` carries
  the phrasings, `searchText` covers both.
- Chunk ids: `<documentId>#<n>`, n from 1, stable for the same input.
- `sourceLabel`: `"<source.work> · <first reference>[–<last reference>]"`.
- Embedding input is `"<title>\n<text>"` (answers: questions, then answer).

## 5. Releases

Written by `release.write_release`, verified by `release.load_release` (see its
docstring for the layout). `channel` is `development` unless every document is
approved and non-synthetic and every source it cites is `cleared` in the source
registry, in which case the builder may write `published`. `write_release`
enforces this itself (`publication_problems`), so the pipeline CLI and
`scripts/build_release.py` apply the same rule: a licence still `pending_legal`
never publishes. It also refuses a chunk-v2 child whose parent is not in the
release, because the retriever serves children as their parent (§6.2).
The manifest records the embedder identity, `pipeline`
(`{"normalizer": "norm-v1", "chunker": "chunk-v1", "maxChunkWords": 180}`) and
`review` counts. Releases live outside git (`releases/` is ignored).

**Serving rule.** `Chunk.servable` — approved, or synthetic development copy.
The API retrieves only servable chunks. The operator console and the evaluator
may include drafts with `--include-drafts`; nothing child-facing can. Because
validation refuses synthetic religious content (§3.2 rule 2), the synthetic
exception admits only app help and orientation, and real content is served only
once approved.

The server does not check a release's `channel`: with grounded answers enabled
it serves a `development` release. That is what makes this development-only.
The child experience may retrieve only from published, scholar-approved
releases (`AGENTS.md`), so serving only `published` releases, with the
synthetic exception removed, is one of the gates in ADR 0003.

## 6. Answer runtime

### 6.1 Routing (before any model call)

`router.route(text) -> Route` with `category` one of `safety`, `personal_data`,
`ruling`, `injection`, `retrieve`, and a fixed `reason_code`. Development rules
(`dev-patterns-v1`) are keyword and pattern lists, clearly labelled as not an
approved safeguarding classifier; they fail towards the fixed replies. The
order is fixed: safety first, then personal data, rulings and injection. Safety
→ `safety` answer; personal data, rulings and injection attempts →
`redirected`. The fixed replies in `responses.py` are development copy awaiting
safeguarding and scholarly review; none promises secrecy, names a helpline (that
depends on the launch jurisdiction) or speaks with religious authority.

Patterns match whole words of `router.matchable(text)`: the search text with
apostrophes and transliteration marks joined rather than split, and diacritics
dropped, so "Don't", "dont" and "DON'T", or "Shafi'i" and "Shafii", read the
same. Emails, phone numbers and prompt delimiters (chat-template tokens,
`<system>`-style tags, `NOT_IN_SOURCES`) depend on punctuation that search text
removes, so those rules match the NFKC-composed raw text instead.

A `SafetyClassifier` protocol leaves room for a guard model (for example
Qwen3Guard) behind the same interface. It runs only after the rules let a
question through and can only add diversions: it cannot turn a fixed reply
back into retrieval.

**Conversation policy.** After the language check, [`conversation-policy.md`](conversation-policy.md)
decides what happens next: a faith topic is answered only from the corpus (or
abstains with `ABSTAIN_FAITH`), an exact reviewed phrasing is returned, small
talk goes to Robert's persona (`chat`), and anything else is retrieved as below,
with weak evidence and `NOT_IN_SOURCES` outside faith going to the persona
instead of abstaining at once. The fixed routes above are unchanged.

**Service language.** After routing and before retrieval, a question whose
detected language is not the service's (`en` in development) abstains with
outcome `language_mismatch`, without retrieval or a model call. The patterns
read English only, apart from two Arabic ruling patterns, so a question in
another language would pass them unread. `normalize.detect_language` tells only
Arabic from Latin script, so today this catches Arabic-script questions; a
question in another Latin-script language is routed as if it were English.

### 6.2 Retrieval

Hybrid (`hybrid-rrf-v2`): BM25 over `searchText` and cosine over vectors, each
top-20, fused with reciprocal rank fusion (k = 60); top 4 go to the prompt.
Small-to-big (new in v2): a chunk-v2 child is ranked like any chunk, but its hit
serves its parent, once, at the best rank any member reached. The prompt gets
the whole unit and the citation names the parent, and one passage cannot take
several of the four slots. Releases without children rank exactly as in v1.
Filters: servable, language (profile language, `en` in development), age band
when given (the API gives none yet: it has one synthetic profile). Weak
evidence — no BM25 hit among the eligible chunks and best cosine under the
embedder's threshold, or no eligible chunk at all — abstains without calling the
model. Thresholds are in §6.7.

The BM25 index covers each chunk's search text. For an answer chunk it also
covers a reviewed phrasing, but only when that phrasing is not already part of
the search text: the pipeline puts the questions there (§4), and counting them
twice would inflate their term frequency.

**Exact reviewed phrasings first of all.** Before any scoring, the question's
full search text (stopwords included) is looked up among the reviewed
`questions` of the eligible answer chunks; an exact match is returned verbatim
as `reviewed_answer`. This is what answers "What can you do?" and "Who are
you?": every word in them is a stopword, so BM25, the Jaccard match and the
hashing embedder all see nothing, and without the lookup they read as weak
evidence (found on the emulator, 2026-09-25).

**Reviewed answers first.** Every `answer` chunk among the top 4 is checked, in
rank order, against its reviewed `questions`: the first whose phrasing matches
the question closely (token Jaccard ≥ 0.6 over content words) is returned
verbatim as `reviewed_answer`. Only when no phrasing matches does the cosine
test apply, and only to the top candidate: an `answer` chunk ranked first with
cosine ≥ the reviewed-answer threshold is returned. In both cases the model is
not called. Checking the top candidate alone is not enough: a sibling answer
that repeats the subject ("Robert") can outrank the entry holding the child's
exact question, and even clear the cosine threshold, because one repeated word
dominates both vectors, and its text would then be returned verbatim for the
wrong question.

### 6.3 Generation

`generator.OpenAICompatibleGenerator` posts to `{base}/chat/completions` with
`model` (allowlisted: `qwen3.5:9b`, `qwen3.5:9b-*`, `Qwen/Qwen3.5-9B`),
temperature 0.3, top_p 0.8, `max_tokens` 320, no streaming, and thinking
disabled two ways: `"reasoning_effort": "none"` (Ollama) and
`"chat_template_kwargs": {"enable_thinking": false}` (llama.cpp, vLLM). Any
`<think>…</think>` block is stripped (an unclosed leading one means the output
was cut off while reasoning, so there is no answer) and
`reasoning`/`reasoning_content` fields are never read. Errors carry a status or
an exception type, never request or response content. Prompt `rag-answer-v2`
(in `prompts.py`) numbers the passages, marks them as evidence rather than
instructions, and requires every sentence to end with a citation like `[1]`, or
the exact reply `NOT_IN_SOURCES`. v2 makes Robert speak in the first person
(only words about Robert change; "you" stays "you"), gently and without jokes
on faith topics, and tells the model to reply `NOT_IN_SOURCES` rather than
explain that it cannot answer. The persona call (`chat-v2`) adds JSON mode and
temperature 0.7 per call. Passages and the question sit in delimited
blocks, and anything in them that looks like a delimiter, a chat-template
token, a citation marker or the sentinel is neutralized first.

### 6.4 Verification (before release)

Every sentence must be attributed to at least one passage that exists: by its
own `[n]` marker, or by the next marker when the model cites once at the end of
a short run (at most two uncited sentences directly before a marker, which
Qwen3.5-9B writes in about two answers out of five). At least half of each
sentence's content words must be found in the passages it is attributed to
(§6.7), carried or not; the answer
must pass output checks (length, no URLs, emails, phone numbers or markup, no
claims of religious authority, no secrecy promises). Any failure abstains. The
released text has the `[n]` markers removed; `citations` and `sources` carry
them.

The support check (`grounding-v2`) is lexical on purpose: lenient on inflection
(a shared base form or 5-character prefix counts), strict on numbers. It
cannot judge paraphrase, so it errs towards rejecting reworded answers, which
costs only an abstention. A sentence with no content words ("Yes!") counts as
unsupported, because it asserts nothing the passages can vouch for. A reply
that is only `NOT_IN_SOURCES` abstains, and so does one that mixes the sentinel
with other text. Failures are fixed codes (`missing_citation`,
`invalid_citation`, `unsupported_sentence`, `not_in_sources`, `too_long`,
`url`, `authority_claim` and so on) that reach the log as the outcome (§6.6).

### 6.5 Execution model

Routing is synchronous: a fixed reply is stored as a `completed` turn in the
request that created it, without using the queue. Everything else — the
language check, retrieval and, when needed, generation — runs on a single
background worker thread inside the API process (one GPU). At most 8 turns may
be queued or running at once: the count covers the job on the thread as well as
those waiting, so at most eight answers are ever in flight, the running one
included. A ninth returns
`503 answer_queue_full`; fixed replies are still accepted. A turn is `pending`
until its answer is stored, which includes turns that end as `reviewed_answer`
or `abstained`. Deleting the conversation while a turn is pending discards the
result. The question text lives only in that job's memory; it is never stored,
logged or embedded into the release. `AnswerService.answer` never raises: any
error becomes the abstention reply. Production moves this to the worker
process.

On shutdown, queued jobs are cancelled. A generation already running keeps its
worker thread until the model call returns or reaches
`COMPANION_LLM_TIMEOUT_SECONDS`, and its answer is discarded.

### 6.6 Provenance and logs

Each answer logs one line on `companion_api.rag`, fixed replies included:

```
INFO:     companion_api.rag rag_answer {"answer_type": "reviewed_answer", "chat_checker": "chat-check-v1", "chat_prompt_version": "chat-v2", "embedder": "hashing/hashing-v1", "latency_ms": 1, "model": "qwen3.5:9b", "outcome": "reviewed_match", "passages": 1, "policy": "conversation-policy-v1", "prompt_version": "rag-answer-v2", "release_id": "dev-app-help-hashing", "retriever": "hybrid-rrf-v2", "verifier": "grounding-v2"}
```

The fields are answer type, release id, model, prompt version, retriever,
verifier and embedder versions, number of passages and latency, plus an
`outcome` code for everything except a fixed reply (whose route the answer type
already implies): `reviewed_match`, `grounded`, `weak_evidence`,
`language_mismatch`, `grounding:<failure>` or `error:<exception type>`, and the
conversation policy's `chat`, `chat_fallback:<reason>`, `question`,
`persona_failed:<reason>` and `faith_abstain:<reason>` (conversation-policy
§10). The line also carries the policy, chat prompt and chat checker versions,
and `grounding` when the persona answered after the grounded prompt declined.
The same code is `AnswerResult.reason`, where fixed replies read
`route:<category>`.
Errors log a separate warning with the exception type only. Never the
question, the passages or the answer.

Uvicorn configures only its own loggers, so when the server builds the service
from its settings it attaches a stream handler at INFO to `companion_api.rag`
(unless that logger already has one); otherwise the line would be dropped.

### 6.7 Thresholds and calibration

| Setting | Value | Where |
|---|---|---|
| Fusion constant | RRF k = 60 | `retriever.RRF_K` |
| Candidates per branch | 20 (BM25 and cosine each) | `retriever.BRANCH_K` |
| Passages to the prompt | 4 | `retriever.FINAL_K` |
| Weak evidence, `hashing` | no BM25 hit and best cosine < 0.2 | `retriever.THRESHOLDS` |
| Reviewed answer by cosine, `hashing` | top candidate ≥ 0.75 | `retriever.THRESHOLDS` |
| Weak evidence, `openai-compatible` | no BM25 hit and best cosine < 0.55 (measured) | `retriever.THRESHOLDS` |
| Reviewed answer by cosine, `openai-compatible` | top candidate ≥ 0.85 | `retriever.THRESHOLDS` |
| Any other embedder | the strictest pair: 0.55 and 0.85 | `retriever.STRICT_THRESHOLDS` |
| Reviewed answer by phrasing | token Jaccard ≥ 0.6, any answer chunk in the top 4 | `retriever.REVIEWED_JACCARD` |
| Grounding support | ≥ 0.5 of each sentence's content words | `grounding.MIN_SUPPORT` |
| Answer length | released text ≤ 1200 characters; raw output over 4800 refused | `grounding.MAX_CHARS` |
| Generation | temperature 0.3, top_p 0.8, `max_tokens` 320 | `generator`, `service` |

Cosine scales differ between embedders, so the cosine thresholds are per
embedder (`EmbedderIdentity.name`) and can be overridden when a
`HybridRetriever` is constructed; there is no environment variable for them.

**Calibration.** The `hashing` values were measured on the development corpus:
unrelated questions score about −0.15 to 0.13 (random hash collisions) and
related ones 0.27 and up; a reviewed phrasing asked verbatim scores about 0.84
against its answer chunk, and a different question on the same subject 0.5 to
0.65. The `openai-compatible` values for `qwen3-embedding:0.6b` were measured
on 2026-09-25 against release `dev-app-help-qwen-1`: questions the corpus
answers score 0.685 to 0.856 against their best chunk, unrelated ones 0.245 to
0.462 ("What is the weather today?" is the 0.462), so weak evidence is < 0.55
with margin on both sides. The provisional 0.45 would have let that weather
question through. Questions that name Robert but that the corpus cannot answer
("Can Robert fly?") score about 0.63; declining those is the model's and the
verifier's job, not the threshold's. A near-verbatim reviewed phrasing scores
about 0.85, which stays the reviewed-answer cutoff. Recalibrate with
`python -m companion_api.rag.evaluate` (offline for retrieval, `--generate` for
grounding and abstention) after any model, prompt, embedder or material corpus
change.

## 7. API (v1 additions)

`GET /v1/bootstrap` — `features.generativeAnswers` is `true` when the server
started with grounded answers enabled, otherwise `false`.

`POST /v1/conversations/{id}/turns` → `{"turnId": "...", "status": "pending" | "completed"}`

`completed` when grounded answers are off (the answer is the fixed
`unavailable` text) and for a fixed reply (§6.1); `pending` for everything that
goes to the answer worker (§6.5). `503 answer_queue_full` when 8 turns are
already queued or running.

`GET /v1/turns/{id}` →

```json
{
  "turnId": "…",
  "status": "pending | completed",
  "answerType": null,
  "text": "",
  "citations": [],
  "sources": []
}
```

When `completed`: `answerType` is one of `unavailable` (grounded answers are
off), `grounded`, `reviewed_answer`, `abstained`, `redirected`, `safety`, `chat`
(Robert's checked casual reply, conversation-policy §9);
`text` is 1–1200 characters without citation markers; `citations` is the list
of chunk ids and `sources` the same ids with display data, in the same order,
at most 4, with `title` 1–120 characters and `reference` 1–160 (the pipeline
refuses documents that could exceed either, and the client refuses the whole
reply if one does):

```json
{"id": "app-help-stars#1", "title": "How learning stars work", "reference": "Robert's guide · part 1"}
```

`sources` is empty for every type except `grounded` and `reviewed_answer`.

A `chat` turn is `pending` then `completed` like a grounded answer, has no
citations or sources, and is one segment.

`GET /v1/turns/{id}/events` (SSE) — while pending, the body is only
`retry: 1000` so the client reconnects, and the only accepted `Last-Event-ID`
is `0` (nothing has been sent yet); once completed, one `segment` event per
verified sentence (`{"text", "citations"}`, ids 1..n) then `completed`
(`{"turnId", "answerType"}`, id n+1). A fixed reply, a reviewed answer and an
abstention are one segment. `Last-Event-ID` outside 0..n+1 is `422`.

With grounded answers off the stream is unchanged apart from one field: event 1
is the whole fixed text and event 2 is `completed`, which now also carries
`"answerType": "unavailable"`, so a client reads the answer type the same way in
both modes.

`DELETE /v1/conversations/{id}` also discards the answer of a pending turn: the
job finds no turn to write to.

## 8. Evaluation cases

`corpus/<id>/eval.json`:

```json
{"schemaVersion": 1, "cases": [
  {"id": "stars-1", "question": "How do I earn stars?",
   "expect": {"answerTypes": ["grounded", "reviewed_answer"], "documents": ["app-help-stars"]}},
  {"id": "ruling-1", "question": "Is it haram to …?", "expect": {"answerTypes": ["redirected"]}}
]}
```

`python -m companion_api.rag.evaluate --release <dir> --cases <eval.json>`
reports routing accuracy and retrieval recall@4 offline; `--generate` also
calls the model and reports answer-type match, grounding pass and abstention
rates. Religious content changes require the reviewed religious and
child-safety evaluation set (not yet written — it needs the scholarly board).

The evaluator builds its service through `service.assemble` from the §9
environment variables and calls `AnswerService.prepare()`, which is the API's
own path up to the model call (routing, language check, retrieval, weak
evidence, reviewed answers), so offline results predict what the API does. It
reads the outcome from `AnswerResult.reason`. Offline, a case expecting
`grounded` or `reviewed_answer` passes when the question reaches retrieval, the
evidence is not weak and an expected document is in the top 4; any other case
passes when the deterministic outcome is one it expects. Recall@4 is measured
for every case that lists documents, whatever the router did. Exit status is 0
when every case passes, 1 when any fails and 2 when the cases or the release
are refused. `--json` carries case ids and outcomes, never question text.

`corpus/dev-app-help/eval.json` has 47 development cases: 16 answerable app-help
questions (each with expected documents), two rulings, two safety disclosures,
two pieces of personal data, two injection attempts, three questions outside
the corpus, 11 casual chats, five faith questions and four persona boundaries.
The evaluator's handling of `chat` and of the persona's paths is in
conversation-policy §11.

## 9. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `COMPANION_RAG_ENABLED` | `false` | kill switch; `true` loads a release and enables answers |
| `COMPANION_RAG_RELEASE` | — | path to one release directory |
| `COMPANION_LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | private OpenAI-compatible endpoint |
| `COMPANION_LLM_MODEL` | `qwen3.5:9b` | must be allowlisted |
| `COMPANION_LLM_TIMEOUT_SECONDS` | `60` | per generation |
| `COMPANION_EMBEDDING_BASE_URL` | LLM base URL | private endpoint for embeddings |
| `COMPANION_EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | `hashing` selects the offline embedder |
| `COMPANION_RAG_LANGUAGE` | `en` | the service's one language, `en` or `ar` (§9.1) |
| `COMPANION_RAG_PREVIEW_DRAFTS` | `false` | corpus preview: `true` serves draft chunks (§9.1) |

The server refuses to start with grounded answers enabled when the release is
missing or fails verification, either endpoint is not private, the model is not
allowlisted, the timeout is not 1 to 600 seconds, or the configured embedder
does not match the release's. `require_rag` names every settings problem in one
message. Only the exact value `true` enables answers.

The pipeline's `build` reads `COMPANION_EMBEDDING_MODEL`,
`COMPANION_EMBEDDING_BASE_URL` and `COMPANION_LLM_BASE_URL` when its flags are
not given, and `evaluate` and `ask` read all of these variables except
`COMPANION_RAG_ENABLED` and `COMPANION_RAG_RELEASE` (they take `--release`), so
an operator run measures what the server would do.

### 9.1 Corpus preview (adult operators only)

The corpus-tasks releases (wave 1, layer 0) are Arabic and every document in
them is a draft, so the default service (English, servable chunks only) cannot
answer from them at all. To try them end to end in the app, an adult operator
may start the development server with `COMPANION_RAG_LANGUAGE=ar` and
`COMPANION_RAG_PREVIEW_DRAFTS=true`. Then:

- the retriever includes draft chunks, exactly as `evaluate --include-drafts`
  does, and the language check reads Arabic instead of English;
- `GET /v1/bootstrap` reports `contentStatus: "unreviewed_drafts"`, and an app
  built before this value existed refuses the service; the app shows every
  reply as unreviewed draft content for adult testing;
- nothing else changes: routing, the faith rule (corpus or abstain), grounding
  verification and the fixed replies are the same code.

This is a development exception to "retrieve only from published,
scholar-approved releases" (`AGENTS.md`) and is never a child-facing setting.
The first run found that the router read English only and every fixed reply was
English; since test/corpus-tasks the router reads Arabic and Arabizi and replies
come in the child's language (§15), pending native-speaker review. What remains:
Arabic answers are generated by the model from draft passages that no scholar
has reviewed, checked by the same model's judge. Both settings default to off,
and the server logs nothing more than usual.

## 10. What this does not do yet

pgvector storage, a guard model, a reranker, follow-up question rewriting
(each turn stands alone, so no transcript is kept), Arabic answer generation
review, streaming partial answers, and the reviewed evaluation set. Each is a
separate task behind the same interfaces.

Known limitations of this increment:

- **Both models together exceed this development machine's commit limit.**
  Run against the real Qwen3.5-9B on 2026-09-25 (RTX 3060 12 GB, 16 GB RAM,
  3.5 GB fixed page file): each Ollama model runs in its own process with its
  own CUDA context, the embedder's alone commits about 3.4 GB of host memory,
  and loading Qwen3.5 (with the vision projector Ollama bundles) needs about
  5 GB more. With other applications open, the two did not fit together:
  loads failed with `std::bad_alloc` and PTX JIT "Memory allocation failure".
  Both fit in VRAM; the limit is Windows' commit charge. A larger page file (or
  more RAM) lets them co-reside; until then, the `hashing` embedder with Qwen
  generating works (§11). Ollama also needed `OLLAMA_FLASH_ATTENTION=0` on this
  GPU, because its CUDA 13 build JIT-compiles the flash-attention kernel for
  sm_86 and that compile ran out of memory.
- **Embedding dimensions are assumed.** `embeddings.embedder_for` takes no
  dimensions parameter, so every non-`hashing` model is expected to return 1024
  dimensions (`qwen3-embedding:0.6b`), at build time and at query time. Another
  model fails the build with a dimensions error rather than being supported.
- **Shutdown waits for a running generation** (§6.5), up to the model timeout.
- **Development releases are served** when enabled (§5), and the router and
  fixed replies are development copy (§6.1).

## 11. Operator commands

Run from the repository root with the virtual environment's Python. None of
these downloads a model; they call the configured private endpoint, or nothing
at all with the `hashing` embedder.

| Command | What it does | Exit status |
|---|---|---|
| `python -m companion_api.rag.pipeline validate <corpus-dir> [--json]` | the §3.2 report | 1 on errors |
| `python -m companion_api.rag.pipeline build <corpus-dir> --out <root> [--release-id ID] [--embedding-model M] [--embedding-base-url URL] [--channel development\|published] [--max-chunk-words N]` | validate, chunk, embed, write a new release; `--embedding-model hashing` works offline | 1 when refused |
| `python -m companion_api.rag.pipeline verify <release-dir>` | checksums, counts and manifest summary | 1 when refused |
| `python -m companion_api.rag.pipeline stats <release-dir>` | chunk counts by content type, language, review status and kind, and words per chunk | 1 when refused |
| `python -m companion_api.rag.pipeline import-markdown <file-or-dir> <out-dir> [--overwrite]` | §3.3 Markdown to canonical JSON; writes nothing if any file has errors | 1 on errors |
| `python -m companion_api.rag.ask --release <dir> --check` | release verified, embedder matches and answers, model allowlisted, endpoint private and serving the model | 1 on any failure |
| `python -m companion_api.rag.ask --release <dir> [--include-drafts]` | one synthetic question per stdin line; prints answer type, text, sources and outcome | 0 |
| `python -m companion_api.rag.evaluate --release <dir> --cases <eval.json> [--generate] [--include-drafts] [--json]` | §8 | 0 all pass, 1 any fail, 2 refused |

`ask --check` always checks the generation endpoint, so it fails without a
model server even for a `hashing` release. Pipeline output is counts, ids and
paths, never document text. The evaluator's human-readable output prints each
case's question, which is synthetic development text; `--json` does not.

## 12. Changes from the first draft

The first draft of this contract was written before the pipeline and the
runtime. Implementing them settled or changed the following; the sections
above already describe the result.

1. **Reviewed answers (§6.2).** Phrasing (Jaccard) is checked against every
   answer chunk in the top 4, and the cosine test applies only to the top
   candidate. The draft tested the best candidate only, which could return a
   sibling answer verbatim for the wrong question.
2. **Service language (§6.1).** A question not in the service language abstains
   before retrieval, because the router's patterns are written for English; the
   draft had no language step.
3. **Router matching (§6.1).** Apostrophes, transliteration marks and
   diacritics are folded before matching, and emails, phone numbers and prompt
   delimiters are matched on the raw text, which search normalization would
   otherwise strip of the punctuation they depend on.
4. **Lexical index (§6.2).** An answer's reviewed questions are added to the
   BM25 index only when they are not already in its search text.
5. **Queue limit (§6.5).** The limit of 8 counts queued plus running turns, not
   queued turns only.
6. **Log line (§6.6).** The provenance line also carries the verifier and
   embedder versions and an `outcome` code.
7. **Evaluator path (§8).** `AnswerResult.reason` and a public
   `AnswerService.prepare()` exist so that the evaluator follows the API's path
   instead of a copy of it.
8. **Support check (§6.4).** A sentence with no content words counts as
   unsupported.
9. **Disabled-mode stream (§7).** The `completed` event includes
   `"answerType": "unavailable"`.
10. **Logging handler (§6.6).** When the server builds the service from its
    settings it attaches a stream handler to `companion_api.rag`, because
    Uvicorn does not configure that logger. The line carries versions, counts
    and timings only.
11. **Carried citations (§6.4, `grounding-v2`).** Found running the real
    Qwen3.5-9B: in two of five samples it wrote "They are Talk, Learn, Quests
    and Style. Tap one to open it.[1]", one marker after two sentences, and
    `grounding-v1` refused the whole answer. A marker now also covers up to two
    uncited sentences directly before it. Each carried sentence is held to the
    same support check against that passage, and a sentence with no marker
    after it still fails. Twelve of twelve samples verified afterwards.
12. **Exact reviewed phrasings (§6.2).** Found on the emulator: a question made
    only of stopwords ("What can you do?") abstained as weak evidence with
    either embedder, even when a reviewed answer held that exact phrasing. An
    exact search-text lookup now runs before scoring.
13. **Conversation policy (§6.1, §6.3, §6.6, §7).** Casual chat and a faith-only
    rule, specified in [`conversation-policy.md`](conversation-policy.md): the
    `chat` answer type, the `chat-v1` persona prompt and `chat-check-v1`
    checks, `rag-answer-v2` in Robert's first-person voice, and weak evidence
    or `NOT_IN_SOURCES` outside faith asking the persona instead of abstaining
    at once. `AnswerService.prepare` now returns a `Plan`. Chat replies cannot
    be grounded, so they pass their own checks instead; that scoped exception
    is recorded in [ADR 0004](adr-0004-casual-conversation.md).

## 13. Schema v2, chunk-v2 and norm-v2 (corpus tasks, 2026-09-27)

Added for the religious corpus ([`corpus-tasks.md`](corpus-tasks.md), task 9). Everything
here is optional or additive: schema v1 documents, chunk-v1 release files and the app-help
corpus behave as before.

**Document schema v2** (`schemaVersion: 2`). Extra document fields: `tier` (0 reference text,
1 scholarly explanation, 2 child content, 3 app help), `contextHeader`, `prophetId`, `topics`,
`madhhabScope` (`common` / `differs` / null), `clusterId` and `clusterRefs` (the same hadith in
other collections), `sourceIds` (registry ids), `parentChunk` (for example tafsir pointing at its
Quran segment), `children` (`units`), `generatedQuestions` (retrieval aids, at most 8, never shown).
Extra unit fields: `sourceRefs`, a list such as `["quran:12:4"]` or `["bukhari:6018"]`, next to the
old single `reference` that stays readable; and `parts`, verbatim excerpts of the unit, checked to
occur in its text in order. Tier 0/1 units that cite their own `sourceRefs` skip duplicate detection,
because reference text repeats for real (a refrain ayah, one tafsir for several ayat).

**chunk-v2.** Packing is unchanged (§4). New: each chunk carries `sourceRefs`, `parentId`,
`clusterId`, `clusterRefs`, `contextHeader`, `tier`, `prophetId`, `topics`, `madhhabScope`,
`grading`, `reviewer`, `sourceIds`, `generatedQuestions`, `checksum` (sha256 of the text) and
`releaseId`. Child chunks for small-to-big retrieval: one per verbatim `part`, and one per unit of a
multi-unit chunk when `children: units`. Children are numbered after the parent chunks, so every id
keeps the `<document>#<n>` form the API contract accepts, and they point at the parent with
`parentId`. A narration is never split: a long hadith is one parent chunk plus part children.
`embedding_text` puts `contextHeader` (else the title) first. Unknown chunk fields still fail
`load_release`.

**norm-v2.** norm-v1 plus one Arabic step: Uthmani-rasm spellings map to the simple spelling from
`src/companion_api/rag/data/rasm_map.tsv`, derived from Tanzil's own Uthmani and simple texts by
`corpusprep.rasm` (750 entries; word agreement between the two texts 90.5% → 97.5%). Latin text is
unchanged. Search text only; displayed text never changes.

**norm-v3 (test/corpus-tasks, 2026-10-01).** The rasm map applies to Quran text only
(`search_text(text, quranic=True)`, set by the chunker for `contentType: quran`), and a Quran chunk is
embedded from that simple-spelling search text. norm-v2 mapped every text, so ordinary words in questions,
hadith and app help were merged with Quranic spellings: شعير (barley) became شعاير (rituals), ثلث (a third)
became ثلاث (three), and 59 of the 750 keys occur as ordinary words in the Bukhari and Muslim texts.
Questions are never mapped: they are written in simple spelling, which is what a mapped Quran text becomes.
`normalize.arabic_forms` gives a token's light stems (each leading clitic and trailing pronoun removed) for
grounding-v3's matching; it never changes search text.

**Where the corpus comes from.** `scripts/fetch_sources.py` (registry, sha256, canonical files) and
`scripts/build_corpus.py` (checks, clusters, segments, documents) write `corpus/layer0/` and
`corpus/wave1/` as ordinary corpus folders that `python -m companion_api.rag.pipeline build`
releases. Both are regenerated and stay out of git.

## 14. No child content in the vector store (corpus tasks, 2026-09-27)

`release.write_release` is the only writer of vectors, and it admits a chunk only when
`release.admission_problems` finds nothing: an indexable content type; synthetic chunks only as
`app_help` or `orientation`; every other chunk citing at least one `sourceIds` entry that is in the
source registry and is not `candidate` or `rejected`. Both builders pass the registry
(`pipeline build --registry`, default `corpus/sources/registry.yaml`; `scripts/build_release.py`), so a
schema v1 non-synthetic document, which cannot cite a registry source, is no longer releasable. The
manifest lists every `chunkIds` entry, and `load_release` refuses a release whose chunks differ from it.
`python scripts/scan_index.py [release]` rescans a release: ids against the manifest, text against each
chunk's checksum, and every chunk against the admission rule (a source that becomes blocked later shows
up here). `tests/test_no_child_content.py` checks that conversation modules (router, chat, service,
generator, grounding, API, store) never import the pipeline, corpus preparation, governance or the chunker,
and never call `write_release` or `embed_documents`.

## 15. Arabic answers, the faith prompt and the faith judge (test/corpus-tasks, 2026-10-01)

The first end-to-end run over the Arabic corpus (2026-09-30) released 4 answers out of 83 Arabic gold
questions, and only one of them was right: the prompt's first-person rule made Robert narrate as Allah or a
prophet, the lexical check passed a quote from the wrong scene and two verses fused into a false statement,
and none of the 11 Arabic distress messages reached the safeguarding reply. This branch changes, in order:

| Piece | Version | What changed |
| --- | --- | --- |
| Router | `dev-patterns-v2` | Arabic (MSA, Levantine, Gulf, Egyptian) and Arabizi patterns for safety, personal data, rulings and injection (`rag/arabic_rules.py`); English distress and fabrication additions. Arabic faith terms and prophets' names in a religious context; Arabic courtesy formulas. |
| Small talk | `small-talk-v2` | Arabic greetings, how-are-you, thanks, goodbyes and feelings. |
| Policy | `conversation-policy-v2` | Replies in the child's language (Arabic for Arabic script and Arabizi); Arabic small talk gets reviewed Arabic copy (the persona and its checks read English only); abuse and grooming get `SAFETY_ABUSE`, which never sends the child back to a parent; persistent sadness gets `SAFETY_DISTRESS`. |
| Prompt | `rag-answer-v3` | `FAITH_SYSTEM` when the best passage is religious text: third person, never speaking as Allah or a prophet, quotations word for word in « », the question's language, NOT_IN_SOURCES when the passage tells another scene. App help keeps `SYSTEM`. |
| Verifier | `grounding-v3` | `misquoted` (a quotation of two or more words not found word for word in a cited passage), `first_person` (outside quotations, in an answer citing religious text), Arabic-aware support (`normalize.arabic_forms`), passages read in their search text. |
| Judge | `faith-judge-v1` | A JSON-mode call on every answer that cites religious text: `answers_question`, `supported`, `speaker_ok`; any false, unreadable or failed verdict gives the faith abstention (`judge.py`). |
| Retrieval | `hybrid-rrf-v2` | Optional `prophet_ids` filter. An Arabizi question is searched with Arabic terms from `rag/data/query_aliases.json` (`rag/arabizi.py`), narrowed to the prophets it names. |

**Faith by passage.** A question that names no faith term still gets faith handling when its best passage is
Quran, tafsir or hadith (`prompts.FAITH_CONTENT`): the faith prompt, the faith abstention on any failure, and
the judge whenever the answer cites religious text. The router's faith detection decides only whether casual
chat may run.

**Language.** One service still serves one corpus language. A message in another language abstains in the
child's language (`language_mismatch`). Arabizi counts as Arabic. English questions to the Arabic corpus need
reviewed English content (licensed translations), which is a corpus decision, not code.

**What these checks cannot do.** The judge is the same model that wrote the answer: a second line, not an
independent reviewer. None of this replaces the scholarly review of the corpus and of the evaluation sets.

**Arabic function words (norm-v3).** The first answers over the Arabic corpus failed the support check largely
on words that state nothing: the Arabic stopword list had 12 entries against about 50 English ones, and the
model framed facts with "كما ورد في المصدر". `normalize.ARABIC_FUNCTION_WORDS` adds common function words and
the citation-framing words; the faith prompt asks for the source's own words and no framing. "ذكر" stays a
content word, because it is also dhikr.

## 16. The verification pipeline (test/corpus-tasks-serving, 2026-10-02)

The 2026-10-01 run (Qwen3.5-9B, release `wave1-preview-3`, 145 Arabic-script gold questions) released 13
answers; 3 were wrong and every one had passed grounding-v3 and the faith judge: a quote from the wrong scene
(yusuf-04-gulf: 12:63, the return from Egypt, for the wolf story of 12:16-18), a prayer to Allah framed as words
to a father (ibrahim-04-msa: «رَبِّ…» after "قال إبراهيم لأبيه"), and an answer with no duration to
"how long did Nuh call his people" (nuh-01-arabizi). And 8 of 62 Arabizi faith questions got the puzzled chat
line. This branch adds a verification pipeline of small, named checks, mostly deterministic, around the judge.

**Shape.** After grounding passes (§6.4), a faith answer (a faith topic, or any answer citing religious text)
goes through `checks.Verifier.run`: a list of independent checks, each returning `pass`, `fail` with a fixed
reason code, or `unavailable` when the data it needs is missing (recorded, never counted as a pass, and it does
not withhold the answer). Every deterministic check runs and is recorded; the model judge runs last, and only
when all of them passed, so a failure never costs a model call. The first failure in order is the faith
abstention's reason (`faith_abstain:<reason>`). Results reach `AnswerResult.checks` and the log line
(`"checks": {"answered": "pass", "scene": "fail:scene:absent_person", …}`, `"checks_version": "checks-v1"`):
names and codes, never text. App-help answers do not go through it, as before.

| # | Check | Applies to | Fails (reason) when |
| --- | --- | --- | --- |
| 1 | `first_person` | answers citing religious text | "I" outside a quotation (`grounding:first_person`, as before) |
| 2 | `faith_terms` | faith topics | a decline (`declined`), or neither the answer nor its passages use the question's faith terms (`off_topic`); conversation-policy §3.1, unchanged except that an Arabizi question's terms are read through its Arabic search terms |
| 3 | `answered` | questions asking how many, how much, how long (كم، قديش، كام، kam, 2adeish, how many/long) or when (متى، إمتى، emta, a clause-initial "when") | the answer holds no number (digits or number words) and no duration (`answered:no_quantity`); for "when", also no time of day and no time clause (`answered:no_time`) |
| 4 | `addressee` | a quotation framed as said to someone (لأبيه، لقومه، لربه، لابنه، لإخوته، للملك، لفرعون; "said to his father") | the quotation's own vocative names someone else: «رَبِّ/ربنا/اللهم» Allah, «يا أبت/يابت/يا أبانا» a father, «يا قوم/يقوم» a people, «يا بني/يبني» a son, «يا أيها الملأ» a council, «يا موسى» Musa; "O my Lord", "O my father"… (`addressee:mismatch`). Either side unknown: pass |
| 5 | `scene` | answers citing Quran passages inside the Wave 1 episode map | another episode (`scene:other_episode`) or a scene defined by someone's absence (`scene:absent_person`), below; `unavailable` when the map is missing or the cited ayahs lie outside every mapped episode; hadith: not applicable |
| 6 | `translation` | a sentence quoting a cited translation of the meanings | it does not say it is a translation (`translation:unframed`) or does not name it (`translation:unnamed`) |
| 7 | `judge` | answers citing religious text | `faith-judge-v1`, unchanged (`judge:<field>`) |

**The scene check's decision rule** (`scene.py`). Episodes come from the Wave 1 source maps, exported with
English labels to `rag/data/episodes.json` by `scripts/export_episodes.py` (59 ranges of 5 prophets: ranges
and our own draft labels only; a test fails when it is out of date). A cited passage belongs to the episodes
whose ranges hold its ayahs.

1. *Another episode.* The question's words that name episodes of the cited prophet's story (key words of their
   labels; not a word every episode of that prophet shares, not a generic label word such as «الدعوة» or
   «النجاة», not the prophet's own name) point to those episodes. A passage in one of them passes. A passage
   outside all of them fails only when one of those words names a person of the story (a father, brother, son,
   mother or wife, the magicians, Pharaoh, the king, Iblis, another prophet; Yaqub counts as "father" in Yusuf's
   story) and that person appears neither in the cited ayahs, nor within two ayahs of them, nor in their
   episode's label. Objects and actions only point («الفلك» tells «السفينة» in another surah).
2. *The absent person.* A question that defines its scene by someone's absence («بدون يوسف», "without his
   brother", "bdoon yusuf") must be answered from ayahs that name that person: the ayahs the answer draws on (the
   ayah holding a quotation, else the ayah sharing most words with the sentence) and two on each side.

Neither rule decides which scene was asked; each refuses only on positive evidence of another scene.
Measured: on the 13 released answers both wrong-scene answers fail (ibrahim-04-msa on rule 1, yusuf-04-gulf on
rule 2) and the 10 right ones pass; on the gold set, every (question, expected passage) pair of the six Arabic
variants passes (603 pairs with this branch's new intents, 0 failures; 100 hadith pairs not applicable).
Quranpedia topics were read and are not used: they are thematic rather than narrative (12:60-61 carry none), and
topic 3719 joins 12:16 with 12:63, the very scenes rule 2 must separate. No index built from them exists in the
repository or in a release.

**Misquoted ayahs.** `ayahs.AyahIndex` splits a release's Quran chunks back into ayahs (units joined by a blank
line, one `quran:S:A` per unit). Before the faith step, `near_quote` aligns the question (or each quoted span)
word by word with the ayahs sharing its words (Smith-Waterman over search tokens; a looser spelling form drops
alef and hamza and joins a vocative "يا" to its noun, so spelling never counts as a change). A near quote needs
at least 4 agreeing words, 3 of them content words, covering 60% of the aligned span on each side, and at least
one word changed, missing or added inside it; without quotation marks or a quoting phrase ("قال تعالى", "الآية",
"the ayah"), 7 agreeing words. An exact quote, whole or partial, is never corrected. The reply quotes the exact
ayah from the release, named by surah (the release's title) and number, in the child's language
(`responses.QURAN_CORRECTION[_AR]`; an ayah too long for one reply is named, never cut): answer type `grounded`,
reason `quran_correction`, the ayah's chunk as its source, and no model reads the altered words. Measured on 130
probes built in memory from `wave1-preview-3` (never written): exact quotes corrected 0, a replaced word
corrected 119, a dropped word 119 (the misses are spans of particles); evaluation questions corrected 0 of 539.

**English answers over translations of the meanings.** `quran_translation` and `tafsir_translation` are faith
content (`prompts.FAITH_CONTENT`). An English question over them gets `FAITH_SYSTEM_EN` (rag-answer-v4): the
sources carry `translation="<name>"` from their source label, and the prompt presents a translation as a named
translation of the meanings ("In the translation of the meanings (Saheeh International): "…" [1]"), never as
the words of the Quran or of Allah, in the third person. Quotations are held word for word to the translation
passage (`misquoted`, which grounding-v4 extends to curly single quotes), and the `translation` check holds the
framing. Arabic answers keep `FAITH_SYSTEM`. `release.INDEXABLE_CONTENT_TYPES` must also admit the two types
before such a release can be written (the layer-0 translations work owns that file's change).

**Replay.** `python scripts/replay_checks.py RECORDED.jsonl [RELEASE]` runs every deterministic check over the
answers a real model released in a recorded run (a local file, never committed), reports the judge
`unavailable`, and shows where the other recorded questions are routed now. On the 2026-10-01 run:
nuh-01-arabizi fails `answered`, ibrahim-04-msa fails `addressee` and `scene`, yusuf-04-gulf fails `scene`;
the other 10 pass every check; the 8 Arabizi questions that got the chat line now take the faith route.

**Versions.**

| Piece | Version | What changed |
| --- | --- | --- |
| Prompt | `rag-answer-v4` | `FAITH_SYSTEM_EN` for English answers over translations; Arabic unchanged |
| Verifier | `grounding-v4` | quotations in curly single quotes are held word for word too |
| Checks | `checks-v1` | the pipeline above (provenance `checks`, log `checks` and `checks_version`) |
| Router | `dev-patterns-v3` | Arabizi faith terms; the AI-disclosure detector; «إنسانًا», «تنحسب», «بنو إسرائيل» |
| Policy | `conversation-policy-v3` | disclosure, misquoted-ayah correction, the checks (conversation-policy §14-16) |
| Judge | `faith-judge-v1` | unchanged, now the last check |
| Retriever, normalizer | `hybrid-rrf-v2`, `norm-v3` | unchanged |

**What this cannot do.** The checks are lexical and rule-based: the scene rules act only on episode words, people
and absence, inside the five Wave 1 stories, so a wrong scene told with the same people goes on to the judge.
"answered" accepts any number or duration, not only the right one. The near-quote detector reads Arabic ayahs
only (not a misquoted translation, not Arabizi). The episode map is model-proposed draft data, like the source
maps. None of this replaces the scholarly review of the corpus and of the evaluation sets.
