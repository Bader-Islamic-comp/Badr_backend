"""Quranpedia dumps (corpusprep/quranpedia.py), the Quran text comparison (corpusprep/quran_compare.py) and the
layer 0 documents built from them (ingest.translation_documents, ingest.quranpedia_tafsir_documents).

Arabic and English words here are placeholders, not Quran, tafsir or translation text. Combining marks are
built with chr() so the source shows which code point each test uses.
"""
import gzip
import json

import pytest

from companion_api.corpusprep import build, ingest, quran_compare as qc, quranpedia as qp
from companion_api.corpusprep.registry import Registry
from companion_api.corpusprep.segments import Segment
from companion_api.rag.chunking import chunk_document
from companion_api.rag.corpus import parse_document

FATHA, DAMMA, KASRA, SUKUN, SHADDA = chr(0x064E), chr(0x064F), chr(0x0650), chr(0x0652), chr(0x0651)
KFC_SUKUN, OPEN_TANWEEN, PAUSE = chr(0x06E1), chr(0x0656), chr(0x06DA)
TATWEEL, HAMZA_ABOVE, MADDAH, BOM, WASLA = chr(0x0640), chr(0x0654), chr(0x0653), chr(0xFEFF), chr(0x0671)
NBSP = chr(0x00A0)
MUJAHID = next(book for book in qp.TAFSIR_BOOKS if book.slug == "mujahid")
SAHIH = next(item for item in qp.TRANSLATIONS if item.slug == "sahih-international")
MUKHTASAR = next(item for item in qp.TRANSLATIONS if item.slug == "mukhtasar")


def _write(path, data, gz=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    path.write_bytes(gzip.compress(raw) if gz else raw)
    return path


# --- HTML to text -----------------------------------------------------------------------------------------

def test_html_text_keeps_the_words_and_moves_the_footnotes_out():
    html = ('قال: <span class="book-ayah text-primary">﴿كلمة أولى﴾</span> <span class="surah-ref">[س: ١]</span>'
            '<a class="foot-note text-primary" href="#f-1">(١)</a> شرح&nbsp;قصير<br />\r\n'
            "<strong>سطر\tثان</strong>   ينتهي<table class='poem'><tr><td>شطر أول</td><td>شطر ثان</td></tr></table>"
            "<div class=\"foot-notes\"><span class='foot-note' id='f-1'>١ - حاشية المحقق.</span><br></div>بعد")
    parsed = qp.html_text(html)
    assert parsed.text == "قال: ﴿كلمة أولى﴾ [س: ١](١) شرح قصير\nسطر ثان ينتهي\nشطر أول شطر ثان\nبعد"
    assert parsed.footnotes == "١ - حاشية المحقق." and parsed.quran_quotes == 1


def test_html_text_adds_nothing_but_spaces_and_line_breaks():
    html = '<p class="text-center">أ<b>ب</b></p><h3>ج &amp; د</h3><hr>هـ<div>و<div class="foot-notes">ز</div></div>'
    parsed = qp.html_text(html)
    visible = "".join(parsed.text.split()) + "".join(parsed.footnotes.split())
    assert sorted(visible) == sorted("أبج&دهـوز") and parsed.footnotes == "ز"


def test_load_reads_gzip_by_its_bytes_not_its_name(tmp_path):
    plain = _write(tmp_path / "a.json", {"x": "ي"})
    zipped = _write(tmp_path / "b.json", {"x": "ي"}, gz=True)  # gzip without a .gz name
    assert qp.load(plain) == qp.load(zipped) == {"x": "ي"}


# --- mushafs --------------------------------------------------------------------------------------------

def _mushaf(number, ayat, mushaf_id=2):
    return {"license": {"version": "2026-09-30"}, "schema": f"/v1/mushafs/{mushaf_id}",
            "data": {"id": mushaf_id, "name": "م", "description": "d", "surahs": [
                {"id": surah, "ayahs": [{"surah": str(surah), "number": ayah, "text": text, "page_number": 1,
                                         "number_in_hafs": [ayah]} for (s, ayah), text in ayat.items() if s == surah]}
                for surah in sorted({s for s, _ in ayat})]}}


def test_parse_mushaf_keeps_text_verbatim_and_counts_per_surah(tmp_path):
    text = BOM + "كلمة" + FATHA
    path = _write(tmp_path / "m.json.gz", _mushaf(2, {(1, 1): text, (1, 2): "ب", (2, 1): "ج"}), gz=True)
    mushaf = qp.parse_mushaf(path, 2)
    assert mushaf.texts[(1, 1)] == text and mushaf.per_surah == {1: 2, 2: 1} and mushaf.version == "2026-09-30"


@pytest.mark.parametrize("change, message", [
    (lambda d: d["data"].update(id=1), "expected 2"),
    (lambda d: d["data"]["surahs"][0]["ayahs"].append(dict(d["data"]["surahs"][0]["ayahs"][0])), "appears twice"),
    (lambda d: d["data"]["surahs"][0]["ayahs"][0].update(surah="2"), "filed under surah 1"),
    (lambda d: d["data"]["surahs"][0]["ayahs"][0].update(number_in_hafs=[5]), "numbered"),
])
def test_parse_mushaf_refuses_a_malformed_file(tmp_path, change, message):
    data = _mushaf(2, {(1, 1): "أ", (1, 2): "ب"})
    change(data)
    with pytest.raises(qp.QuranpediaError, match=message):
        qp.parse_mushaf(_write(tmp_path / "m.json", data), 2)


# --- translations ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("html, ayah, text, label, notes, mismatch", [
    ("(3) Placeholder words.[7]<br />\n____________________<br /><span class=\"text-danger\">\n[7]-</span> A note.",
     3, "Placeholder words.[7]", "(3)", "[7]- A note.", False),
    (f"{NBSP}3.{NBSP}Placeholder{NBSP}words.", 3, "Placeholder words.", "3.", "", False),
    ("<span class=\"text-danger\">12-</span>13. Shared words.", 13, "Shared words.", "12-13.", "", False),
    ("4. Words of another ayah.", 3, "4. Words of another ayah.", None, "", True),
    ("Plain words, 2 of them.", 2, "Plain words, 2 of them.", None, "", False),
])
def test_split_translation(html, ayah, text, label, notes, mismatch):
    assert qp.split_translation(html, ayah) == {"text": text, "footnotes": notes, "number_label": label,
                                                "label_mismatch": mismatch}


