"""Task 15: nothing from a conversation or about a child can reach the vector store."""
import ast
import json
from pathlib import Path

import pytest

from companion_api.rag import normalize
from companion_api.rag.release import ReleaseError, load_release, scan, write_release
from companion_api.rag.types import Chunk, EmbedderIdentity, ReleaseManifest

SRC = Path(__file__).resolve().parents[1] / "src" / "companion_api"
# Everything that handles a child's turn: routing, chat, generation, verification, the API and storage.
CONVERSATION_MODULES = ["rag/chat.py", "rag/service.py", "rag/router.py", "rag/generator.py", "rag/grounding.py",
                        "rag/responses.py", "rag/prompts.py", "rag/retriever.py", "rag/ask.py", "main.py",
                        "store.py", "schemas.py", "safety.py", "worker.py", "content.py"]
FORBIDDEN_MODULES = ("pipeline", "corpusprep", "governance", "chunking")
FORBIDDEN_NAMES = ("write_release", "admission_problems", "embed_documents", "chunk_documents", "chunk_document")
SOURCES = {"good-source": "pending_legal", "unclear-source": "candidate"}


def _chunk(chunk_id="doc-a#1", *, text="A registered passage.", content_type="tafsir", synthetic=False,
           source_ids=("good-source",)):
    return Chunk(id=chunk_id, document_id=chunk_id.split("#")[0], kind="passage", title="t", language="en",
                 age_bands=("7-9",), content_type=content_type, madhhab=(), review_status="draft",
                 synthetic=synthetic, text=text, search_text=normalize.search_text(text), references=(),
                 source_label="t", unit_ids=("u1",), source_ids=source_ids)


def _write(tmp_path, chunks, release_id="rel-1"):
    manifest = ReleaseManifest(release_id, "", "development", ("c",), 0, 0, EmbedderIdentity("hashing", "h", 2))
    return write_release(tmp_path, manifest, chunks, [[1.0, 0.0]] * len(chunks), sources=SOURCES)


@pytest.mark.parametrize("chunk, reason", [
    # A child's message indexed as if it were content: no registered source.
    (_chunk("turn-123#1", text="child turn text (synthetic placeholder)", source_ids=()), "cites no registered source"),
    # The same text dressed up as synthetic app help, under a conversation content type.
    (_chunk("turn-124#1", content_type="conversation", synthetic=True, source_ids=()), "not indexable"),
    # Synthetic text claiming a religious content type.
    (_chunk("turn-125#1", content_type="hadith", synthetic=True, source_ids=()), "app help or orientation"),
    # A made-up source id, and a registered source whose licence is unclear.
    (_chunk("doc-b#1", source_ids=("chat-log",)), "not in the registry"),
    (_chunk("doc-c#1", source_ids=("unclear-source",)), "is candidate"),
])
def test_conversation_or_unregistered_text_is_never_indexed(tmp_path, chunk, reason):
    with pytest.raises(ReleaseError, match=reason):
        _write(tmp_path, [_chunk(), chunk])
    assert not any(tmp_path.iterdir())  # nothing was written


def test_without_a_registry_real_content_is_refused(tmp_path):
    manifest = ReleaseManifest("rel-1", "", "development", ("c",), 0, 0, EmbedderIdentity("hashing", "h", 2))
    with pytest.raises(ReleaseError, match="no source registry"):
        write_release(tmp_path, manifest, [_chunk()], [[1.0, 0.0]])


def test_chunk_schema_refuses_undefined_fields(tmp_path):
    path = _write(tmp_path, [_chunk()])
    data = json.loads((path / "chunks.jsonl").read_text())
    with pytest.raises(TypeError):
        Chunk.from_json({**data, "childUtterance": "x"})


def test_scan_finds_every_chunk_in_the_manifest_and_catches_extras(tmp_path):
    path = _write(tmp_path, [_chunk(), _chunk("doc-d#1", text="Another passage.")])
    assert scan(path, SOURCES) == []
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["chunkIds"] == ["doc-a#1", "doc-d#1"]
    manifest["chunkIds"] = ["doc-a#1", "doc-x#1"]  # an id the index does not match
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ReleaseError, match="chunk ids do not match the manifest"):
        load_release(path)


def test_scan_reports_a_source_blocked_after_release(tmp_path):
    path = _write(tmp_path, [_chunk()])
    assert scan(path, {"good-source": "rejected"}) == ["doc-a#1: source good-source is rejected"]


def _imports(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return modules, names


@pytest.mark.parametrize("module", CONVERSATION_MODULES)
def test_conversation_modules_cannot_reach_the_index_writer(module):
    modules, names = _imports(SRC / module)
    for forbidden in FORBIDDEN_MODULES:
        assert not any(forbidden in part.split(".") for part in modules), f"{module} imports {forbidden}"
    assert not names & set(FORBIDDEN_NAMES), f"{module} uses {names & set(FORBIDDEN_NAMES)}"
