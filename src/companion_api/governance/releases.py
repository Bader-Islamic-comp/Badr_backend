"""Immutable corpus releases with a current pointer, rollback and quarantine (governance task 5).

Builds on `rag.release` (the same manifest.json + chunks.jsonl + vectors.f32
with sha256 checksums) and adds, in the manifest's free-form `pipeline` block,
the provenance a reviewer needs: registry sha256, the sha256 of every source
the release draws on, the canonical manifest, the git commit and the policy
version. Documents whose sources are `candidate` or `rejected` in the registry
never enter a release. Written files are made read-only.

    <releases-root>/current_release         the id the server serves
    <releases-root>/release_history.json    promoted ids, oldest first (rollback pops the top)
    <releases-root>/quarantined.json        ids that must never be served again
    <releases-root>/audit.jsonl             hash-chained events for every pointer change
"""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess

from ..corpusprep import registry as registry_module
from ..rag import embeddings, normalize
from ..rag.chunking import VERSION as CHUNKER, chunk_documents, embedding_text
from ..rag.corpus import load_corpus
from ..rag.release import ReleaseError, load_release, write_release
from ..rag.types import RELEASE_ID, ReleaseManifest
from . import audit

POINTER, HISTORY, QUARANTINE, AUDIT = "current_release", "release_history.json", "quarantined.json", "audit.jsonl"
BLOCKED_STATUSES = ("candidate", "rejected")


def git_commit(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return out.stdout.strip() + ("+dirty" if dirty else "") if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _read_only(path: Path) -> None:
    for item in path.iterdir():
        item.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    path.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)


def build(corpus_dir: Path, releases_root: Path, release_id: str, *, registry_path: Path, actor: str,
          embedding_model: str = "hashing", embedding_base_url: str = embeddings.DEFAULT_BASE_URL,
          channel: str = "development", canonical_manifest: Path | None = None, policy_version: str = "unversioned",
          repo_root: Path | None = None) -> tuple[Path, dict]:
    """Builds one release; returns (path, summary). Raises ReleaseError on any refusal."""
    if not RELEASE_ID.match(release_id):
        raise ReleaseError("release ids are 3-64 characters of a-z, 0-9, '.', '_' or '-'")
    corpus, report = load_corpus(corpus_dir)
    if corpus is None or not report.ok:
        raise ReleaseError(f"corpus {corpus_dir} has {len(report.errors)} validation errors")
    registry = registry_module.load(registry_path)
    status = {source["source_id"]: source["status"] for source in registry.sources}
    kept, excluded = [], {}
    for document in corpus.documents:
        unknown = [sid for sid in document.source_ids if sid not in status]
        if unknown:
            raise ReleaseError(f"{document.id} cites sources missing from the registry: {', '.join(unknown)}")
        blocked = [sid for sid in document.source_ids if status[sid] in BLOCKED_STATUSES]
        if blocked or (not document.source_ids and not document.synthetic):
            reason = f"source {blocked[0]} is {status[blocked[0]]}" if blocked else "no registered source"
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        kept.append(document)
    if not kept:
        raise ReleaseError("no document is eligible for a release")
    if channel == "published" and any(d.synthetic or d.review.status != "approved" for d in kept):
        raise ReleaseError("the published channel needs every document approved and non-synthetic")
    if channel == "published":
        uncleared = sorted({sid for d in kept for sid in d.source_ids if status[sid] != "cleared"})
        if uncleared:
            raise ReleaseError("the published channel needs every source cleared by the rights owner "
                               f"(doc/decisions/decisions.yaml); not cleared: {', '.join(uncleared)}")
    chunks = [replace(chunk, release_id=release_id) for chunk in chunk_documents(kept)]
    embedder = embeddings.embedder_for(embedding_model, embedding_base_url)
    try:
        vectors = embedder.embed_documents([embedding_text(chunk) for chunk in chunks])
    finally:
        close = getattr(embedder, "close", None)
        if close:
            close()
    sources = sorted({sid for document in kept for sid in document.source_ids})
    pipeline = {
        "normalizer": normalize.VERSION, "chunker": CHUNKER, "maxChunkWords": 180,
        "registrySha256": registry.digest, "sourceSha256": {sid: registry.get(sid)["sha256"] for sid in sources},
        "canonicalManifestSha256": (sha256(Path(canonical_manifest).read_bytes()).hexdigest()
                                    if canonical_manifest and Path(canonical_manifest).is_file() else None),
        "gitCommit": git_commit(repo_root or Path(corpus_dir)), "policyVersion": policy_version,
        # The release audit trail's head before this build: an anchor no later rewrite of audit.jsonl can move,
        # because a release directory is read-only (scripts/verify_audit.py checks it).
        "auditHead": audit.head(Path(releases_root) / AUDIT),
        "excludedDocuments": excluded, "corpusDir": Path(corpus_dir).name,
    }
    review = {"approved": sum(d.review.status == "approved" for d in kept),
              "draft": sum(d.review.status != "approved" for d in kept), "synthetic": sum(d.synthetic for d in kept)}
    manifest = ReleaseManifest(release_id=release_id, created_at="", channel=channel, corpus_ids=(corpus.id,),
                               document_count=len(kept), chunk_count=len(chunks), embedder=embedder.identity,
                               pipeline=pipeline, review=review)
    path = write_release(Path(releases_root), manifest, chunks, vectors, sources=status)
    _read_only(path)
    audit.append(Path(releases_root) / AUDIT, actor=actor, action="release.build", item=release_id, from_state=None,
                 to_state="built", reason=f"{len(kept)} documents, {len(chunks)} chunks, excluded {excluded}")
    return path, {"release_id": release_id, "documents": len(kept), "chunks": len(chunks), "excluded": excluded}


