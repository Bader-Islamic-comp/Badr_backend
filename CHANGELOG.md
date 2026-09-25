# Changelog

Development increments, newest first. Nothing here is a release: this is an
adult-operated local demo on synthetic data, and the gates in
[`doc/development-boundary.md`](doc/development-boundary.md) and
[`doc/adr-0003-grounded-answers-development.md`](doc/adr-0003-grounded-answers-development.md)
are still open.

Paired client changes are in `comp-mobile/CHANGELOG.md`; the shared files under
`contracts/` must stay byte-identical between the two repositories.

## Unreleased — 2026-09-25

Grounded answers from a self-hosted Qwen3.5-9B, and the data pipeline that
feeds them, behind a kill switch that is **off by default**. With
`COMPANION_RAG_ENABLED` unset or anything but `true`, the API behaves as before
and every turn is `unavailable`. When enabled, it answers only from a synthetic
app-help corpus, and nothing in it is reviewed for children. The work is on
branch `feature/rag-system-and-data-pipeline` in three commits: `9e7482b`
(shared foundation), `cf6e727` (data pipeline) and `602479b` (answer runtime and
API). The design contract is [`doc/rag-system.md`](doc/rag-system.md), and the
boundary, including what still gates any child use, is
[ADR 0003](doc/adr-0003-grounded-answers-development.md).

### Added

**Shared foundation** (`src/companion_api/rag/`, `9e7482b`). The pipeline and the
runtime meet only here, so either half can change without the other.

- `types.py`: `Chunk`, the unit of retrieval and citation, with id
  `<documentId>#<n>` and canonical `text` kept separate from `searchText`.
  `Chunk.servable` means approved, or synthetic development copy. Also
  `ReleaseManifest`, `EmbedderIdentity`, and the `Embedder` and `Generator`
  protocols the application owns.
- `normalize.py` (`norm-v1`): canonical text is only NFC-composed and trimmed.
  Search text folds case, Arabic diacritics, tatweel and letter variants, and is
  never displayed. It also provides English and Arabic stopwords and
  Arabic-versus-Latin language detection.
- `embeddings.py`: `HashingEmbedder` (offline, deterministic, 384 dimensions,
  for tests and development releases) and `OpenAICompatibleEmbedder`
  (`/v1/embeddings` on a self-hosted server, `qwen3-embedding:0.6b` with 1024
  dimensions and instruction-prefixed queries). `embedder_for` is the one place
  a model name becomes an embedder, and the pipeline and the server both use it.
- `endpoints.py`: refuses any model endpoint that is not `localhost` or a
  private IP address, and any URL with credentials, a query or a fragment.
- `release.py`: immutable release directories (`manifest.json`,
  `chunks.jsonl`, `vectors.f32`), written through a staging directory, never
  overwritten, and verified by SHA-256 checksums and counts on every load.
- `doc/rag-system.md`: the contract between the pipeline, the runtime and the
  Flutter client. Section numbers are referenced from code comments.

**Data pipeline** (`cf6e727`)

- `corpus.py`: document schema v1, with passages made of atomic units and
  answer-bank entries holding 1–12 reviewed phrasings and one answer. The
  validation report lists every problem in one pass with file, line (for
  Markdown and JSON syntax), document and field, and never quotes document
  text. Synthetic documents may only be `app_help` or `orientation`. Real
  documents need work, edition, publisher and licence; hadith need a grading;
  every Qur'an unit needs a reference; approval needs a reviewer and an ISO
  date. Identical text is an error and near-duplicates (Jaccard ≥ 0.9) are a
  warning.
  - It also reports these errors: misspelled fields (with a suggestion); keys
    repeated in one JSON object; files that are not UTF-8 or not valid JSON;
    items listed twice; an empty `ageBands`; a non-ISO `approvedOn`;
    `keepWithNext` into a new section; reviewed answers over 1200 characters;
    one phrasing in two answers; a document id used by two files; a missing
    `corpus.json` or `documents/`; and bad `eval.json` cases (a duplicate id, an
    unknown answer type, a question over 2000 characters, an expected document
    not in the corpus).
  - It also reports these warnings: text that looks like another language than
    the document's; `keepWithNext` on the last unit or over the chunk budget; a
    synthetic document without `source.work`; a file name that differs from the
    document id; non-document files in `documents/`; and `expect.documents` on a
    case where it is not checked.
