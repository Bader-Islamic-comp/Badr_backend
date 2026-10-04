"""Serving chunk-v2 releases: children served as their parent (hybrid-rrf-v2), and the published channel
refused anything whose sources are not cleared, whatever builds it. Placeholder text only, no sacred text."""
import pytest

from companion_api.rag import normalize
from companion_api.rag.chunking import chunk_document, embedding_text
from companion_api.rag.corpus import parse_document
from companion_api.rag.embeddings import HashingEmbedder
from companion_api.rag.release import ReleaseError, load_release, scan, write_release
from companion_api.rag.retriever import HybridRetriever
from companion_api.rag.types import Chunk, ReleaseManifest

UNITS = ("The moon lights the night sky for travellers on the road.",
         "Stars help sailors find their way across the sea at night.",
         "The sun rises in the east and warms the fields every morning.")
SOURCES = {"demo-source": "pending_legal"}


def _document(**extra):
    data = {"schemaVersion": 2, "id": "sky-lesson", "kind": "passage", "title": "The sky", "language": "en",
            "ageBands": ["7-9", "10-11"], "contentType": "lesson", "madhhab": [], "curriculumPolicy": "test",
            "synthetic": False, "source": {"work": "Demo", "edition": "1", "publisher": "Test", "translator": None,
                                           "license": "test", "checksum": None},
            "review": {"status": "draft", "reviewer": None, "approvedOn": None, "supersedes": None},
            "units": [{"id": f"u{n}", "text": text, "reference": f"demo:{n}", "sourceRefs": [f"demo:{n}"]}
                      for n, text in enumerate(UNITS, 1)],
            "children": "units", "contextHeader": "Demo sky lesson", "sourceIds": ["demo-source"]}
    data.update(extra)
    document, issues = parse_document(data, "sky-lesson.json")
    assert document, [issue.message for issue in issues]
    return document


def _filler(number):
    text = f"Unrelated placeholder lesson {number} about finishing lessons and earning learning stars."
    return Chunk(id=f"filler-{number}#1", document_id=f"filler-{number}", kind="passage", title=f"Filler {number}",
                 language="en", age_bands=("7-9", "10-11"), content_type="lesson", madhhab=(), review_status="draft",
                 synthetic=False, text=text, search_text=normalize.search_text(text), references=(),
                 source_label="Filler", unit_ids=("u1",), source_ids=("demo-source",))


def _manifest(release_id, channel="development"):
    embedder = HashingEmbedder()
    return ReleaseManifest(release_id=release_id, created_at="", channel=channel, corpus_ids=("demo",),
                           document_count=0, chunk_count=0, embedder=embedder.identity)


def _release(tmp_path, chunks, release_id="sky-1", channel="development", sources=SOURCES):
    vectors = HashingEmbedder().embed_documents([embedding_text(chunk) for chunk in chunks])
    return write_release(tmp_path, _manifest(release_id, channel), chunks, vectors, sources=sources)


def test_a_passage_fills_one_slot_however_many_of_its_children_match(tmp_path):
    chunks = chunk_document(_document())
    parent, children = chunks[0], chunks[1:]
    assert len(children) == 3 and all(child.parent_id == parent.id for child in children)
    retriever = HybridRetriever(load_release(_release(tmp_path, chunks + [_filler(n) for n in range(6)])),
                                HashingEmbedder(), include_drafts=True)
    result = retriever.retrieve("How do sailors find their way with the stars at night?")
    ids = [candidate.chunk.id for candidate in result.candidates]
    assert ids[0] == parent.id and ids.count(parent.id) == 1
    assert not any(candidate.chunk.is_child for candidate in result.candidates)
    assert len(ids) == len(set(ids))


def test_a_question_only_a_child_matches_is_served_as_the_parent(tmp_path):
    chunks = chunk_document(_document())
    retriever = HybridRetriever(load_release(_release(tmp_path, chunks)), HashingEmbedder(), include_drafts=True)
    best = retriever.retrieve("sun rises east warms fields morning").candidates[0]
    assert best.chunk.id == "sky-lesson#1" and best.chunk.text.count("\n\n") == 2  # the whole passage


def test_a_child_whose_parent_is_missing_is_refused(tmp_path):
    chunks = chunk_document(_document())
    with pytest.raises(ReleaseError, match="parent outside the release"):
        _release(tmp_path, chunks[1:])


def _published_chunk(**overrides):
    values = {"id": "real-lesson#1", "document_id": "real-lesson", "kind": "passage", "title": "Real lesson",
              "language": "en", "age_bands": ("7-9",), "content_type": "lesson", "madhhab": (),
              "review_status": "approved", "synthetic": False, "text": "An approved placeholder passage.",
              "search_text": normalize.search_text("An approved placeholder passage."), "references": (),
              "source_label": "Real lesson", "unit_ids": ("u1",), "source_ids": ("demo-source",)}
    values.update(overrides)
    return Chunk(**values)


@pytest.mark.parametrize("status", ["pending_legal", "candidate", "rejected"])
def test_the_published_channel_needs_every_source_cleared(tmp_path, status):
    with pytest.raises(ReleaseError, match="may not be (indexed|published)"):
        _release(tmp_path, [_published_chunk()], release_id="pub-1", channel="published",
                 sources={"demo-source": status})
    assert not (tmp_path / "pub-1").exists()


@pytest.mark.parametrize("overrides", [{"review_status": "draft"},
                                       {"synthetic": True, "content_type": "app_help", "source_ids": ()}])
def test_the_published_channel_needs_approved_real_content(tmp_path, overrides):
    with pytest.raises(ReleaseError, match="approved, non-synthetic"):
        _release(tmp_path, [_published_chunk(**overrides)], release_id="pub-1", channel="published",
                 sources={"demo-source": "cleared"})


def test_a_cleared_release_publishes_and_the_scan_catches_a_withdrawn_clearance(tmp_path):
    path = _release(tmp_path, [_published_chunk()], release_id="pub-1", channel="published",
                    sources={"demo-source": "cleared"})
    assert load_release(path).manifest.channel == "published"
    assert scan(path, {"demo-source": "cleared"}) == []
    assert scan(path, {"demo-source": "pending_legal"}) == [
        "real-lesson#1: source demo-source is pending_legal, not cleared"]


def test_the_development_channel_still_accepts_pending_sources(tmp_path):
    path = _release(tmp_path, [_published_chunk(review_status="draft")], release_id="dev-1")
    assert scan(path, SOURCES) == []
