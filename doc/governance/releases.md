# Immutable corpus releases with rollback (draft)

Status: **draft; tooling implemented; owner Mousa al-Rashdan.** Task:
[Immutable corpus releases with rollback](https://app.clickup.com/t/z8q7hbct4d).

Builds on the existing release format (`doc/rag-system.md` §5): `manifest.json`, `chunks.jsonl`,
`vectors.f32`, sha256 checksums verified on every load.

```bash
python scripts/build_release.py corpus/wave1 --release-id wave1-dev-1 --actor "NAME" --promote
python scripts/rollback.py --status
python scripts/rollback.py --actor "NAME" --reason "why"              # previous verified release
python scripts/rollback.py --actor "NAME" --reason "why" --quarantine # and never serve this one again
```

- **Gate:** documents whose `sourceIds` include a `candidate` or `rejected` registry source are left
  out (counted in `pipeline.excludedDocuments`); `published` needs every document approved and every
  source `cleared`. `rag.release.write_release` enforces the published rule itself, so
  `python -m companion_api.rag.pipeline build --channel published` cannot skip it.
- **Provenance** in the manifest `pipeline` block: `registrySha256`, `sourceSha256` per source,
  `canonicalManifestSha256`, `gitCommit`, `policyVersion`, chunker and normalizer versions; the
  embedding model is the manifest `embedder`. Every chunk carries its `releaseId`.
- **Read-only:** files are chmod 444 and the directory 555 after writing; any edit fails the checksum.
- **Pointer:** `releases/current_release` names the served release; `COMPANION_RAG_RELEASE` may point at
  this file. `releases/release_history.json` is the promotion stack; rollback pops it and verifies the
  target before switching. `releases/quarantined.json` lists releases that are refused even by pointer.
- Every build, promotion, rollback and quarantine is an audit event in `releases/audit.jsonl`.

**Audit anchors (test/corpus-tasks).** Each release manifest records `pipeline.auditHead`, the head
(`seq`, `hash`) of `releases/audit.jsonl` when it was built. A release directory is read-only, so
`scripts/verify_audit.py` checks the trail against every manifest's anchor and reports events removed after an
anchor or a trail rewritten before it, which the hash chain alone cannot see.