- `markdown.py`: a small, strict Markdown authoring form (flat front matter,
  `## ` sections, one paragraph per unit, `{ref: …}` and `{keep-with-next}`
  markers). Errors carry line numbers.
- `chunking.py` (`chunk-v1`): packs whole units up to 180 words by default. It
  never splits a unit, never crosses a section and never separates a
  `keepWithNext` pair. An answer document becomes exactly one chunk. Chunk ids
  are stable across rebuilds.
- `pipeline.py`: `python -m companion_api.rag.pipeline validate | build | verify
  | import-markdown | stats`. Output is counts, ids and paths, never document
  text. `build` refuses a corpus with errors, refuses an existing release id,
  and refuses `--channel published` unless every document is approved and
  non-synthetic.
- `corpus/dev-app-help/`: the synthetic development corpus. It has 18 app-help
  documents (11 passages and 7 answer-bank entries), two of them authored in
  Markdown (`app-help-looks.md`, `answer-take-break.md`), and builds into 29
  chunks. `eval.json` has 24 cases: 14 answerable questions with expected
  documents, and two each of rulings, safety disclosures, personal data,
  injection attempts and out-of-corpus questions. It is not reviewed and not for
  children.
- `corpus/README.md`: a guide for people preparing corpus data. It covers
  synthetic versus real content, both document forms, what the validator
  checks, the pipeline commands and evaluation cases.

**Answer runtime** (`602479b`)

- `router.py` (`dev-patterns-v1`): deterministic routing before any model call.
  Safety disclosures go to a fixed safeguarding reply; personal data, religious
  rulings and prompt injection go to fixed redirects. Matching folds
  apostrophes and diacritics; emails, phone numbers and prompt delimiters are
  matched on the raw text. It is labelled as **not** an approved safeguarding
  classifier. A `SafetyClassifier` protocol leaves room for a guard model that
  can only add diversions.
- `responses.py`: the fixed replies (safety, personal data, ruling, injection,
  abstain). All are development copy awaiting safeguarding and scholarly
  review.
- `lexical.py` and `retriever.py` (`hybrid-rrf-v1`): BM25 and cosine, each
  top-20, fused with reciprocal rank fusion (k = 60), with the top 4 kept.
  Results are filtered to servable chunks in the service language. Weak
  evidence abstains without a model call. A reviewed answer is returned
  verbatim when any answer chunk in the top 4 has a phrasing with token
  Jaccard ≥ 0.6, or when the top candidate is an answer above the per-embedder
  cosine threshold. The retriever refuses a release built with a different
  embedder.
- `prompts.py` (`rag-answer-v1`): numbered passages marked as evidence, not
  instructions. Delimiters, chat-template tokens and citation markers in
  passages and the question are neutralized. Every sentence must cite a
  passage, or the reply is exactly `NOT_IN_SOURCES`.
- `generator.py`: an OpenAI-compatible chat adapter for Qwen3.5-9B. It accepts
  only the allowlisted models `qwen3.5:9b`, `qwen3.5:9b-<tag>` and
  `Qwen/Qwen3.5-9B`, and only private endpoints. Thinking is disabled with
  `reasoning_effort: "none"` (Ollama) and `chat_template_kwargs.enable_thinking:
  false` (llama.cpp, vLLM). `<think>` blocks are stripped and reasoning fields
  are never read. Errors carry a status or an exception type only.
- `grounding.py` (`grounding-v1`): every sentence must cite a passage from the
  prompt, and at least half of its content words must be found in the cited
  passages; a sentence with no content words is unsupported. Output checks
  cover length, URLs, emails, phone numbers, markup, claims of religious
  authority and secrecy promises. Any failure abstains.
- `service.py`: `AnswerService` runs route → language check → retrieve →
  generate → verify, and never raises; any error becomes the abstention reply.
  `prepare()` is public and `AnswerResult.reason` records the outcome, so the
  evaluator follows the API's own path. `assemble` is the one place a service is
  built from settings.
- `evaluate.py`: `python -m companion_api.rag.evaluate`. Offline, it reports
  routing accuracy and recall@4; with `--generate` it also calls the model and
  reports answer-type match, grounding pass and abstention rates. `--json`
  output has no question text. It exits 0, 1 or 2.
