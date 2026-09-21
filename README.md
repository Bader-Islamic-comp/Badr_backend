# Companion server development foundation

## Android client and backend inference

The primary client is the separate Android-first Flutter phone app. User chat travels from Flutter to this backend; the backend owns all AI inference, agent orchestration, reviewed-content retrieval, input safety, grounding and output validation. Flutter receives validated replies and maps allowlisted presentation cues to Unity. Unity never calls this API or model providers directly.

No model inference or provider credentials belong on the phone. This deployment split does not remove the backend's authority over consent, progress, rewards or inventory. These are target responsibilities: the current synthetic demo still returns fixed unavailable responses, with no enabled model, retrieval or speech provider. Provider and safeguarding reviews remain prerequisites.

This is an **adult-operated local development demo using synthetic data only**.
It is not ready for children, a pilot, or deployment. No guardian authentication,
consent service, approved religious corpus, reviewed safeguarding playbook,
generative model, retrieval, voice provider, or analytics are enabled.

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
payloads, tokens, transcripts, or retrieved passages. Responses include a fresh
correlation UUID and `Cache-Control: no-store`. Do not enable debug request dumps
or production telemetry on this scaffold.

`constraints-dev.txt` records the versions verified on Windows with Python 3.10.
Review dependency updates and rerun the suite before changing those pins; this
development constraint set is not a production supply-chain approval.

In a second terminal with the same environment settings, the independent worker
entrypoint can be run as follows. It deliberately has no jobs or outbound calls:

```powershell
.venv/Scripts/python.exe -m companion_api.worker --check
.venv/Scripts/python.exe -m companion_api.worker
```

`--check` validates configuration and exits; normal operation waits until stopped.

## API behavior

- `GET /health/live` is the only unauthenticated endpoint.
- `GET /v1/bootstrap`, `/v1/lessons`, `/v1/challenges/today`, `/v1/rewards`, and
  `/v1/inventory` expose one synthetic profile, one orientation activity, an
  earn-only learning reward, and Robert's original cosmetic.
- `POST /v1/lessons/demo-learning/complete` with `{}` grants five learning stars
  once per process/profile, even across concurrent calls or different retry keys.
- `PUT /v1/equipped-cosmetics` with `{"cosmeticId":"default"}` accepts only the
  owned, allowlisted original skin.
- `POST /v1/conversations` with `{}` creates a synthetic conversation.
- `POST /v1/conversations/{id}/turns` accepts `{"text":"synthetic test input"}`.
  All input takes a fixed unavailable response route; this is not a high-risk
  classifier or an approved safeguarding response. No religious claims are made.
- `GET /v1/turns/{id}` returns the completed fixed answer and empty citations.
- `GET /v1/turns/{id}/events` returns finite SSE: event `1` is the full `segment`,
  event `2` is `completed`. `Last-Event-ID: 0`, `1`, or `2` resumes after that event;
  other cursors return a redacted 422. Reconnect with the same turn ID.
- `DELETE /v1/conversations/{id}` removes conversation, turns, creation replay,
  and turn replay records. Reusing a removed creation key creates a new ID;
  replaying a removed turn key against the old conversation returns 404.

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
Only fixed service text is retained for turns, and no raw transcript history is
implemented. Restart the local synthetic demo when necessary; no data migration
or retention guarantees are claimed.

Modules separate configuration, API schemas/boundaries, synthetic content,
deterministic routing, state/ledger operations, and the worker lifecycle. Future
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

Tests exercise startup restrictions, token checks, atomic reward grants,
idempotency conflicts, inventory ownership, input bounds/redacted errors,
non-retention, SSE resume, deletion/stale replay cleanup, bounded capacity, and
isolated restarts. They do not establish child safety or content review approval.

The suite runs from a fresh checkout without an editable install: the worker
check passes `src/` to its subprocess explicitly rather than relying on one. If
this repository is moved, an existing `.venv` still holds the old path in its
editable `.pth` file; reinstall with the command above rather than editing it.