def _json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _write(path: Path, value) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def current(releases_root: Path) -> str | None:
    pointer = Path(releases_root) / POINTER
    return pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else None


def promote(releases_root: Path, release_id: str, *, actor: str, reason: str = "") -> None:
    root = Path(releases_root)
    if release_id in _json(root / QUARANTINE, []):
        raise ReleaseError(f"release {release_id} is quarantined and cannot be served")
    load_release(root / release_id)  # verify every checksum before pointing at it
    previous = current(root)
    audit.append(root / AUDIT, actor=actor, action="release.promote", item=release_id, from_state=previous,
                 to_state=release_id, reason=reason)
    history = _json(root / HISTORY, [])
    history.append(release_id)
    _write(root / HISTORY, history)
    _write(root / POINTER, release_id + "\n")


def rollback(releases_root: Path, *, actor: str, reason: str, quarantine: bool = False) -> str:
    """Points back at the previous verified, non-quarantined release; returns its id."""
    root = Path(releases_root)
    if not reason.strip():
        raise ReleaseError("a rollback needs a reason")
    history = _json(root / HISTORY, [])
    active = current(root)
    if not history or history[-1] != active:
        raise ReleaseError("release history does not end with the current release; refusing to guess")
    quarantined = _json(root / QUARANTINE, [])
    if quarantine:
        audit.append(root / AUDIT, actor=actor, action="release.quarantine", item=active, from_state="served",
                     to_state="quarantined", reason=reason)
        quarantined.append(active)
        _write(root / QUARANTINE, quarantined)
    remaining = history[:-1]
    while remaining and remaining[-1] in quarantined:
        remaining.pop()
    if not remaining:
        raise ReleaseError("there is no earlier release to roll back to")
    target = remaining[-1]
    load_release(root / target)
    audit.append(root / AUDIT, actor=actor, action="release.rollback", item=target, from_state=active,
                 to_state=target, reason=reason)
    _write(root / HISTORY, remaining)
    _write(root / POINTER, target + "\n")
    return target
