# ADR 0003: Grounded answers on a self-hosted model, development only

Status: accepted engineering boundary, development only. Date: 2026-09-25.
Supersedes in part [ADR 0002](development-boundary.md), for grounded answers only.

## Context

ADR 0002 made Q&A return a fixed unavailable message, so the request, replay,
streaming and deletion transport could be built without a model, retrieval or
invented religious citations. The gates that would allow real answers are
still open: there is no named scholarly board, no licensed and reviewed
corpus, no jurisdiction-specific safeguarding playbook, no provider review and
no privacy review.

Those gates need something concrete to review: a pipeline that keeps canonical
text and provenance, a retriever that abstains, a verifier that refuses
unsupported sentences, and logs that carry versions but no child content.
Building that machinery against synthetic app-help text lets it be tested
without inventing religious content and without a child ever using it.

## Decision

1. **Build retrieval-augmented answers in the backend on a self-hosted
   Qwen3.5-9B.** As the confirmed delivery direction requires, all inference
   runs on the backend, not on the phone. The model is served through an
   OpenAI-compatible server on this machine or a private network: Ollama
   (`qwen3.5:9b`) by default, or llama.cpp or vLLM. Embeddings use
   `qwen3-embedding:0.6b`. Only `qwen3.5:9b`, `qwen3.5:9b-<tag>` and
   `Qwen/Qwen3.5-9B` are accepted: switching models is a review decision, not a
   configuration change. Thinking is disabled on every request and any
   reasoning that comes back is discarded, so only the final answer is verified
   and nothing else reaches a child. The design contract is
   [`rag-system.md`](rag-system.md).
2. **Off by default.** `COMPANION_RAG_ENABLED` must be exactly `true`. Otherwise
   the API behaves as under ADR 0002: every turn completes with the fixed
   unavailable text and `answerType: "unavailable"`, and bootstrap reports
   `features.generativeAnswers: false`. When enabled, the server fails closed at
   startup on a missing or altered release, a public endpoint, a model off the
   allowlist or a mismatched embedder, instead of degrading at request time.
   This is the kill switch the repository guidance requires for model and
   corpus selection.
3. **Synthetic corpus only.** The only corpus is `corpus/dev-app-help`: invented
   help text about using the app, not reviewed and not for children. The
   validator refuses synthetic content of any religious type, so invented
   religious text cannot be made to look like a source. Real content must carry
   its work, edition, publisher and licence, hadith a grading, and every Qur'an
   unit a reference.
4. **Serving rule.** The API serves a chunk only when it is approved, or when it
   is synthetic development copy (which rule 3 limits to app help and
   orientation). Real drafts can be built and evaluated by an adult operator
   with `--include-drafts`, but are never served by the API.
5. **Private endpoints only.** Model and embedding endpoints must be `localhost`
   or a private IP address, with no credentials, query or fragment. Sending a
   child's question to a third-party provider is exactly what the provider
   review decides, so the code refuses it rather than relying on configuration.
6. **Deterministic replies before any model call.** Development router rules
   send safety disclosures to a fixed safeguarding reply, and personal data,
   religious rulings and prompt injection to fixed redirects. They are labelled
   as **not** an approved safeguarding classifier, and every fixed reply is
   development copy awaiting review. Weak evidence abstains, a reviewed answer
   is returned verbatim, and a generated answer is released only when every
   sentence cites a supporting passage.
7. **No child content kept.** The question lives only in the answer job's
   memory; it is never stored, logged or embedded. Each answer logs one
   provenance line with versions, counts and timings only.

## What still gates any child use

Nothing in this ADR approves grounded answers for children. Before any child
use, including a pilot:

- A named scholarly board, and a licensed corpus it has reviewed and approved,
  published as releases on the `published` channel. The server must then serve
  only published releases; it serves a `development` release today, and the
  synthetic exception in the serving rule must go.
- Reviewed safeguarding replies, and a reviewed safeguarding classifier (for
  example a guard model behind the existing `SafetyClassifier` interface) in
  place of the development patterns, with language coverage for every
  supported language.
- A provider and model review of Qwen3.5-9B and `qwen3-embedding:0.6b`, and of
  how and where they are hosted, covering the points the repository guidance
  lists: privacy, retention, training use, residency, safety and evaluation.
- A privacy review of the whole answer path.
- The reviewed religious and child-safety evaluation set, passing, with the
  retrieval and grounding thresholds recalibrated against it on the real model
  and embedder.
- PostgreSQL as the system of record with `pgvector` for the reviewed corpus,
  replacing the process-local store and file-based in-memory retrieval.

## Consequences

- The API contract changed for both modes: turns are `pending` or `completed`;
  `GET /v1/turns/{id}` carries `answerType` and `sources`; the event stream
  sends `retry: 1000` while pending, then one event per verified sentence;
  `503 answer_queue_full` limits queued and running answers to 8; and
  `features.generativeAnswers` is a boolean. The Flutter client must handle
  every answer type even though the default stays `unavailable`.
- `httpx` is now a runtime dependency, because the server calls the model
  server.
- Operators who enable answers must run a model server themselves and download
  the models themselves; this repository never downloads one. A `hashing`
  embedder lets the pipeline, the tests and the evaluator run offline.
- Answers run on one thread inside the API process, one GPU's worth of work at a
  time. Production moves this to the worker process.
- The retrieval thresholds for the real embedder were measured on the
  development corpus (2026-09-25) and must be re-measured on any real corpus.
  On a 16 GB development machine the embedder and Qwen3.5-9B could not both be
  loaded (Windows commit limit), so the evaluated configuration used the
  offline `hashing` embedder with Qwen3.5-9B generating.
- The model is called through a direct OpenAI-compatible HTTP client behind the
  application-owned `Generator` and `Embedder` interfaces, not through LiteLLM,
  which the roadmap names as the provider adapter. With one self-hosted
  endpoint there is nothing to switch between; adopting LiteLLM later is a
  change behind those interfaces.
- The boundary of ADR 0002 otherwise stands: synthetic data, an adult operator,
  a local operator token that is not authentication or consent, and no voice,
  generative stories or live Unity embedding.