def _translation_file(tmp_path, book_id=1947, rows=None):
    rows = rows or [(1, 1, "(1) First placeholder."), (1, 2, "(2) Second placeholder."),
                    (2, 1, "(1) Third placeholder.")]
    return _write(tmp_path / "t.json", {"id": book_id, "name": "n", "language": "English", "ayahs": [
        {"surah_number": s, "ayah_number": a, "page_number": 1, "translated_text": t} for s, a, t in rows]})


def test_translation_records_cover_every_ayah(tmp_path):
    _, entries = qp.parse_translation(_translation_file(tmp_path), SAHIH)
    records, summary = qp.translation_records(entries, {(1, 1), (1, 2), (2, 1), (2, 2)}, SAHIH, "listed")
    assert [record["quran_ref"] for record in records] == ["quran:1:1", "quran:1:2", "quran:2:1"]
    assert records[0]["text"] == "First placeholder." and records[0]["package_rule"] == "listed"
    assert summary["ayat"] == 3 and summary["missing_ayat"] == 1 and summary["labels_removed"] == 3


def test_translation_parsing_refuses_wrong_books_and_unknown_ayat(tmp_path):
    with pytest.raises(qp.QuranpediaError, match="expected 1947"):
        qp.parse_translation(_translation_file(tmp_path, book_id=1948), SAHIH)
    _, entries = qp.parse_translation(_translation_file(tmp_path), SAHIH)
    with pytest.raises(qp.QuranpediaError, match="do not exist"):
        qp.translation_records(entries, {(1, 1)}, SAHIH, "listed")


# --- tafsir books ---------------------------------------------------------------------------------------