- `ask.py`: `python -m companion_api.rag.ask`, an operator console for synthetic
  questions. `--check` verifies the release, the embedder and the model
  endpoint.
- Tests: `test_rag_foundation.py`, `test_rag_corpus.py`, `test_rag_markdown.py`,
  `test_rag_chunking.py`, `test_rag_pipeline.py`, `test_rag_runtime.py` and
  `test_rag_api.py`.

### Changed

- **Source display limits match the client.** `Source.title` is 1–120
  characters and `Source.reference` 1–160, which is what the Flutter client
  shows; it refuses the whole reply otherwise. Validation now errors on a
  document title over 120 characters or a work name and unit references that
  could make a citation label longer than 160.
- **Turns are `pending` or `completed`.** With answers enabled, fixed replies
  complete in the request. Everything else is `pending` while a single
  background thread answers it (one GPU). At most 8 turns can be queued or
  running; beyond that, `503 answer_queue_full` is returned, and fixed replies
  are still accepted. Deleting a conversation discards a pending answer.
- **`GET /v1/turns/{id}`** adds `answerType` (null while pending; otherwise
  `unavailable`, `grounded`, `reviewed_answer`, `abstained`, `redirected` or
  `safety`) and `sources` (`id`, `title`, `reference`; at most 4). `text` is
  capped at 1200 characters.
- **`GET /v1/turns/{id}/events`** sends only `retry: 1000` while pending, then
  one `segment` per verified sentence and a `completed` event carrying
  `answerType`. With answers off, this is still one segment then `completed`,
  and `completed` now carries `"answerType": "unavailable"`. Cursors are
  accepted from `0` to `n+1`.
- **`features.generativeAnswers`** in bootstrap is a boolean, `true` only when
  the process started with grounded answers enabled.
- `config.py`: new settings `COMPANION_RAG_ENABLED`, `COMPANION_RAG_RELEASE`,
  `COMPANION_LLM_BASE_URL`, `COMPANION_LLM_MODEL`,
  `COMPANION_LLM_TIMEOUT_SECONDS`, `COMPANION_EMBEDDING_BASE_URL` and
  `COMPANION_EMBEDDING_MODEL`. `require_rag` names every problem at once.
- `main.py`: `create_app(settings, answer_service=None)` builds the answer
  service at startup when enabled and fails closed. A lifespan hook stops the
  answer worker on shutdown. When built from settings, the service attaches a
  stream handler to the `companion_api.rag` logger, because Uvicorn does not
  configure it.
- `store.py`: `DemoStore` takes an optional answer service and a queue bound,
  and stores only the released answer, its segments and its sources.
- `pyproject.toml`: `httpx` moved from the test extra to the runtime
  dependencies, because the server now calls the model server.
  `constraints-dev.txt` already pinned it (0.28.1).
- `.env.example`: the grounded-answer variables, off by default.
- `.gitignore`: `releases/`, because releases are build output.

### Security and privacy

- The question is passed only to the answer job. It is never stored, logged or
  embedded, and the store keeps only the released answer and keyed
  fingerprints. A test asserts that question text appears in neither the logs
  nor the retained state.
- One provenance line per answer on `companion_api.rag` records the answer
  type, release, model, prompt, retriever, verifier and embedder versions,
  passage count, latency and an outcome code. It never records the question,
  the passages or the answer.
- Model and embedding endpoints must be private, and only allowlisted models
  are accepted, so a child's question cannot reach a third-party provider
  through configuration.
- Retrieved passages and the question are evidence, never instructions, and
  are neutralized before prompting. Reasoning output is never read or shown.
- Real drafts are never served by the API. Synthetic content cannot be
  religious.
- CLI output never contains document text. Evaluator `--json` output never
  contains question text.

### Contracts and docs

- `contracts/openapi-v1.json` regenerated: `TurnCreated.status` and
  `Turn.status` are `pending | completed`; `Turn` adds `answerType` and
  `sources` (a new `Source` schema), and caps `text`, `citations` and `sources`;
  `Features.generativeAnswers` is a boolean.
- `doc/rag-system.md` updated to match the implementation. It records the
  changes from its first draft (§12), adds the thresholds table and calibration
  note (§6.7) and an operator command reference (§11).
