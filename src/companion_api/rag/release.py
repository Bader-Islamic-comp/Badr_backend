"""Immutable corpus releases on disk.

A release is one directory, written once and never modified:

    <releases-root>/<release-id>/
        manifest.json   ReleaseManifest, including SHA-256 checksums of the others
        chunks.jsonl    one Chunk per line, in vector order
        vectors.f32     little-endian float32, chunk_count x dimensions, row-major

Rolling back is pointing the server at the previous directory. Loading verifies
every checksum and count before anything is served, so a truncated copy or a
hand-edited chunk fails loudly instead of answering from altered text.
"""
from array import array
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Sequence

from .types import RELEASE_ID, SCHEMA_VERSION, Chunk, ReleaseManifest

MANIFEST, CHUNKS, VECTORS = "manifest.json", "chunks.jsonl", "vectors.f32"
# The only content a release may index (doc/corpus-tasks.md task 15): registered reference and reviewed
# content, or synthetic app help. Never conversation text, child utterances or anything about a child.
INDEXABLE_CONTENT_TYPES = ("app_help", "orientation", "lesson", "story", "quran", "tafsir", "hadith", "dua", "fiqh")
SYNTHETIC_CONTENT_TYPES = ("app_help", "orientation")
BLOCKED_SOURCE_STATUSES = ("candidate", "rejected")


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedRelease:
    manifest: ReleaseManifest
    chunks: tuple[Chunk, ...]
    vectors: tuple[array, ...]


