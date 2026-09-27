# Re-review cadence and change triggers (draft proposal)

Status: **proposal; owner Mousa al-Rashdan; not approved.** Task:
[Re-review cadence and change triggers](https://app.clickup.com/t/z8q7hbct4h).

## Triggers (checked by `python scripts/due_for_review.py [release]`)

| Trigger | Detected when | Scope |
| --- | --- | --- |
| `source_changed` | a source's registry sha256 differs from the one in the release manifest | chunks citing it |
| `source_status_changed` | a cited source is now `candidate` or `rejected` | chunks citing it |
| `embedding_changed` | the configured embedding model differs from the release's | every chunk (new release + retrieval regression run) |
| `policy_changed` | `corpus/governance/policy_version.txt` differs from the release's `policyVersion` | every chunk |
| `cadence_elapsed` | the release is older than the cadence | approved chunks |

Drafts are reported as `never_approved`; they need a first review, not a re-review.

## Proposed cadence

- Approved layer 2 content: every **12 months** (default `--cadence-days 365`).
- After any trigger above: before the next release.
- Emergency: a credible report of an error quarantines the item or the release at once
  (`scripts/review.py quarantine`, `scripts/rollback.py --quarantine`), then review.
- A 5% weekly sample of answers goes to a scholarly reviewer (plan.md component 9).

## Decisions needed

The cadence, who may raise an emergency quarantine, and when a policy change counts as material.