- `doc/adr-0003-grounded-answers-development.md` (new): the decision, the
  serving and private-endpoint rules, and what still gates child use.
  `doc/development-boundary.md` (ADR 0002) is marked as superseded in part.
- `README.md`: the development RAG setup, the new turn and event shapes, and
  corrected statements about what is enabled.
- `doc/product-architecture-roadmap.md`: brief implementation-status notes.
- `AGENTS.md`: a pointer to the contract and ADR 0003. `corpus/dev-app-help`
  must stay synthetic app help.

### Verification

28 → **334 tests** (18 foundation, 142 pipeline, 146 runtime and API). None needs
a model server: they use the hashing embedder, mocked HTTP transports and
scripted generators. The paired Flutter suite passes 81 tests.

- Offline `evaluate` of a hashing build of `dev-app-help`: routing 24/24,
  recall@4 14/14.
- A live end-to-end run used the real API with grounded answers on, a hashing
  release, and a stand-in OpenAI-compatible server on localhost in place of
  Qwen. No model was downloaded.
  - Every path behaved correctly: `reviewed_answer`, `grounded` (with a
    `<think>` block stripped), `redirected`, `safety` and `abstained`.
  - Only one question reached the model, and its request disabled thinking
    both ways.
  - The real Flutter client parsed all five reply types from that live server.
  - No question text appeared in the server logs.

**Run against the real Qwen3.5-9B** (Ollama 0.34.4, RTX 3060 12 GB, 16 GB RAM):

- Built `dev-app-help-qwen-1` with `qwen3-embedding:0.6b` (29 chunks, 1024
  dimensions); `ask --check` passed every check. Offline `evaluate`: 24/24
  routing, 14/14 recall@4.
- Measured the real embedder's scores and set its weak-evidence threshold from
  the provisional 0.45 to **0.55** (answerable questions 0.685–0.856, unrelated
  0.245–0.462). Details in `doc/rag-system.md` §6.7.
- Raised the embedding client's timeout from 30 s to 120 s: the first request
  after a start loads the model onto the GPU, and that took over 30 s here.
- Ollama needed `OLLAMA_FLASH_ATTENTION=0` (its flash-attention kernel is JIT
  compiled for this GPU and the compile ran out of memory), and the embedder
  and Qwen could not both be loaded under the machine's commit limit.