def _tafsir_file(tmp_path, rows, book_id=269):
    return _write(tmp_path / "b.json.gz", {"license": {"version": "2026-08-10"}, "book": {
        "id": book_id, "name": "كتاب", "author": {"ar_name": "مؤلف"}}, "ayahs": [
        {"surah": s, "ayah": a, "content": [{"text": t, "part": "1", "page": p, "ayahs": n} for t, p, n in items]}
        for s, a, items in rows]}, gz=True)


PER_SURAH = {1: 3, 2: 4}  # global numbers: 1:1-3 are 1-3, 2:1-4 are 4-7


def test_parse_tafsir_reads_global_and_in_surah_numbering_and_keeps_a_range_once(tmp_path):
    rows = [(1, 1, [("شرح <b>الأولى</b>", 10, "1")]),
            (2, 1, [("شرح مشترك", 11, "4,5")]), (2, 2, [("شرح مشترك", 11, "4,5"), ("شرح ثان", 12, "2")]),
            (2, 3, [("<br>", 12, "6")])]
    _, passages = qp.parse_tafsir(_tafsir_file(tmp_path, rows), MUJAHID, PER_SURAH)
    assert [(p["surah"], p["first"], p["last"], p["numbering"]) for p in passages] == [
        (1, 1, 1, "global"), (2, 1, 2, "global"), (2, 2, 2, "in_surah"), (2, 3, 3, "global")]
    assert passages[0]["text"] == "شرح الأولى" and passages[3]["flags"] == ["empty"]
    records, summary = qp.tafsir_records(passages, MUJAHID, "in_rule")
    assert [r["record_id"] for r in records] == ["mujahid:1:1/1", "mujahid:2:1-2/1", "mujahid:2:2/1", "mujahid:2:3/1"]
    assert records[1]["quran_refs"] == ["quran:2:1", "quran:2:2"] and records[1]["package_rule"] == "in_rule"
    assert summary["usable_records"] == 3 and summary["ayat_covered"] == 3 and summary["flags"] == {"empty": 1}
    assert summary["numbering_in_surah"] == 1 and summary["multi_ayah_records"] == 1


def test_a_passage_printed_before_the_first_ayah_but_filed_later_is_out_of_place(tmp_path):
    rows = [(1, 1, [("شرح", 20, "1")]), (2, 4, [("مقدمة الكتاب", 3, "7"), ("شرح أخير", 90, "7")])]
    _, passages = qp.parse_tafsir(_tafsir_file(tmp_path, rows), MUJAHID, PER_SURAH)
    records, summary = qp.tafsir_records(passages, MUJAHID, "in_rule")
    assert [r["flags"] for r in records] == [[], ["out_of_place"], []]
    assert not qp.usable_record(records[1]) and summary["flags"] == {"out_of_place": 1}


@pytest.mark.parametrize("rows, book_id, message", [
    ([(1, 1, [("x", 1, "1")])], 4, "expected 269"),
    ([(3, 1, [("x", 1, "1")])], 269, "does not exist"),
    ([(1, 3, [("x", 1, "3,4")])], 269, "spans two surahs"),
])
def test_parse_tafsir_refuses_a_malformed_book(tmp_path, rows, book_id, message):
    with pytest.raises(qp.QuranpediaError, match=message):
        qp.parse_tafsir(_tafsir_file(tmp_path, rows, book_id), MUJAHID, PER_SURAH)


def test_parse_books_index(tmp_path):
    path = _write(tmp_path / "books.json.gz", {"data": [
        {"id": 269, "name": "كتاب", "type": "tafsir", "language": {"code": "ar"}, "category": {"name": "تفسير"},
         "author": {"ar_name": "مؤلف", "full_name": "مؤلف كامل"}, "mohaqeq": "محقق", "translator": None,
         "edition": "الأولى", "nasher": "دار", "about": "<div>نبذة</div>"}]}, gz=True)
    book = qp.parse_books_index(path)[269]
    assert book["author"] == "مؤلف" and book["publisher"] == "دار" and "about" not in book


