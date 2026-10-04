# Source selection and provenance policy (draft)

Status: **draft; owner Mousa al-Rashdan; not approved.** Task:
[Source selection and provenance policy](https://app.clickup.com/t/z8q7hbct4a).

## Acceptance criteria for a source

1. Identified edition: title, edition or commit, publisher, numbering system.
2. Terms found and recorded (`license`, `license_url`, `terms_summary`); if not, the source stays
   `candidate` and never enters a release.
3. Machine-readable download that is reproducible byte for byte (a pinned commit where possible).
4. For hadith: a grading and the grader's name from the source, or a collection rule the board has
   accepted (Bukhari and Muslim: sahih). No grading means ineligible.
5. Two independent datasets where one exists, cross-checked; disagreement is recorded, never
   resolved automatically.

## Chain of evidence (implemented)

| Link | Where |
| --- | --- |
| URL, edition, publisher, licence, terms | `corpus/sources/registry.yaml` |
| sha256 and retrieval date of each file | same entry; written once with `--record`, verified on every run |
| Raw file as downloaded | `corpus/raw/<source_id>/` (outside git; rebuilt by `scripts/fetch_sources.py`) |
| Canonical text, verbatim | `corpus/canonical/`, sha256 of each file in `corpus/canonical/manifest.json` |
| Structural checks | Quran counts against two references; hadith cross-check `corpus/reports/hadith_crosscheck.md` |
| Release provenance | release manifest `pipeline`: registry sha256, per-source sha256, git commit, policy version |

A changed upstream file fails `scripts/fetch_sources.py` (exit 2) and overwrites nothing: a new
edition is a governance decision, recorded by updating the registry deliberately.

## Registry statuses

`candidate` (terms not found; blocked from releases), `pending_legal` (terms recorded; awaiting the
rights owner), `rejected` (must not be used). No source is marked cleared by tooling.

## Decisions needed

- Acceptance of each registered source (see `doc/governance/rights-clearance.md`).
- Whether a single-source collection may ever enter a release, and under what extra review.
