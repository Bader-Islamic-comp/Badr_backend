"""The shared contract between the data pipeline and the RAG runtime."""
import json

import httpx
import pytest

from companion_api.rag import normalize
from companion_api.rag.embeddings import EmbeddingError, HashingEmbedder, OpenAICompatibleEmbedder, cosine
from companion_api.rag.endpoints import EndpointError, require_private_endpoint
from companion_api.rag.release import ReleaseError, load_release, write_release
from companion_api.rag.types import Chunk, EmbedderIdentity, ReleaseManifest


def chunk(document_id="app-help-stars", number=1, **overrides):
    values = dict(id=f"{document_id}#{number}", document_id=document_id, kind="passage", title="How stars work",
                  language="en", age_bands=("7-9",), content_type="app_help", madhhab=(), review_status="draft",
                  synthetic=True, text="Stars are earned by finishing lessons.",
                  search_text="stars are earned by finishing lessons", references=("part 1",),
                  source_label="Robert's guide · part 1", unit_ids=("u1",))
    values.update(overrides)
    return Chunk(**values)


def manifest(release_id="dev-test-1", dimensions=384):
    return ReleaseManifest(release_id=release_id, created_at="", channel="development", corpus_ids=("dev",),
                           document_count=0, chunk_count=0,
                           embedder=EmbedderIdentity("hashing", "hashing-v1", dimensions))


def test_search_text_folds_but_canonical_text_is_untouched():
    arabic = "\u0623\u064e\u0644\u0652\u062d\u064e\u0645\u0652\u062f\u064f"  # voweled, hamza on alef
    assert normalize.canonical(f"  {arabic}  ") == arabic
    assert normalize.search_text(arabic) == "\u0627\u0644\u062d\u0645\u062f"
    assert normalize.search_text("Learning STARS, earned!") == "learning stars earned"
    assert normalize.search_text(normalize.search_text("Ｓｔａｒｓ \u0640")) == "stars"
    assert normalize.content_tokens("How do I earn the stars?") == ["earn", "stars"]
    assert normalize.detect_language("\u0645\u0627 \u0647\u0648 \u0627\u0644\u0646\u062c\u0645 star") == "ar"
    assert normalize.detect_language("What is a star?") == "en"


def test_hashing_embedder_is_deterministic_and_prefers_shared_words():
    embedder = HashingEmbedder()
    first, second = HashingEmbedder().embed_query("earning stars"), embedder.embed_query("earning stars")
    assert first == second and abs(cosine(first, first) - 1) < 1e-9
    related, unrelated = embedder.embed_documents(["How learning stars are earned", "Choosing a look for Robert"])
    assert cosine(first, related) > cosine(first, unrelated)


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434/v1", "http://localhost:8080/v1/", "http://10.0.0.5:11434/v1",
                                 "http://192.168.1.20/v1", "http://[::1]:11434/v1"])
def test_private_endpoints_are_accepted(url):
    assert not require_private_endpoint(url).endswith("/")


@pytest.mark.parametrize("url", ["https://api.example.com/v1", "http://8.8.8.8/v1", "http://0.0.0.0:11434/v1",
                                 "http://user:pw@127.0.0.1/v1", "http://127.0.0.1/v1?key=x", "ftp://127.0.0.1/v1"])
def test_provider_endpoints_are_refused(url):
    with pytest.raises(EndpointError):
        require_private_endpoint(url)


def test_openai_compatible_embedder_batches_and_instructs_queries():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [3.0, 4.0]} for i, _ in enumerate(body["input"])]})

    embedder = OpenAICompatibleEmbedder("http://127.0.0.1:11434/v1", dimensions=2, batch_size=2,
                                        client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert embedder.embed_documents(["a", "b", "c"]) == [[0.6, 0.8]] * 3
    assert [len(body["input"]) for body in seen] == [2, 1]
    embedder.embed_query("stars?")
    assert seen[-1]["input"][0].startswith("Instruct: ") and seen[-1]["input"][0].endswith("\nQuery:stars?")


def test_openai_compatible_embedder_errors_never_echo_input():
    embedder = OpenAICompatibleEmbedder("http://127.0.0.1:11434/v1", dimensions=3,
                                        client=httpx.Client(transport=httpx.MockTransport(
                                            lambda request: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]}))))
    with pytest.raises(EmbeddingError) as error:
        embedder.embed_query("SYNTHETIC_SECRET_QUESTION")
    assert "SYNTHETIC_SECRET_QUESTION" not in str(error.value)


def test_release_round_trip_and_immutability(tmp_path):
    chunks = [chunk(), chunk("app-help-looks", 1, kind="answer", questions=("How do I get a new look?",),
                             text="Spend learning stars on the Style tab.")]
    vectors = HashingEmbedder().embed_documents([c.text for c in chunks])
    path = write_release(tmp_path, manifest(), chunks, vectors)
    loaded = load_release(path)
    assert loaded.chunks == tuple(chunks)
    assert loaded.manifest.chunk_count == 2 and loaded.manifest.document_count == 2
    assert all(abs(a - b) < 1e-6 for a, b in zip(loaded.vectors[1], vectors[1]))
    with pytest.raises(ReleaseError):
        write_release(tmp_path, manifest(), chunks, vectors)
    assert [p.name for p in tmp_path.iterdir()] == ["dev-test-1"]


def test_tampered_release_is_refused(tmp_path):
    path = write_release(tmp_path, manifest(), [chunk()], HashingEmbedder().embed_documents(["x"]))
    chunks_file = path / "chunks.jsonl"
    chunks_file.write_text(chunks_file.read_text(encoding="utf-8").replace("finishing", "skipping"), encoding="utf-8")
    with pytest.raises(ReleaseError):
        load_release(path)


def test_chunks_validate_ids_and_answer_questions():
    with pytest.raises(ValueError):
        chunk(id="other-doc#1")
    with pytest.raises(ValueError):
        chunk(kind="answer")
    assert chunk().servable and chunk(synthetic=False, review_status="approved").servable
    assert not chunk(synthetic=False).servable