# --- the Quran text comparison --------------------------------------------------------------------------

def test_fold_removes_marks_and_folds_glyph_variants():
    assert qc.fold(WASLA + "ل" + SUKUN + "ب" + FATHA + "ي" + TATWEEL + "ت" + PAUSE) == "البيت"
    assert qc.fold("ف" + KASRA + "ى") == qc.fold("ف" + KASRA + "ي") == "في"
    assert qc.fold("أمل", 1) == "أمل" and qc.fold("أمل", 2) == "امل"


def test_compare_ayah_statuses():
    basmala = [qc.fold(word, 2) for word in "كلمة البدء الأولى هنا".split()]
    tanzil = f"قَالَ {WASLA}لْوَلَد{DAMMA} {PAUSE} ف{KASRA}ى {WASLA}لْبَيْت{KASRA}"
    kfc = f"قَالَ {WASLA}ل{KFC_SUKUN}وَلَد{DAMMA}{PAUSE} ف{KASRA}ي {WASLA}ل{KFC_SUKUN}بَي{KFC_SUKUN}ت{KASRA}"
    assert qc.compare_ayah(tanzil, tanzil).status == "identical"
    assert qc.compare_ayah(tanzil, kfc).status == "identical_after_normalization"
    hamza = qc.compare_ayah("م" + TATWEEL + HAMZA_ABOVE + "ال", "مأ" + MADDAH + "ل")
    assert hamza.status == "identical_except_hamza" and hamza.diffs[0]["kind"] == "hamza"
    prefixed = qc.compare_ayah("كلمة البدء الأولى هنا " + tanzil, kfc, basmala)
    assert prefixed.status == "basmala_prefixed" and prefixed.public()["diffs"] == [
        {"ours": [1, 4], "theirs": [], "kind": "basmala"}]
    divided = qc.compare_ayah("قال كي لا يرى", "قال كيلا يرى")
    assert divided.status == "differs" and divided.public()["diffs"] == [
        {"ours": [2, 3], "theirs": [2, 2], "kind": "word_division"}]
    changed = qc.compare_ayah("قال الولد", "قال البنت")
    assert changed.diffs[0]["kind"] == "words" and changed.diffs[0]["ours_words"] == ["الولد"]


def test_compare_reports_counts_per_surah_and_missing_ayat():
    ours = {(1, 1): "كلمة البدء الأولى هنا", (2, 1): "كلمة البدء الأولى هنا قال", (2, 2): "ب"}
    theirs = {(1, 1): "كلمة البدء الأولى هنا", (2, 1): "قال"}
    results, summary = qc.compare(ours, theirs)
    assert results[(2, 1)].status == "basmala_prefixed" and results[(1, 1)].status == "identical"
    assert not summary["per_surah_counts_match"] and summary["per_surah_count_differences"] == {"2": [2, 1]}
    assert summary["missing_in_reference"] == ["quran:2:2"]


def test_the_comparison_report_holds_references_not_words(tmp_path):
    ours = {(1, 1): "كلمة البدء الأولى هنا", (2, 1): "قال كي لا يرى"}
    mushaf = lambda texts: qp.Mushaf(2, "mushaf", "d", "v", texts, {})
    comparison = build.compare_with_kfc(ours, ours, {qp.MUSHAF_UTHMANI: mushaf({(1, 1): ours[(1, 1)],
                                                                               (2, 1): "قال كيلا يرى"}),
                                                     qp.MUSHAF_PRINT: mushaf(dict(ours))})
    build.write_quran_comparison(tmp_path, comparison)
    data = json.loads((tmp_path / "quran_text_comparison.json").read_text(encoding="utf-8"))
    assert data["comparisons"]["uthmani"]["differs"] == {"quran:2:1": [{"ours": [2, 3], "theirs": [2, 2],
                                                                        "kind": "word_division"}]}
    published = (tmp_path / "quran_text_comparison.json").read_text(encoding="utf-8") + \
        (tmp_path / "quran_text_comparison.md").read_text(encoding="utf-8")
    assert "كيلا" not in published and "يرى" not in published and "2:1" in published
    assert "كيلا" in (tmp_path / "quran_text_comparison_details.jsonl").read_text(encoding="utf-8")


