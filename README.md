# Companion server development foundation

## Android client and backend inference

The primary client is the separate Android-first Flutter phone app. User chat travels from Flutter to this backend; the backend owns all AI inference, agent orchestration, reviewed-content retrieval, input safety, grounding and output validation. Flutter receives validated replies and maps allowlisted presentation cues to Unity. Unity never calls this API or model providers directly.

No model inference or provider credentials belong on the phone. This deployment split does not remove the backend's authority over consent, progress, rewards or inventory. These are target responsibilities. Grounded answers are off by default, and the synthetic demo then returns fixed unavailable responses. Development-only grounded answers from a self-hosted model over a synthetic app-help corpus can be enabled by an operator (see [Grounded answers (RAG) — development](#grounded-answers-rag--development)). No speech provider exists. Provider and safeguarding reviews remain prerequisites.

This is an **adult-operated local development demo using synthetic data only**.
It is not ready for children, a pilot, or deployment. No guardian authentication,
consent service, approved religious corpus, reviewed safeguarding playbook,
voice provider, or analytics exist. The generative model and retrieval are off
by default; development-only grounded answers can be enabled within the
boundary of [ADR 0003](doc/adr-0003-grounded-answers-development.md).

[`CHANGELOG.md`](CHANGELOG.md) records what each development increment changed
and what it verified.

Run commands from this server repository's root (`comp-server`). Python 3.10+
is required. The current source implements the versioned API in the development
plan; Flutter is a separate repository and is its only intended client.

## Setup and run (PowerShell)

```powershell
py -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[test]' -c constraints-dev.txt
$env:COMPANION_DEMO_MODE = 'true'
$env:COMPANION_DEMO_TOKEN = (.venv/Scripts/python.exe -c 'import secrets; print(secrets.token_urlsafe(32))')
.venv/Scripts/python.exe -m uvicorn companion_api.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Provide the same operator-generated secret to the local Flutter demo through its
documented configuration. Every `/v1` route requires `X-Demo-Token`. The API
refuses initialization unless demo mode is explicitly `true` and the token is at
least 24 ASCII characters. This is a local operator boundary, not child identity
or a parental gate. Do not expose the port publicly. CORS is disabled. Android
emulator clients use `http://10.0.2.2:8000`; desktop clients use loopback.

`.env.example` lists configuration but is not loaded automatically. Never commit
the real token. The safe startup command disables access logs because arbitrary
URLs/query strings can contain sensitive data. Application code logs no request
payloads, tokens, transcripts, or retrieved passages. With grounded answers on,
each answer logs one provenance line on `companion_api.rag`: versions, counts,
latency and an outcome code, never the question, the passages or the answer.
Responses include a fresh correlation UUID and `Cache-Control: no-store`. Do not
enable debug request dumps or production telemetry on this scaffold.

`constraints-dev.txt` records the versions verified on Windows with Python 3.10.
Review dependency updates and rerun the suite before changing those pins; this
development constraint set is not a production supply-chain approval.

In a second terminal with the same environment settings, the independent worker
entrypoint can be run as follows. It deliberately has no jobs or outbound calls;
grounded-answer jobs currently run on a thread inside the API process:

```powershell
.venv/Scripts/python.exe -m companion_api.worker --check
.venv/Scripts/python.exe -m companion_api.worker
```

`--check` validates configuration and exits; normal operation waits until stopped.

## Grounded answers (RAG) — development

Off by default. With `COMPANION_RAG_ENABLED=true` the API answers from one
immutable corpus release. A development router sends safety, personal-data,
ruling and prompt-injection messages to fixed replies. Hybrid retrieval then
returns a reviewed answer verbatim, or abstains when the evidence is weak.
Otherwise a self-hosted Qwen3.5-9B writes an answer from the top four passages,
and it is released only if every sentence is attributed to a passage that supports it.
The only corpus is the synthetic `corpus/dev-app-help` (help text about the
app, no religious content), and none of this is reviewed for children. The
router is not an approved safeguarding classifier, and the fixed replies are
development copy awaiting review.