- With the `hashing` embedder and Qwen3.5-9B generating
  (`dev-app-help-hashing-1`), `evaluate --generate` matched **23 of 24** answer
  types; **5 of 6** generated answers passed grounding. The sixth ("What is the
  parent area for?") added a sentence the source does not support, and the
  verifier refused it. For "Can Robert fly?" Qwen wrote "The sources do not
  say…" instead of `NOT_IN_SOURCES`; the verifier refused that too, so the
  child gets the abstention.
- The Flutter client, against the live API on real Qwen: grounded answers in
  about 2 s (including the 1 s poll), reviewed answers in 1 s, rulings in 4 ms.
- **Verifier `grounding-v2`.** In the app, "What do the tabs at the bottom do?"
  first came back as "Robert isn't sure": Qwen had written two sentences and
  one `[1]` after both, and `grounding-v1` required a marker per sentence.
  Sampling showed that shape in two answers of five. A marker now also covers
  up to two uncited sentences directly before it, each still held to the
  support check against that passage; 12 of 12 samples then verified. Tests:
  333.
- **Exact reviewed phrasings.** Asked on the emulator, "What can you do?"
  came back "Robert isn't sure": all its words are stopwords, so nothing
  reached the retriever's scoring and it read as weak evidence with either
  embedder. The retriever now looks a question's full search text up among the
  reviewed phrasings before scoring. The development corpus gains two reviewed
  answers for questions addressed to Robert (`answer-who-are-you`,
  `answer-what-can-you-do`): 20 documents, 31 chunks, 26 evaluation cases, all
  passing offline. Tests: 334.
- **On the Android emulator** (after closing Steam and Chrome to free memory),
  with the API on real Qwen: the thinking bubble, a grounded answer with its
  sources, and a ruling redirect all rendered as designed
  (`comp-mobile/design/grounded-answer.png`, `thinking-bubble.png`,
  `redirect-reply.png`).
- Every model failure along the way (CUDA errors, empty replies) ended as an
  abstention, never as an unverified answer.

### Known gaps

- **The two models do not fit this machine's memory commit limit together.**
  See "Run against the real Qwen3.5-9B" below. With the real embedder and Qwen
  both loaded, loads fail with `std::bad_alloc`; a larger page file or more RAM
  is needed to use `qwen3-embedding:0.6b` at query time.
- `embedder_for` has no dimensions parameter, so the build, the server and the
  operator tools assume 1024 dimensions for every non-hashing model.
- On shutdown, a generation already running keeps its worker thread until the
  model call returns or times out (`COMPANION_LLM_TIMEOUT_SECONDS`). Its answer
  is discarded.
- The language check tells only Arabic from Latin script. A question in
  another Latin-script language is routed by the English patterns.
- The router is not an approved safeguarding classifier, the fixed replies are
  unreviewed development copy, and there is no guard model.
- The server serves `development` releases and synthetic chunks when enabled.
  Child use needs published, approved releases only (ADR 0003).
- The model is called directly over HTTP behind the `Generator` interface, not
  through LiteLLM.
- There is no reranker, no follow-up question rewriting, no Arabic generation
  review and no streaming of partial answers. The reviewed religious and
  child-safety evaluation set does not exist yet. Answers run in the API
  process, not the worker. Releases are files searched in memory, not
  PostgreSQL with `pgvector`.

## Unreleased — 2026-09-22

A cosmetic catalogue that is actually earned, so the client's new customization
tab has something server-authoritative behind it.

### Added

- **A four-look catalogue** in `content.py` (`COSMETICS`, `CATALOGUE`), priced
  in the same learning stars the lesson ledger grants: Robert Original (0),
  Sunset Copper (5), Dune Walker (15), Midnight Teal (30). Ids match the room's
  own fixed allowlist; the service never invents one.
- **`POST /v1/cosmetics/claim`** — spends the catalogue price against the
  ledger. The price and the balance are read here, never sent by the client, so
  a look cannot be unlocked by a tampered app.
  - `403 insufficient_stars` when it costs more than the balance.
  - `404 not_found` for an unknown id.
  - An already-owned look is a no-op reporting `"spent": 0`, so a lost response
    or a second key cannot charge twice.
  - The balance can never go negative.
- **`tools/export_contracts.py`** — writes `contracts/openapi-v1.json` from the
  app itself, and optionally a consumer's copy. The app serves no
  `/openapi.json`, so that file is the published contract; hand-editing is how
  it drifts from the routes it describes.
- **Ownership and equipment state** in `DemoStore`: `_owned`, `_equipped`,
  `_completed_lessons`, plus `inventory()`, `claim()` and `completed_any_lesson`.

### Changed

- **`GET /v1/inventory`** now returns the whole catalogue from the store, with
  `description` and `cost` on each entry, instead of one hard-coded item.
- **`PUT /v1/equipped-cosmetics`** accepts any look this process records as
  owned, instead of only `default`. Anything else is `403 cosmetic_not_owned`.
- **Lesson completion is tracked explicitly** rather than inferred from the
  ledger being empty. Spending stars writes to the same ledger, so the old
  `if not self._ledger` guard would have silently stopped granting the lesson's
  five stars after the first purchase. `GET /v1/challenges/today` reads
  `store.completed_any_lesson` for the same reason.
- Spending appends a **negative** entry to the append-only ledger, so the
  balance stays a sum over that ledger and is never stored as a mutable number.
  Earn-only still holds in the sense the roadmap means it: stars come from
  learning, never from money, trade or chance.

### Contracts and docs

- `contracts/openapi-v1.json` regenerated: the claim route, the `Claimed`
  schema, and `description`/`cost` on `Cosmetic`.
- `contracts/avatar-bridge-v1.schema.json`: `cosmeticId` widened from
  `const: "default"` to the four-id enum.
- `doc/product-architecture-roadmap.md`: the claim route added to the API list.
- `README.md`: the new endpoint's rules, the ledger note and how to regenerate
  the contract.

### Verification

25 → **28 tests**. The new ones cover looks being earned from the ledger and
never going negative, equipment following ownership, and the published contract
matching the routes the app actually serves.

`DemoStore` remains a bounded, process-local adapter for synthetic tests. All of
this ownership state disappears on restart and is not a PostgreSQL replacement.
