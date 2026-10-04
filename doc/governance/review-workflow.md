# Review workflow, audit trail and admin interface (draft)

Status: **draft; owner Mousa al-Rashdan; tooling implemented, nothing approved.** Tasks:
[Review workflow tooling and admin UI](https://app.clickup.com/t/z8q7hbct4e),
[Audit trail for every approval](https://app.clickup.com/t/z8q7hbct4f).

## States

```text
empty (template) -> draft -> in_review -> approved
                                       -> rejected -> draft (revise)
draft | in_review | approved | rejected -> quarantined
```

A review item is one version of one age-band draft: `<draft id>@<band>` (e.g. `story-yusuf-s01@7-9`).

## CLI (`scripts/review.py`)

| Command | Who | Refused when |
| --- | --- | --- |
| `list [--status S]` | anyone | — |
| `submit ITEM --actor A` | the author | not draft, or actor is not the author |
| `approve ITEM --actor R` | a reviewer | not in_review; R is the author; R not qualified; R declared a conflict; checks do not pass |
| `reject ITEM --actor R --reason T` | a reviewer | same as approve, except checks; a reason is required |
| `revise ITEM --actor A` | the author | not rejected |
| `quarantine ITEM --actor N --reason T` | governance | no reason |

## Audit trail

`corpus/governance/audit.jsonl` (content) and `releases/audit.jsonl` (release pointer changes):
one JSON event per line with `seq`, `at`, `actor`, `action`, `item`, `from_state`, `to_state`,
`reason`, `prev_hash` and `hash` (sha256 of the event). Every transition is appended **before** the
file changes, and appending refuses a broken trail. `python scripts/verify_audit.py` names the first
edited, removed, inserted or reordered line and exits 1. Events carry ids and names, never content
text or child data.

## Admin interface (not built)

The backend has no admin router today, so no UI was built. The interface the portal needs, behind
guardian-free staff authentication and role checks (architecture §5.2 lists `/v1/admin/...`):

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/admin/review-items?status=` | list items with checks and author |
| `POST /v1/admin/review-items/{id}/submit` | author submits |
| `POST /v1/admin/review-items/{id}/approve` / `reject` | reviewer decision (reason for reject) |
| `POST /v1/admin/review-items/{id}/quarantine` | emergency pull (reason) |
| `GET /v1/admin/audit?item=` | read the trail for one item |
| `POST /v1/admin/corpus-releases`, `POST /v1/admin/corpus-releases/{id}/promote`, `POST .../rollback` | release management |

Each endpoint calls the same functions as the CLI (`companion_api.governance.review`,
`governance.releases`), so the rules cannot differ between the two.
