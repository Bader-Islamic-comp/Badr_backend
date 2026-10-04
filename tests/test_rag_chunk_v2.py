"""Schema v2 documents and chunk-v2 (doc/rag-system.md §13). Placeholder text only, no sacred text."""
import json

from companion_api.rag import normalize
from companion_api.rag.chunking import chunk_document, embedding_text
from companion_api.rag.corpus import parse_document
from companion_api.rag.release import load_release, write_release
from companion_api.rag.types import Chunk, EmbedderIdentity, ReleaseManifest


def _doc(**extra):
    data = {"schemaVersion": 2, "id": "hadith-demo-1", "kind": "passage", "title": "Demo 1", "language": "en",
            "ageBands": ["7-9", "10-11"], "contentType": "hadith", "madhhab": [], "curriculumPolicy": "test",
            "synthetic": False, "source": {"work": "Demo", "edition": "1", "publisher": "Test", "translator": None,
                                           "license": "test", "checksum": None},
            "grading": "sahih", "review": {"status": "draft", "reviewer": None, "approvedOn": None, "supersedes": None},
            "units": [{"id": "u1", "text": "alpha beta gamma. delta epsilon zeta.", "reference": "demo:1",
                       "sourceRefs": ["demo:1"], "parts": ["alpha beta gamma.", "delta epsilon zeta."]}],
            "tier": 0, "contextHeader": "Demo header", "clusterId": "c-1", "clusterRefs": ["other:7"],
            "sourceIds": ["demo-source"], "topics": ["kindness"]}
    data.update(extra)
    return data


def test_v1_documents_reject_v2_fields():
    data = _doc(schemaVersion=1)
    document, issues = parse_document(data, "x.json")
    assert document is None and any("unknown field" in issue.message for issue in issues)


def test_parts_must_be_verbatim_and_in_order():
    data = _doc()
    data["units"][0]["parts"] = ["delta epsilon zeta.", "alpha beta gamma."]
    assert parse_document(data, "x.json")[0] is None
    data["units"][0]["parts"] = ["alpha beta GAMMA.", "delta epsilon zeta."]
    assert parse_document(data, "x.json")[0] is None


def test_bad_source_refs_and_cluster_refs_without_cluster():
    data = _doc(clusterId=None)
    data["units"][0]["sourceRefs"] = ["not a ref"]
    _, issues = parse_document(data, "x.json")
    fields = {issue.field for issue in issues}
    assert "units[u1].sourceRefs[#1]" in fields and "clusterRefs" in fields


def test_chunk_v2_parent_children_and_metadata():
    document, issues = parse_document(_doc(), "x.json")
    assert document and not [issue for issue in issues if issue.severity == "error"]
    parent, *children = chunk_document(document)
    assert parent.id == "hadith-demo-1#1" and parent.parent_id is None and not parent.is_child
    assert parent.source_refs == ("demo:1",) and parent.cluster_refs == ("other:7",) and parent.tier == 0
    assert parent.text == "alpha beta gamma. delta epsilon zeta."  # the narration is never split
    assert [child.id for child in children] == ["hadith-demo-1#2", "hadith-demo-1#3"]
    assert all(child.is_child and child.parent_id == parent.id for child in children)
    assert children[0].text == "alpha beta gamma." and "part 1 of 2" in children[0].context_header
    assert embedding_text(parent).startswith("Demo header\n")
    assert len(parent.checksum) == 64


def test_children_per_unit_for_multi_unit_chunks():
    data = _doc(contentType="quran", grading=None, children="units", clusterId=None, clusterRefs=[])
    data["units"] = [{"id": f"a{n}", "text": f"verse text {n}", "reference": f"quran:1:{n}",
                      "sourceRefs": [f"quran:1:{n}"], "section": "s1"} for n in (1, 2, 3)]
    document, _ = parse_document(data, "x.json")
    parent, *children = chunk_document(document)
    assert parent.source_refs == ("quran:1:1", "quran:1:2", "quran:1:3")
    assert [child.source_refs for child in children] == [("quran:1:1",), ("quran:1:2",), ("quran:1:3",)]


def test_chunk_v1_release_still_loads(tmp_path):
    v1 = {"id": "app-help-x#1", "documentId": "app-help-x", "kind": "passage", "title": "T", "language": "en",
          "ageBands": ["7-9"], "contentType": "app_help", "madhhab": [], "reviewStatus": "draft", "synthetic": True,
          "text": "hello", "searchText": "hello", "references": [], "sourceLabel": "T", "unitIds": ["u1"],
          "questions": []}
    chunk = Chunk.from_json(v1)
    assert chunk.source_refs == () and chunk.parent_id is None
    manifest = ReleaseManifest("rel-v1", "", "development", ("x",), 0, 0, EmbedderIdentity("hashing", "h", 2),
                               pipeline={"normalizer": "norm-v1", "chunker": "chunk-v1"})
    path = write_release(tmp_path, manifest, [chunk], [[0.0, 1.0]])
    lines = (path / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    assert load_release(path).chunks[0].text == "hello" and json.loads(lines[0])["sourceRefs"] == []


def test_norm_v3_maps_rasm_only_for_quran_text():
    assert normalize.search_text("Stars, STARS!") == "stars stars"
    word, target = next(iter(normalize.RASM.items()))
    assert normalize.search_text(word, quranic=True) == target and normalize.search_text_v1(word) == word
    # A question, a hadith or app help is never mapped: these keys are ordinary words there.
    assert normalize.search_text(word) == word
    for ordinary in ("شعير", "ثلث", "تبرك"):  # barley, a third, seeking blessing
        assert ordinary in normalize.RASM and normalize.search_text(ordinary) == ordinary


def test_quran_chunks_are_searched_and_embedded_in_simple_spelling():
    word, target = next(iter(normalize.RASM.items()))
    document, _ = parse_document(_doc(contentType="quran", grading=None, clusterId=None, clusterRefs=[], units=[
        {"id": "u1", "text": f"{word} alpha.", "reference": "demo:1", "sourceRefs": ["demo:1"]}]), "x.json")
    chunk = chunk_document(document)[0]
    assert chunk.text.startswith(word) and target in chunk.search_text.split()
    assert target in embedding_text(chunk) and word not in embedding_text(chunk).split()


def test_arabic_forms_match_across_clitics():
    forms = normalize.arabic_forms
    assert forms("والملايكه") & forms("للملايكه")  # and-the-angels, to-the-angels
    assert "ادم" in forms("لادم") and forms("كتابهم") & forms("الكتاب")  # the ك of كتاب is a root letter
    assert forms("في") == {"في"} and forms("stars") == {"stars"}
    assert not forms("ثلث") & forms("ثلاث")