def _digest(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _float32_bytes(vectors: Sequence[Sequence[float]], dimensions: int) -> bytes:
    flat = array("f")
    for vector in vectors:
        if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
            raise ReleaseError(f"every vector must have {dimensions} finite values")
        flat.extend(vector)
    if sys.byteorder != "little":
        flat.byteswap()
    return flat.tobytes()


def admission_problems(chunks: Sequence[Chunk], sources: dict[str, str] | None) -> list[str]:
    """Why chunks may not be indexed. `sources` maps registry source_id -> status.

    Synthetic chunks are app help or orientation only. Every other chunk must cite at least one
    registry source, all registered and none candidate or rejected. A chunk that does not satisfy
    this (a chat turn, a child's words, text from nowhere) never reaches the vector store.
    """
    problems = []
    for chunk in chunks:
        if chunk.content_type not in INDEXABLE_CONTENT_TYPES:
            problems.append(f"{chunk.id}: content type {chunk.content_type!r} is not indexable")
        elif chunk.synthetic:
            if chunk.content_type not in SYNTHETIC_CONTENT_TYPES:
                problems.append(f"{chunk.id}: synthetic chunks may only be app help or orientation")
        elif not chunk.source_ids:
            problems.append(f"{chunk.id}: cites no registered source")
        elif sources is None:
            problems.append(f"{chunk.id}: no source registry was given to check it against")
        else:
            for source_id in chunk.source_ids:
                status = sources.get(source_id)
                if status is None:
                    problems.append(f"{chunk.id}: source {source_id} is not in the registry")
                elif status in BLOCKED_SOURCE_STATUSES:
                    problems.append(f"{chunk.id}: source {source_id} is {status}")
    return problems


def write_release(root: Path, manifest: ReleaseManifest, chunks: Sequence[Chunk],
                  vectors: Sequence[Sequence[float]], *, sources: dict[str, str] | None = None) -> Path:
    """Writes a new release directory and returns its path. The only writer of vectors.

    Chunks are admitted only as `admission_problems` allows, checked against `sources`
    (registry source_id -> status); any refusal writes nothing.

    `manifest` supplies identity and metadata; counts, checksums and (when
    empty) `created_at` are filled in here. An existing release id is refused:
    releases are immutable, so a rebuild needs a new id.
    """
    if not RELEASE_ID.match(manifest.release_id):
        raise ReleaseError("release ids are 3-64 characters of a-z, 0-9, '.', '_' or '-'")
    if not chunks or len(chunks) != len(vectors):
        raise ReleaseError("a release needs at least one chunk and exactly one vector per chunk")
    if len({chunk.id for chunk in chunks}) != len(chunks):
        raise ReleaseError("chunk ids must be unique within a release")
    problems = admission_problems(chunks, sources)
    if problems:
        raise ReleaseError(f"{len(problems)} chunks may not be indexed: " + "; ".join(problems[:5]))
    root = Path(root)
    target = root / manifest.release_id
    if target.exists():
        raise ReleaseError(f"release {manifest.release_id!r} already exists; releases are immutable")
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{manifest.release_id}.", dir=root))
    try:
        lines = "".join(json.dumps(chunk.to_json(), ensure_ascii=False, sort_keys=True) + "\n" for chunk in chunks)
        (staging / CHUNKS).write_text(lines, encoding="utf-8", newline="\n")
        (staging / VECTORS).write_bytes(_float32_bytes(vectors, manifest.embedder.dimensions))
        final = replace(
            manifest,
            schema_version=SCHEMA_VERSION,
            created_at=manifest.created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            document_count=len({chunk.document_id for chunk in chunks}),
            chunk_count=len(chunks),
            chunk_ids=tuple(chunk.id for chunk in chunks),
            checksums={CHUNKS: _digest(staging / CHUNKS), VECTORS: _digest(staging / VECTORS)},
        )
        (staging / MANIFEST).write_text(json.dumps(final.to_json(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


POINTER = "current_release"
QUARANTINED = "quarantined.json"


def resolve(path: Path) -> Path:
    """A release directory, or a `current_release` pointer file naming one beside it.

    A quarantined release is refused even when a pointer still names it.
    """
    path = Path(path)
    if path.is_file() and path.name == POINTER:
        release_id = path.read_text(encoding="utf-8").strip()
        if not RELEASE_ID.match(release_id):
            raise ReleaseError(f"{path} does not name a release id")
        path = path.parent / release_id
    quarantine = path.parent / QUARANTINED
    if quarantine.is_file() and path.name in json.loads(quarantine.read_text(encoding="utf-8")):
        raise ReleaseError(f"release {path.name} is quarantined")
    return path


def load_release(path: Path) -> LoadedRelease:
    """Reads and verifies a release. Raises `ReleaseError` on any inconsistency."""
    path = resolve(path)
    try:
        manifest = ReleaseManifest.from_json(json.loads((path / MANIFEST).read_text(encoding="utf-8")))
    except FileNotFoundError:
        raise ReleaseError(f"no {MANIFEST} in {path}") from None
    except (KeyError, TypeError, ValueError) as exception:
        raise ReleaseError(f"unreadable {MANIFEST}: {exception}") from None
    if manifest.schema_version != SCHEMA_VERSION:
        raise ReleaseError(f"release schema {manifest.schema_version} is not supported (expected {SCHEMA_VERSION})")
    for name in (CHUNKS, VECTORS):
        if not (path / name).is_file() or _digest(path / name) != manifest.checksums.get(name):
            raise ReleaseError(f"{name} is missing or does not match the manifest checksum")
    try:
        chunks = tuple(Chunk.from_json(json.loads(line))
                       for line in (path / CHUNKS).read_text(encoding="utf-8").splitlines() if line.strip())
    except (TypeError, ValueError) as exception:
        raise ReleaseError(f"unreadable {CHUNKS}: {exception}") from None
    flat = array("f")
    flat.frombytes((path / VECTORS).read_bytes())
    if sys.byteorder != "little":
        flat.byteswap()
    dimensions = manifest.embedder.dimensions
    if len(chunks) != manifest.chunk_count or len(flat) != manifest.chunk_count * dimensions:
        raise ReleaseError("chunk or vector counts do not match the manifest")
    if manifest.chunk_ids and tuple(chunk.id for chunk in chunks) != manifest.chunk_ids:
        raise ReleaseError("chunk ids do not match the manifest")
    vectors = tuple(flat[row * dimensions:(row + 1) * dimensions] for row in range(len(chunks)))
    return LoadedRelease(manifest, chunks, vectors)


def scan(path: Path, sources: dict[str, str] | None) -> list[str]:
    """Scans a release (the index) and returns every problem: ids not in the manifest, altered text,
    or chunks that `admission_problems` would refuse. An empty list means the index is clean."""
    loaded = load_release(path)
    problems = []
    listed = set(loaded.manifest.chunk_ids)
    if not listed:
        problems.append("the manifest lists no chunk ids (release written before chunk-id listing)")
    for chunk in loaded.chunks:
        if listed and chunk.id not in listed:
            problems.append(f"{chunk.id}: not in the manifest")
        if chunk.checksum and sha256(chunk.text.encode("utf-8")).hexdigest() != chunk.checksum:
            problems.append(f"{chunk.id}: text does not match its checksum")
    problems += admission_problems(loaded.chunks, sources)
    return problems