A conversation policy sits in front of retrieval. A faith question is answered
only from the corpus (a reviewed answer, or a grounded answer that verifies and
really answers) and otherwise gets a gentle faith abstention; it never reaches
casual chat or model memory. Small talk such as "Hi, how are you?", and
non-faith messages the corpus cannot answer, go to Robert's persona prompt. Its
reply is released as answer type `chat`, with no sources, only after its own
checks, or is replaced by reviewed copy; a factual question it recognises still
abstains.

- [`doc/rag-system.md`](doc/rag-system.md) is the design contract: corpus
  format, chunking, releases, routing, retrieval, thresholds, the API shapes and
  the operator commands.
- [`doc/conversation-policy.md`](doc/conversation-policy.md) is the
  conversation policy: the decision order, the faith and small-talk detectors,
  the persona call and its checks, and the reviewed fallbacks and invitations.
- [`doc/robert-persona.md`](doc/robert-persona.md) is Robert's character sheet,
  the only source of facts about him.
- [`corpus/README.md`](corpus/README.md) is the guide for people preparing
  corpus data.
- [ADR 0003](doc/adr-0003-grounded-answers-development.md) records the boundary
  and what still gates any child use.
- [ADR 0004](doc/adr-0004-casual-conversation.md) records the boundary for
  casual chat, its scoped exception to grounding verification, and what else
  gates child use.

The model and embedding endpoints must be on this machine or a private network
(`localhost` or a private IP address), and the model must be allowlisted
(`qwen3.5:9b`, `qwen3.5:9b-<tag>`, `Qwen/Qwen3.5-9B`). The server refuses to
start with answers enabled otherwise, or when the release fails verification or
was built with a different embedder.

