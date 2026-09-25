"""`chunk-v1` invariants (doc/rag-system.md section 4)."""
from pathlib import Path

import pytest

from companion_api.rag import normalize
from companion_api.rag.chunking import chunk_document, chunk_documents, embedding_text, source_label
from companion_api.rag.corpus import keep_groups, load_corpus, parse_document, word_count

DEV_CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "dev-app-help"


def words(count, tag="w"):
    return " ".join(f"{tag}{n}" for n in range(count))


def document(units, doc_id="doc-one", **overrides):
    """`units` are (text, section, keepWithNext, reference) tuples; ids are u1, u2, ..."""
    data = {"schemaVersion": 1, "id": doc_id, "kind": "passage", "title": "Test document", "language": "en",
            "ageBands": ["7-9"], "contentType": "app_help", "madhhab": [], "curriculumPolicy": "dev-synthetic",
            "synthetic": True, "source": {"work": "Robert's guide"}, "review": {"status": "draft"},
            "units": [{"id": f"u{n}", "text": text, "section": section, "keepWithNext": keep, "reference": reference}
                      for n, (text, section, keep, reference) in enumerate(units, 1)]}
    data.update(overrides)
    built, issues = parse_document(data, "documents/test.json")
    assert built is not None, issues
    return built


def unit(text, section=None, keep=False, reference=None):
    return text, section, keep, reference


def groups(chunks):
    return [list(chunk.unit_ids) for chunk in chunks]


def test_units_are_packed_to_the_budget_and_never_split():
    source = document([unit(words(40, "a")), unit(words(40, "b")), unit(words(40, "c")), unit(words(200, "d")),
                       unit(words(10, "e"))])
    chunks = chunk_document(source, max_chunk_words=100)
    assert groups(chunks) == [["u1", "u2"], ["u3"], ["u4"], ["u5"]]
    assert chunks[2].text == source.units[3].text and word_count(chunks[2].text) == 200
    assert chunks[0].text == source.units[0].text + "\n\n" + source.units[1].text


def test_sections_are_never_crossed():
    source = document([unit("One.", "A"), unit("Two.", "A"), unit("Three.", "B"), unit("Four.", "B"),
                       unit("Five.", "A"), unit("Six.")])
    assert groups(chunk_document(source)) == [["u1", "u2"], ["u3", "u4"], ["u5"], ["u6"]]


def test_keep_with_next_units_travel_together():
    source = document([unit(words(30, "a")), unit(words(15, "b"), keep=True), unit(words(15, "c")),
                       unit(words(10, "d"))])
    assert groups(chunk_document(source, max_chunk_words=50)) == [["u1"], ["u2", "u3", "u4"]]
    plain = document([unit(words(30, "a")), unit(words(15, "b")), unit(words(15, "c")), unit(words(10, "d"))])
    assert groups(chunk_document(plain, max_chunk_words=50)) == [["u1", "u2"], ["u3", "u4"]]
    chain = document([unit(words(30, "a"), keep=True), unit(words(30, "b"), keep=True), unit(words(30, "c")),
                      unit(words(5, "d"))])
    assert groups(chunk_document(chain, max_chunk_words=50)) == [["u1", "u2", "u3"], ["u4"]]


def test_chunk_ids_are_stable_and_numbered_from_one():
    source = document([unit(words(100, "a")), unit(words(100, "b")), unit(words(100, "c"))])
    first, second = chunk_document(source), chunk_document(source)
    assert first == second
    assert [chunk.id for chunk in first] == ["doc-one#1", "doc-one#2", "doc-one#3"]
    assert all(chunk.document_id == "doc-one" and chunk.kind == "passage" for chunk in first)


def test_source_labels_name_the_work_and_the_reference_span():
    source = document([unit("One.", reference="part 1"), unit("Two.", reference="part 1"), unit("Three."),
                       unit("Four.", reference="part 3")])
    (chunk,) = chunk_document(source)
    assert chunk.references == ("part 1", "part 3")
    assert chunk.source_label == "Robert's guide \u00b7 part 1\u2013part 3"
    assert chunk_document(document([unit("One.", reference="part 2")]))[0].source_label == \
        "Robert's guide \u00b7 part 2"
    assert chunk_document(document([unit("One.")]))[0].source_label == "Robert's guide"
    untitled = document([unit("One.", reference="p1")], source={}, title="Stars")
    assert source_label(untitled, ("p1",)) == "Stars \u00b7 p1"