# --- the canonical build ---------------------------------------------------------------------------------
def test_build_quranpedia_writes_canonical_translations_and_tafsir(tmp_path):
    raw, canonical = tmp_path / "raw", tmp_path / "canonical"
    sources = [{"source_id": "tanzil-quran-uthmani", "format": "txt"},
               {"source_id": SAHIH.source_id, "format": "json", "package_rule": "listed"},
               {"source_id": MUJAHID.source_id, "format": "json.gz", "package_rule": "in_rule"},
               {"source_id": qp.BOOKS_INDEX, "format": "json.gz", "package_rule": "not_applicable"}]
    (raw / "tanzil-quran-uthmani").mkdir(parents=True)
    (raw / "tanzil-quran-uthmani/tanzil-quran-uthmani.txt").write_text(
        "1|1|a\n1|2|b\n1|3|c\n2|1|d\n2|2|e\n2|3|f\n2|4|g\n", encoding="utf-8")
    (raw / SAHIH.source_id).mkdir()
    _translation_file(raw / SAHIH.source_id).rename(raw / SAHIH.source_id / f"{SAHIH.source_id}.json")
    _tafsir_file(raw / MUJAHID.source_id, [(2, 1, [("شرح", 5, "4,5")])]).rename(
        raw / MUJAHID.source_id / f"{MUJAHID.source_id}.json.gz")
    _write(raw / qp.BOOKS_INDEX / f"{qp.BOOKS_INDEX}.json.gz", {"data": [{"id": 269, "name": "كتاب"}]}, gz=True)
    files, info = build.build_quranpedia(Registry(None, "", sources), raw, canonical)
    assert set(files) == {f"translations/{SAHIH.source_id}.jsonl", "tafsir/quranpedia-mujahid.jsonl"}
    assert info["translations"][SAHIH.source_id]["ayat"] == 3
    tafsir = info["tafsir"][MUJAHID.source_id]
    assert tafsir["layer0"] and tafsir["ayat_covered"] == 2 and tafsir["book"]["name"] == "كتاب"
    [record] = [json.loads(line) for line in (canonical / "tafsir/quranpedia-mujahid.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert record["record_id"] == "mujahid:2:1-2/1" and record["text"] == "شرح"


# --- documents ------------------------------------------------------------------------------------------

def _registry():
    source = {"title": "Work title", "edition": "e", "publisher": "p", "license": "test", "sha256": "0" * 64}
    return Registry(None, "", [dict(source, source_id=sid) for sid in
                               (SAHIH.source_id, MUKHTASAR.source_id, MUJAHID.source_id)])


def _translation_record(surah, ayah, text, mismatch=False):
    return {"surah": surah, "ayah": ayah, "text": text, "label_mismatch": mismatch}


def test_translation_documents_mirror_the_quran_segments():
    records = {(1, 1): _translation_record(1, 1, "First placeholder."),
               (1, 2): _translation_record(1, 2, "Second placeholder."),
               (1, 3): _translation_record(1, 3, "Words of another ayah.", mismatch=True)}
    built = ingest.translation_documents([Segment(1, 1, 3)], records, SAHIH, {1: "Al-Faatiha"}, _registry(),
                                         {(1, 2): {"id": "adam", "name": "آدم", "latin": "Adam"}})
    [data] = built.documents
    assert data["id"] == "quran-en-sahih-international-001-001-003" and data["language"] == "en"
    assert data["contentType"] == "quran_translation" and data["tier"] == 1 and data["prophetId"] == "adam"
    assert data["title"] == "The Quran 1:1–3 — English translation of the meanings (Saheeh International)"
    assert data["contextHeader"].startswith("The story of the Prophet Adam — English translation of the meanings")
    assert data["parentChunk"] == "quran-001-001-003#1" and data["sourceIds"] == [SAHIH.source_id]
    assert [unit["reference"] for unit in data["units"]] == ["quran:1:1", "quran:1:2"]
    assert data["source"]["translator"] == "Saheeh International"
    assert built.skipped == {"sahih-international_labelled_for_another_ayah": 1}
    document, issues = parse_document(data, "d.json")
    assert document is not None, [str(issue) for issue in issues]
    assert {chunk.content_type for chunk in chunk_document(document)} == {"quran_translation"}


def test_the_mukhtasar_english_is_a_tafsir_translation_citing_every_ayah_of_a_shared_text():
    records = {(1, ayah): _translation_record(1, ayah, "One explanation.") for ayah in (1, 2)}
    [data] = ingest.translation_documents([Segment(1, 1, 2)], records, MUKHTASAR, {1: "Al-Faatiha"}, _registry(),
                                          {}).documents
    assert data["id"] == "tafsir-en-mukhtasar-001-001-002" and data["contentType"] == "tafsir_translation"
    assert data["units"][0]["sourceRefs"] == ["quran:1:1", "quran:1:2"] and "not the words of the Quran" in \
        data["contextHeader"]
    document, issues = parse_document(data, "d.json")
    assert document is not None, [str(issue) for issue in issues]


def test_quranpedia_tafsir_documents_name_the_book_and_keep_passages_apart():
    passages = [{"surah": 1, "first": 1, "last": 2, "text": "فقرة أولى\nفقرة ثانية", "footnotes": "", "quran_quotes": 0,
                 "part": "1", "page": 1, "numbering": "global", "flags": []},
                {"surah": 1, "first": 2, "last": 2, "text": "شرح آخر", "footnotes": "", "quran_quotes": 0,
                 "part": "1", "page": 2, "numbering": "global", "flags": []},
                {"surah": 1, "first": 3, "last": 3, "text": "مقدمة", "footnotes": "", "quran_quotes": 0,
                 "part": "1", "page": 0, "numbering": "global", "flags": ["out_of_place"]}]
    records, _ = qp.tafsir_records(passages, MUJAHID, "in_rule")
    built = ingest.quranpedia_tafsir_documents([Segment(1, 1, 3)], records, MUJAHID, {1: "الفاتحة"}, _registry(), {})
    [data] = built.documents
    assert data["id"] == "tafsir-mujahid-001-001-003" and data["title"] == "تفسير مجاهد 1:1–2"
    assert data["contextHeader"] == "تفسير مجاهد — مجاهد بن جبر (ت 104 هـ) — سورة الفاتحة — الآيات 1–2"
    assert data["tier"] == 1 and data["parentChunk"] == "quran-001-001-003#1"
    assert [(u["id"], u["section"], u["sourceRefs"]) for u in data["units"]] == [
        ("r1p1", "mujahid:1:1-2/1", ["quran:1:1-2"]), ("r1p2", "mujahid:1:1-2/1", ["quran:1:1-2"]),
        ("r2p1", "mujahid:1:2/1", ["quran:1:2"])]
    assert built.skipped == {"mujahid_record_not_usable": 1}
    document, issues = parse_document(data, "d.json")
    assert document is not None, [str(issue) for issue in issues]
    assert [chunk.unit_ids for chunk in chunk_document(document)] == [("r1p1", "r1p2"), ("r2p1",)]


def test_quran_translation_units_need_a_reference():
    data = {"schemaVersion": 2, "id": "quran-en-x-001-001-001", "kind": "passage", "title": "t", "language": "en",
            "ageBands": ["7-9"], "contentType": "quran_translation", "madhhab": [], "curriculumPolicy": "c",
            "synthetic": False, "source": {"work": "w", "edition": "e", "publisher": "p", "translator": "t",
                                           "license": "l", "checksum": None},
            "grading": None, "review": {"status": "draft", "reviewer": None, "approvedOn": None, "supersedes": None},
            "units": [{"id": "a1", "text": "Placeholder words.", "reference": None, "section": None,
                       "keepWithNext": False}]}
    document, issues = parse_document(data, "d.json")
    assert document is None and any("every verse needs its reference" in issue.message for issue in issues)