**1. Model server (the operator's own step).** Nothing in this repository
downloads a model. Install Ollama for Windows from
<https://ollama.com/download>; it serves an OpenAI-compatible API on
`http://127.0.0.1:11434/v1`. Then pull the two models yourself:

```powershell
ollama pull qwen3.5:9b            # generation, about 6.6 GB
ollama pull qwen3-embedding:0.6b  # embeddings, about 0.6 GB
```

llama.cpp or vLLM serving the same models through an OpenAI-compatible API also
work; point `COMPANION_LLM_BASE_URL` (and, if different,
`COMPANION_EMBEDDING_BASE_URL`) at them. Thinking is disabled on every request.

On the RTX 3060 / 16 GB development machine (Ollama 0.34.4), start the server
with flash attention off and a longer keep-alive. Ollama's CUDA 13 build
compiles the flash-attention kernel for this GPU on first use, and that compile
ran out of memory; the keep-alive stops the model reloading between questions:

```powershell
$env:OLLAMA_FLASH_ATTENTION = '0'; $env:OLLAMA_KEEP_ALIVE = '30m'; ollama serve
```

The first request after a start loads the model onto the GPU (over 30 s the
first time). Qwen3.5-9B and the embedder each commit several GB of host memory
in their own process; with a 3.5 GB page file they did not fit together, and
loads failed with `std::bad_alloc`. Either enlarge the page file, or run with
`COMPANION_EMBEDDING_MODEL=hashing` and a `hashing` release so only Qwen loads
(see `doc/rag-system.md` §10).

**2. Build a release.** Choose the release id, so the later commands can name
it. Releases are immutable: rebuilding needs a new `--release-id`. `releases/`
is ignored by git.

```powershell
.venv/Scripts/python.exe -m companion_api.rag.pipeline validate corpus/dev-app-help

# With the real embedder: the model server running with qwen3-embedding:0.6b.
.venv/Scripts/python.exe -m companion_api.rag.pipeline build corpus/dev-app-help --out releases --release-id dev-app-help-qwen

# Offline, without a model server (development only; everything that uses this
# release must then set COMPANION_EMBEDDING_MODEL=hashing too).
.venv/Scripts/python.exe -m companion_api.rag.pipeline build corpus/dev-app-help --out releases --release-id dev-app-help-hashing --embedding-model hashing

.venv/Scripts/python.exe -m companion_api.rag.pipeline verify releases/dev-app-help-qwen
```

**3. Check and evaluate.** `ask` and `evaluate` read the same environment
variables as the server, so set the embedder that built the release first.

```powershell
$env:COMPANION_EMBEDDING_MODEL = 'qwen3-embedding:0.6b'
.venv/Scripts/python.exe -m companion_api.rag.ask --release releases/dev-app-help-qwen --check
.venv/Scripts/python.exe -m companion_api.rag.evaluate --release releases/dev-app-help-qwen --cases corpus/dev-app-help/eval.json
.venv/Scripts/python.exe -m companion_api.rag.evaluate --release releases/dev-app-help-qwen --cases corpus/dev-app-help/eval.json --generate

# Offline evaluation of the hashing release needs no model server.
$env:COMPANION_EMBEDDING_MODEL = 'hashing'
.venv/Scripts/python.exe -m companion_api.rag.evaluate --release releases/dev-app-help-hashing --cases corpus/dev-app-help/eval.json
```

- `ask --check` verifies the release checksums, that the embedder matches the
  release and answers, that the model is allowlisted and the endpoint private,
  and that the endpoint serves the model. It always checks the generation
  endpoint, so it fails without a model server even for the hashing release.
- Offline `evaluate` (the default) calls no model and reports routing accuracy
  and retrieval recall@4. On the hashing release of `dev-app-help` it passes all
  47 cases, with recall@4 of 16/16. `--generate` also calls the model and reports
  answer-type match, grounding pass and abstention rates, and how many chat
  replies passed the checks or fell back (`doc/conversation-policy.md` §11).
  Exit status is 0 when every case passes, 1 when any fails, 2 when refused.
- Without `--check`, `ask` reads one question per line from standard input and
  prints the answer type, text, sources and outcome code. Type synthetic text
  only.
- `--include-drafts` (both tools) also retrieves draft content, which the API
  never serves. It is for adult operators evaluating content.
- The retrieval thresholds for the real embedder were measured this way on
  2026-09-25 (`doc/rag-system.md` §6.7); rerun `evaluate` after material corpus
  changes.

**4. Run the API with grounded answers.** In the terminal that has the demo
settings from [Setup and run](#setup-and-run-powershell), add the variables from
`.env.example` and start the server as before:

```powershell
$env:COMPANION_RAG_ENABLED = 'true'
$env:COMPANION_RAG_RELEASE = 'releases/dev-app-help-qwen'
$env:COMPANION_LLM_BASE_URL = 'http://127.0.0.1:11434/v1'
$env:COMPANION_LLM_MODEL = 'qwen3.5:9b'
$env:COMPANION_LLM_TIMEOUT_SECONDS = '60'
$env:COMPANION_EMBEDDING_MODEL = 'qwen3-embedding:0.6b'
.venv/Scripts/python.exe -m uvicorn companion_api.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

`COMPANION_EMBEDDING_BASE_URL` left unset uses `COMPANION_LLM_BASE_URL`. With the
hashing release (`COMPANION_RAG_RELEASE = 'releases/dev-app-help-hashing'`,
`COMPANION_EMBEDDING_MODEL = 'hashing'`) the server starts without a model
server. Fixed replies, reviewed answers and weak-evidence abstentions then work,
and questions that need the model abstain until one is running.
`GET /v1/bootstrap` reports `features.generativeAnswers: true` while answers are
on. To turn them off, set `$env:COMPANION_RAG_ENABLED = 'false'` (or remove it)
and restart.

## API behavior

- `GET /health/live` is the only unauthenticated endpoint.
- `GET /v1/bootstrap`, `/v1/lessons`, `/v1/challenges/today`, `/v1/rewards`, and
  `/v1/inventory` expose one synthetic profile, one orientation activity, an
  earn-only learning reward, and the ten-look cosmetic catalogue (the original,
  three colourways and six modelled outfits). Bootstrap's
  `features.generativeAnswers` is `true` only when this process started with
  grounded answers enabled.
- `POST /v1/lessons/demo-learning/complete` with `{}` grants five learning stars
  once per process/profile, even across concurrent calls or different retry keys.
- `POST /v1/cosmetics/claim` with `{"cosmeticId":"sunset"}` spends the catalogue
  price against the ledger. The price and the balance are read here, never sent
  by the client, so a look cannot be unlocked by a tampered app. A look that
  costs more than the balance returns 403 `insufficient_stars` and an unknown id
  returns 404; the balance can never go negative. Claiming an already-owned look
  is a no-op that reports `"spent": 0`, so a lost response or a second key
  cannot charge twice.
- `PUT /v1/equipped-cosmetics` with `{"cosmeticId":"sunset"}` accepts only a
  look this process records as owned; anything else is 403 `cosmetic_not_owned`.
- `POST /v1/conversations` with `{}` creates a synthetic conversation.
- `POST /v1/conversations/{id}/turns` accepts `{"text":"synthetic test input"}`
  and returns `{"turnId": "...", "status": "pending" | "completed"}`.
  - With grounded answers off (the default), all input takes a fixed unavailable
    response route and the turn is `completed` at once with `answerType`
    `unavailable`. This is not a high-risk classifier or an approved safeguarding
    response. No religious claims are made.
  - With grounded answers on, the development router answers safety,
    personal-data, ruling and prompt-injection messages at once with fixed
    replies (`completed`, `answerType` `safety` or `redirected`). Everything
    else is `pending` while one background thread retrieves and, when needed,
    calls the model. At most 8 turns can be queued or running; beyond that the
    route returns 503 `answer_queue_full`, and fixed replies are still accepted.
- `GET /v1/turns/{id}` returns `status`, `answerType`, `text`, `citations` and
  `sources`. While pending, `answerType` is null, `text` is empty and both lists
  are empty. When completed, `answerType` is one of `unavailable`, `grounded`,
  `reviewed_answer`, `abstained`, `redirected`, `safety` or `chat`, and `text` is 1–1200
  characters without citation markers. `citations` holds at most four chunk ids,
  and `sources` holds the same ids in the same order with a `title` and a
  `reference`. Both are empty except for `grounded` and `reviewed_answer`.
- `GET /v1/turns/{id}/events` returns finite SSE. While the turn is pending, the
  body is only `retry: 1000`, so the client reconnects after a second; the only
  accepted cursor is `0`. Once completed, event `1..n` is one `segment` per
  verified sentence (`{"text","citations"}`), and event `n+1` is `completed`
  (`{"turnId","answerType"}`). A fixed reply, a reviewed answer, an abstention
  and the unavailable answer are one segment, so event `1` is the whole text and
  event `2` is `completed`. `Last-Event-ID` resumes after that event; a cursor
  outside `0..n+1` returns a redacted 422. Reconnect with the same turn ID.
- `DELETE /v1/conversations/{id}` removes conversation, turns, creation replay,
  and turn replay records, and discards the answer of a turn still pending.
  Reusing a removed creation key creates a new ID; replaying a removed turn key
  against the old conversation returns 404.

Spending appends a negative entry to the same append-only ledger that grants
write to, so the balance stays a sum over that ledger and is never stored as a
mutable number. Lesson completion is tracked separately from ledger emptiness,
because after a purchase the ledger is no longer empty.

The question text is passed only to the answer job; it is never stored,
logged or embedded. Turns keep only the released answer and its sources. The
full contract, including the answer types, is in
[`doc/rag-system.md`](doc/rag-system.md) §7.

All writes require `Idempotency-Key` (8–128 printable ASCII characters without
spaces). Keys are scoped to this one synthetic operator/profile across routes;
use random UUIDs. Matching retries return the original result. Reusing a key for
a different operation or payload returns 409. Failed validation/domain requests
are not cached. Deletion retains only a keyed fingerprint and empty result for
its own retry; no deleted conversation ID or text is retained in that record.

Bodies are bounded to 8 KiB before JSON parsing; text is 1–2000 characters and
must not be blank. Unknown body fields are rejected. Errors use
`{"error":{"code":"..."}}` without echoing input. The original text exists only
transiently while the request is processed. The store retains keyed HMAC
fingerprints of write payloads for conflict detection, never raw user input.
The HMAC secret is process-local and is discarded at restart.

## Storage and architecture limitations

`DemoStore` is a bounded, locked, process-local adapter for synthetic tests. It
is **not a PostgreSQL replacement**. Run exactly one API worker. All progress,
rewards, conversations, and retry state disappear on process restart. Do not
interpret restart behavior as durable idempotency or financial correctness.

Capacity is 128 conversations, 512 turns, and 1024 successful write replays.
Requests exceeding capacity receive 503; existing retries remain available.
Deleting an existing conversation remains possible at capacity and frees its
associated entries. Replays are not silently evicted to allow duplicate grants.
Turns retain only the released answer text (fixed text, a reviewed answer, or
verified generated sentences) and its sources, never the question, and no raw
transcript history is implemented. Restart the local synthetic demo when
necessary; no data migration or retention guarantees are claimed. Corpus
releases are separate, immutable directories on disk, loaded and verified at
startup; they are not stored in `DemoStore`.

Modules separate configuration, API schemas/boundaries, synthetic content,
deterministic routing, state/ledger operations, the worker lifecycle, and the
`rag` package (data pipeline and answer runtime, `doc/rag-system.md` §2). Future
gated work must add real account/household/consent and parent-policy modules,
PostgreSQL transactions and unique constraints, Redis coordination/replay,
approved source governance, privacy-reviewed storage/deletion, and domain-owned
provider interfaces before enabling real users. No empty fake production
integrations are supplied here. Human review and the reviewed religious/child
safety evaluation suite remain prerequisites, not completed checks.

## Verify

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m compileall -q src
```

The suite has 537 tests and needs no model server: the RAG tests use the
offline hashing embedder and stand-in model responses. Tests exercise startup
restrictions, token checks, atomic reward grants, idempotency conflicts,
inventory ownership, earning and wearing a look against the ledger, input
bounds/redacted errors, non-retention, SSE resume, deletion/stale replay
cleanup, bounded capacity, and isolated restarts. For grounded answers they also
cover corpus validation and Markdown import, unit-preserving chunking, release
immutability and tamper detection, private-endpoint and model-allowlist
refusals, routing, hybrid retrieval and reviewed-answer matching, thinking
disabled and reasoning stripped, grounding verification, pending and completed
turns, the event stream, the answer queue, and that question text is never
logged or retained. For the conversation policy they cover the faith and
small-talk detectors, faith never reaching the persona, every chat check and
fallback, the invitations and the salam return. They do not establish child safety or content review
approval.

`contracts/openapi-v1.json` is the published contract, because the app serves no
`/openapi.json`. It is generated, not hand-edited, and a test fails when the
checked-in copy no longer matches the routes the app serves:

```powershell
.venv/Scripts/python.exe tools/export_contracts.py ../comp-mobile/contracts/openapi-v1.json
```

The Flutter repository keeps a byte-identical copy, so pass its path whenever the
API changes.

The suite runs from a fresh checkout without an editable install: the worker
check passes `src/` to its subprocess explicitly rather than relying on one. If
this repository is moved, an existing `.venv` still holds the old path in its
editable `.pth` file; reinstall with the command above rather than editing it.
