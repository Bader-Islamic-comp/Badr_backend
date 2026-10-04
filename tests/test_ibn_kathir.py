"""Tafsir Ibn Kathir import (corpusprep/ibn_kathir.py, ingest.ibn_kathir_documents). Placeholder text only."""
import json

import pytest

from companion_api.corpusprep import ibn_kathir, ingest
from companion_api.rag.corpus import parse_document

PASSAGE = "شرح تجريبي للآيتين.\n\nفقرة ثانية من الشرح [[ملاحظة المحقق: في نسخة أخرى زيادة.]] تكمل المعنى."


def _file(tmp_path, surah, rows):
    path = tmp_path / f"{surah}.json"
    path.write_text(json.dumps([{"surah": str(s), "ayah": str(a), "text": t} for s, a, t in rows],
                               ensure_ascii=False), encoding="utf-8")
    return path


def test_consecutive_ayat_sharing_one_text_are_one_section(tmp_path):
    texts = ibn_kathir.parse_surah(_file(tmp_path, 1, [(1, 1, PASSAGE), (1, 2, PASSAGE), (1, 3, "شرح ثالث.")]), 1)
    records, summary = ibn_kathir.sections(texts, {(1, 1), (1, 2), (1, 3)})
    assert [record["section_id"] for record in records] == ["ibn-kathir:1:1-2", "ibn-kathir:1:3"]
    assert records[0]["quran_refs"] == ["quran:1:1", "quran:1:2"] and records[0]["source_id"] == "ibn-kathir-ar-001"
    assert records[0]["text"] == PASSAGE and records[0]["editor_notes"] == 1
    assert summary["sections"] == 2 and summary["missing_ayat"] == 0


def test_the_same_text_after_a_gap_starts_a_new_section(tmp_path):
    texts = {(1, 1): "أ.", (1, 2): "ب.", (1, 3): "أ."}
    records, _ = ibn_kathir.sections(texts, set(texts))
    assert [record["section_id"] for record in records] == ["ibn-kathir:1:1", "ibn-kathir:1:2", "ibn-kathir:1:3"]


@pytest.mark.parametrize("rows, surah, message", [
    ([(2, 1, "x")], 1, "in the file for surah 1"),
    ([(1, 1, "x"), (1, 1, "y")], 1, "appears twice"),
])
def test_a_malformed_file_is_refused(tmp_path, rows, surah, message):
    with pytest.raises(ibn_kathir.TafsirError, match=message):
        ibn_kathir.parse_surah(_file(tmp_path, surah, rows), surah)


def test_records_for_ayat_that_do_not_exist_are_refused():
    with pytest.raises(ibn_kathir.TafsirError, match="do not exist"):
        ibn_kathir.sections({(1, 9): "x"}, {(1, 1)})


def test_display_text_drops_the_editors_notes_and_keeps_paragraphs():
    assert ibn_kathir.editor_notes(PASSAGE) == ["ملاحظة المحقق: في نسخة أخرى زيادة."]
    assert ibn_kathir.paragraphs(PASSAGE) == ["شرح تجريبي للآيتين.", "فقرة ثانية من الشرح تكمل المعنى."]


class _Registry:
    sources = [{"source_id": "ibn-kathir-ar-001", "edition": "e", "publisher": "p", "license": "l", "sha256": None}]

    def get(self, source_id):
        return next(source for source in self.sources if source["source_id"] == source_id)


def test_each_section_becomes_a_valid_tier_one_tafsir_document():
    records, _ = ibn_kathir.sections({(1, 1): PASSAGE, (1, 2): PASSAGE}, {(1, 1), (1, 2)})
    built = ingest.ibn_kathir_documents(records, {1: "الفاتحة"}, _Registry(), {(1, 2): {"id": "adam", "name": "آدم"}})
    [data] = built.documents
    assert data["id"] == "tafsir-ibn-kathir-001-001-002" and data["contentType"] == "tafsir" and data["tier"] == 1
    assert data["sourceIds"] == ["ibn-kathir-ar-001"] and data["prophetId"] == "adam"
    assert [unit["sourceRefs"] for unit in data["units"]] == [["quran:1:1-2"], ["quran:1:1-2"]]
    document, issues = parse_document(data, "x.json")
    assert document is not None and not [issue for issue in issues if issue.severity == "error"]
