"""The pipeline CLI end to end, and the shipped synthetic development corpus."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import httpx
import pytest

from companion_api.rag import embeddings, pipeline
from companion_api.rag.chunking import chunk_documents, embedding_text
from companion_api.rag.corpus import SYNTHETIC_CONTENT_TYPES, load_corpus, parse_eval
from companion_api.rag.embeddings import HashingEmbedder
from companion_api.rag.pipeline import main
from companion_api.rag.release import load_release

ROOT = Path(__file__).resolve().parents[1]
DEV_CORPUS = ROOT / "corpus" / "dev-app-help"


def dev_documents():
    corpus, report = load_corpus(DEV_CORPUS)
    assert report.ok, report.format()
    return corpus.documents


def document_texts():
    """Every piece of document text that must never reach the build output."""
    for document in dev_documents():
        yield document.title
        yield from (unit.text for unit in document.units)
        yield from document.questions
        if document.answer:
            yield document.answer


def build(tmp_path, *extra, release_id="dev-test-1"):
    arguments = ["build", str(DEV_CORPUS), "--out", str(tmp_path / "releases"), "--embedding-model", "hashing"]
    return main(arguments + (["--release-id", release_id] if release_id else []) + list(extra))


def write_corpus(root, document):
    (root / "documents").mkdir(parents=True)
    (root / "corpus.json").write_text(json.dumps({"schemaVersion": 1, "id": "tmp-corpus", "title": "Tmp"}),
                                      encoding="utf-8")
    (root / "documents" / f"{document['id']}.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def real_document(**overrides):
    """Approved, non-synthetic and shaped like reviewed content; the text is an obvious placeholder."""
    data = {"schemaVersion": 1, "id": "real-doc", "kind": "passage", "title": "Placeholder title", "language": "en",
            "ageBands": ["10-11"], "contentType": "lesson", "curriculumPolicy": "placeholder-policy",
            "synthetic": False, "source": {"work": "Placeholder work", "edition": "1", "publisher": "Placeholder press",
                                           "license": "placeholder"},
            "review": {"status": "approved", "reviewer": "Board member", "approvedOn": "2026-09-25"},
            "units": [{"id": "u1", "text": "Placeholder unit text.", "reference": "1"}]}
    data.update(overrides)
    return data


def test_shipped_dev_corpus_validates_with_zero_errors():
    corpus, report = load_corpus(DEV_CORPUS)
    assert report.ok and not report.warnings, report.format()
    documents = corpus.documents
    passages = [document for document in documents if document.kind == "passage"]
    answers = [document for document in documents if document.kind == "answer"]
    assert corpus.id == "dev-app-help" and len(passages) >= 10 and len(answers) >= 6
    # Synthetic app help only: never religious teaching, never presented as reviewed.
    assert all(document.synthetic and document.language == "en" and document.review.status == "draft"
               and document.content_type in SYNTHETIC_CONTENT_TYPES for document in documents)
    assert {document.file.rsplit(".", 1)[1] for document in documents} == {"json", "md"}
    assert {document.kind for document in documents if document.file.endswith(".md")} == {"passage", "answer"}
    assert any(unit.keep_with_next for document in passages for unit in document.units)
    assert sum(len({unit.section for unit in document.units}) > 1 for document in passages) >= 3
    assert all(len(document.units) > 1 for document in passages)


def test_dev_eval_cases_reference_only_existing_documents():
    ids = {document.id for document in dev_documents()}
    cases, issues = parse_eval(json.loads((DEV_CORPUS / "eval.json").read_text(encoding="utf-8")), ids)
    assert not issues and len(cases) >= 20
    for case in cases:
        retrieval = set(case.answer_types) == {"grounded", "reviewed_answer"}
        assert retrieval == bool(case.documents) and set(case.documents) <= ids
    covered = {answer_type for case in cases for answer_type in case.answer_types}
    assert covered == {"grounded", "reviewed_answer", "redirected", "safety", "abstained"}


def test_validate_prints_the_report_and_sets_the_exit_code(tmp_path, capsys):
    assert main(["validate", str(DEV_CORPUS)]) == 0
    output = capsys.readouterr().out
    assert "Corpus dev-app-help: 20 valid documents (11 passage, 9 answer)" in output and "0 errors" in output
    assert main(["validate", str(DEV_CORPUS), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["corpus"] == "dev-app-help" and report["documents"] == 20 and not report["issues"]
    broken = write_corpus(tmp_path / "broken", real_document(synthetic=True))
    assert main(["validate", str(broken), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert not report["ok"] and report["issues"][0]["field"] == "contentType"
    assert main(["validate", str(tmp_path / "missing")]) == 1
    assert main(["validate", str(DEV_CORPUS), "--max-chunk-words", "0"]) == 1


def test_build_verify_and_load_round_trip(tmp_path, capsys):
    assert build(tmp_path) == 0
    output = capsys.readouterr()
    path = tmp_path / "releases" / "dev-test-1"
    assert f"path:      {path}" in output.out and "embedder:  hashing / hashing-v1, 384 dimensions" in output.out
    release = load_release(path)
    documents = dev_documents()
    expected = chunk_documents(documents, 180)
    assert release.chunks == tuple(expected)
    manifest = release.manifest
    assert (manifest.release_id, manifest.channel, manifest.corpus_ids) == ("dev-test-1", "development",
                                                                            ("dev-app-help",))
    assert manifest.document_count == len(documents) == 20 and manifest.chunk_count == len(expected)
    assert manifest.pipeline == {"normalizer": "norm-v1", "chunker": "chunk-v1", "maxChunkWords": 180}
    assert manifest.review == {"approved": 0, "draft": 20, "synthetic": 20}
    assert manifest.embedder == HashingEmbedder().identity
    vectors = HashingEmbedder().embed_documents([embedding_text(chunk) for chunk in expected])
    assert all(abs(a - b) < 1e-6 for row, stored in zip(vectors, release.vectors) for a, b in zip(row, stored))

    assert main(["verify", str(path)]) == 0
    verified = capsys.readouterr().out
    assert "Release dev-test-1 verified" in verified and "channel:   development" in verified
    assert f"chunks:    {len(expected)} ({len(expected)} servable)" in verified
    assert main(["stats", str(path)]) == 0
    stats = capsys.readouterr().out
    words = [len(chunk.text.split()) for chunk in expected]
    assert f"{len(expected)} chunks from 20 documents" in stats and "language:      en " in stats
    assert f"average {sum(words) / len(words):.1f}, max {max(words)}" in stats
    assert "kind:          answer 9, passage" in stats and "review status: draft" in stats

    printed = output.out + output.err + verified + stats
    leaked = [text for text in document_texts() if text in printed]
    assert not leaked


def test_build_output_never_contains_document_text_even_with_warnings(tmp_path, capsys):
    assert build(tmp_path, "--max-chunk-words", "5") == 0
    output = capsys.readouterr()
    assert "warning" in output.out and "more than the 5-word chunk budget" in output.out
    assert not [text for text in document_texts() if text in output.out + output.err]


def test_default_release_id_and_embedder_come_from_the_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COMPANION_EMBEDDING_MODEL", "hashing")
    assert main(["build", str(DEV_CORPUS), "--out", str(tmp_path)]) == 0
    (release,) = tmp_path.iterdir()
    assert re.fullmatch(r"dev-app-help-\d{14}", release.name)
    assert load_release(release).manifest.embedder.name == "hashing"


def test_embedding_settings_resolve_flags_then_environment(monkeypatch):
    for name in ("COMPANION_EMBEDDING_MODEL", "COMPANION_EMBEDDING_BASE_URL", "COMPANION_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert pipeline._embedding_settings(None, None) == ("qwen3-embedding:0.6b", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("COMPANION_LLM_BASE_URL", "http://10.0.0.5:11434/v1")
    assert pipeline._embedding_settings(None, None)[1] == "http://10.0.0.5:11434/v1"
    monkeypatch.setenv("COMPANION_EMBEDDING_BASE_URL", "http://10.0.0.6:8080/v1")
    monkeypatch.setenv("COMPANION_EMBEDDING_MODEL", "other-model")
    assert pipeline._embedding_settings(None, None) == ("other-model", "http://10.0.0.6:8080/v1")
    assert pipeline._embedding_settings("hashing", "http://localhost:1/v1") == ("hashing", "http://localhost:1/v1")


def test_an_existing_release_id_is_refused(tmp_path, capsys):
    assert build(tmp_path) == 0
    before = (tmp_path / "releases" / "dev-test-1" / "manifest.json").read_bytes()
    assert build(tmp_path) == 1
    assert "already exists" in capsys.readouterr().err
    assert [path.name for path in (tmp_path / "releases").iterdir()] == ["dev-test-1"]
    assert (tmp_path / "releases" / "dev-test-1" / "manifest.json").read_bytes() == before
    assert build(tmp_path, release_id="Bad Id") == 1


def test_published_channel_needs_approved_real_documents(tmp_path, capsys):
    assert build(tmp_path, "--channel", "published") == 1
    assert "published channel needs every document approved and non-synthetic" in capsys.readouterr().err
    assert not (tmp_path / "releases").exists()
    draft = write_corpus(tmp_path / "draft", real_document(review={"status": "draft"}))
    assert main(["build", str(draft), "--out", str(tmp_path / "out"), "--embedding-model", "hashing",
                 "--channel", "published"]) == 1
    approved = write_corpus(tmp_path / "approved", real_document())
    assert main(["build", str(approved), "--out", str(tmp_path / "out"), "--embedding-model", "hashing",
                 "--channel", "published", "--release-id", "real-1"]) == 0
    manifest = load_release(tmp_path / "out" / "real-1").manifest
    assert manifest.channel == "published" and manifest.review == {"approved": 1, "draft": 0, "synthetic": 0}


def test_build_refuses_a_corpus_with_errors(tmp_path, capsys):
    root = write_corpus(tmp_path / "bad", real_document(synthetic=True))
    assert main(["build", str(root), "--out", str(tmp_path / "out"), "--embedding-model", "hashing"]) == 1
    output = capsys.readouterr()
    assert "contentType" in output.out and "Build refused" in output.err
    assert not (tmp_path / "out").exists()


def test_unreachable_embedding_endpoint_fails_with_a_way_forward(tmp_path, monkeypatch, capsys):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    def offline_embedder(model, base_url):
        return embeddings.OpenAICompatibleEmbedder(base_url, model, client=httpx.Client(
            transport=httpx.MockTransport(refuse)))

    monkeypatch.setattr(embeddings, "embedder_for", offline_embedder)
    assert build(tmp_path, "--embedding-model", "qwen3-embedding:0.6b") == 1
    error = capsys.readouterr().err
    assert "qwen3-embedding:0.6b at http://127.0.0.1:11434/v1" in error and "unreachable" in error
    assert "--embedding-model hashing" in error and "Ollama" in error
    assert not (tmp_path / "releases").exists()


def test_a_public_embedding_endpoint_is_refused(tmp_path, capsys):
    assert build(tmp_path, "--embedding-model", "qwen3-embedding:0.6b",
                 "--embedding-base-url", "https://api.example.com/v1") == 1
    error = capsys.readouterr().err
    assert "private network" in error or "private IP" in error
    assert "--embedding-model hashing" in error


def test_verify_and_stats_refuse_a_tampered_release(tmp_path, capsys):
    assert build(tmp_path) == 0
    chunks = tmp_path / "releases" / "dev-test-1" / "chunks.jsonl"
    chunks.write_text(chunks.read_text(encoding="utf-8").replace("finishing", "skipping"), encoding="utf-8")
    capsys.readouterr()
    assert main(["verify", str(chunks.parent)]) == 1
    assert main(["stats", str(chunks.parent)]) == 1
    assert "Release refused: chunks.jsonl" in capsys.readouterr().err
    assert main(["verify", str(tmp_path / "missing")]) == 1


def test_the_module_runs_as_a_command():
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run([sys.executable, "-m", "companion_api.rag.pipeline", "validate", str(DEV_CORPUS)],
                            env=environment, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert b"0 errors, 0 warnings." in result.stdout
    usage = subprocess.run([sys.executable, "-m", "companion_api.rag.pipeline"], env=environment,
                           capture_output=True, timeout=60)
    assert usage.returncode == 2 and b"validate" in usage.stderr


@pytest.mark.parametrize("command", ["validate", "build", "verify", "import-markdown", "stats"])
def test_every_subcommand_has_help(command, capsys):
    with pytest.raises(SystemExit) as exit_:
        main([command, "--help"])
    assert exit_.value.code == 0 and "usage:" in capsys.readouterr().out