def test_answer_documents_become_exactly_one_chunk_with_questions():
    data = {"schemaVersion": 1, "id": "answer-stars", "kind": "answer", "title": "Earning stars", "language": "en",
            "ageBands": ["7-9", "10-11"], "contentType": "app_help", "curriculumPolicy": "dev-synthetic",
            "synthetic": True, "source": {"work": "Robert's guide"}, "review": {"status": "draft"},
            "questions": ["How do I earn STARS?", "Where do stars come from?"],
            "answer": "You earn learning stars by finishing lessons."}
    source, _ = parse_document(data, "documents/answer-stars.json")
    (chunk,) = chunk_document(source, max_chunk_words=3)
    assert chunk.id == "answer-stars#1" and chunk.kind == "answer" and chunk.text == source.answer
    assert chunk.questions == ("How do I earn STARS?", "Where do stars come from?")
    assert chunk.search_text == normalize.search_text(
        "How do I earn STARS?\nWhere do stars come from?\n" + source.answer)
    assert chunk.references == () and chunk.unit_ids == () and chunk.source_label == "Robert's guide"
    assert embedding_text(chunk) == ("Earning stars\nHow do I earn STARS?\nWhere do stars come from?\n"
                                     "You earn learning stars by finishing lessons.")


def test_chunks_carry_review_status_provenance_and_filters():
    approved = document([unit("Placeholder unit.", reference="1")], doc_id="real-doc", synthetic=False,
                        contentType="lesson", madhhab=["placeholder-school"], ageBands=["10-11", "12-14"],
                        source={"work": "Placeholder work", "edition": "1", "publisher": "Placeholder press",
                                "license": "placeholder"},
                        review={"status": "approved", "reviewer": "Board member", "approvedOn": "2026-09-25"})
    (chunk,) = chunk_document(approved)
    assert (chunk.review_status, chunk.synthetic, chunk.content_type) == ("approved", False, "lesson")
    assert chunk.madhhab == ("placeholder-school",) and chunk.age_bands == ("10-11", "12-14") and chunk.servable
    draft = document([unit("Placeholder unit.")], doc_id="real-draft", synthetic=False, contentType="lesson",
                     source=approved.to_json()["source"])
    assert not chunk_document(draft)[0].servable
    assert chunk_document(document([unit("Synthetic help.")]))[0].servable


def test_search_text_is_a_separate_view_of_untouched_canonical_text():
    voweled = "\u0623\u064e\u0644\u0652\u062d\u064e\u0645\u0652\u062f\u064f \u0644\u0650\u0644\u0651\u064e\u0647\u0650"
    source = document([unit(voweled)], language="ar", title="\u0645\u062b\u0627\u0644")
    (chunk,) = chunk_document(source)
    # NFC may reorder stacked marks (fatha before shadda) but never drops or folds one.
    assert chunk.text == normalize.canonical(voweled) and sorted(chunk.text) == sorted(voweled)
    assert chunk.search_text == normalize.search_text(voweled) == "\u0627\u0644\u062d\u0645\u062f \u0644\u0644\u0647"
    assert embedding_text(chunk) == "\u0645\u062b\u0627\u0644\n" + chunk.text


@pytest.mark.parametrize("budget", [1, 12, 40, 180])
def test_dev_corpus_chunks_hold_every_invariant(budget):
    corpus, report = load_corpus(DEV_CORPUS, max_chunk_words=budget)
    assert not report.errors
    chunks = chunk_documents(corpus.documents, budget)
    assert [chunk.document_id for chunk in chunks] == sorted(chunk.document_id for chunk in chunks)
    by_document = {}
    for chunk in chunks:
        by_document.setdefault(chunk.document_id, []).append(chunk)
    for source in corpus.documents:
        produced = by_document[source.id]
        assert [chunk.id for chunk in produced] == [f"{source.id}#{n}" for n in range(1, len(produced) + 1)]
        if source.kind == "answer":
            assert len(produced) == 1 and produced[0].questions == source.questions
            continue
        units = {item.id: item for item in source.units}
        # Every unit exactly once, whole and in reading order.
        assert [unit_id for chunk in produced for unit_id in chunk.unit_ids] == [item.id for item in source.units]
        for chunk in produced:
            members = [units[unit_id] for unit_id in chunk.unit_ids]
            assert chunk.text == "\n\n".join(item.text for item in members)
            assert len({item.section for item in members}) == 1
            assert chunk.search_text == normalize.search_text(chunk.text)
            whole_groups = [group for group in keep_groups(source.units) if group[0].id in chunk.unit_ids]
            assert word_count(chunk.text) <= budget or len(whole_groups) == 1
        for group in keep_groups(source.units):
            assert len({chunk.id for chunk in produced for item in group if item.id in chunk.unit_ids}) == 1


def test_invalid_budget_is_refused():
    with pytest.raises(ValueError):
        chunk_document(document([unit("One.")]), max_chunk_words=0)
