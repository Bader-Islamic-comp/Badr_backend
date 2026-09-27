"""Phase 2 ingestion: segments, verbatim parts, clusters, Nawawi links, candidate checks, documents.

Arabic words here are placeholder tokens, not Quran or hadith text. The salutation formula is used
only because matn detection keys on it.
"""
import pytest

from companion_api.corpusprep import candidates, cluster, ingest
from companion_api.corpusprep.registry import Registry
from companion_api.corpusprep.segments import Segment, segment, verify_cover
from companion_api.rag.chunking import chunk_document
from companion_api.rag.corpus import parse_document

PBUH = "صلى الله عليه وسلم"


def _words(n: int, offset: int = 0) -> str:
    return " ".join(f"كلمة{i}" for i in range(offset, offset + n))


# --- segments --------------------------------------------------------------------------------------------

def test_segments_respect_rukus_ayat_and_word_budget():
    counts = {1: 20}
    words = {(1, a): 10 for a in range(1, 21)}
    words[(1, 15)] = 400  # one ayah over the budget stays whole, alone
    result = segment(counts, [(1, 1), (1, 11)], words, budget=180)
    verify_cover(result, counts)
    assert all(s.last - s.first + 1 <= 8 for s in result)
    assert Segment(1, 15, 15) in result
    assert not any(s.first <= 10 < s.last for s in result)  # never across a ruku boundary


def test_verify_cover_reports_gaps():
    with pytest.raises(ValueError, match="not in any segment"):
        verify_cover([Segment(1, 1, 2)], {1: 3})


# --- verbatim parts -------------------------------------------------------------------------------------

def test_verbatim_parts_are_ordered_excerpts():
    text = ". ".join(_words(30, 100 * n) for n in range(4)) + "."
    parts = ingest.verbatim_parts(text)
    assert len(parts) >= 2
    cursor = 0
    for part in parts:
        found = text.find(part, cursor)
        assert found >= cursor
        cursor = found + len(part)
    assert ingest.verbatim_parts(_words(50)) == []  # short narrations are not split


# --- clusters and Nawawi links --------------------------------------------------------------------------

def _record(collection, number, text, eligible=True):
    return cluster.Record(collection, number, eligible, frozenset(cluster.grams(cluster.matn_tokens(text))))


def test_same_matn_different_chain_clusters_with_bukhari_primary():
    matn = _words(25, 500)
    records = [_record("muslim", "9", f"{_words(8, 0)} {PBUH} {matn}"),
               _record("bukhari", "30", f"{_words(8, 50)} {PBUH} {matn}"),
               _record("bukhari", "31", f"{_words(8, 90)} {PBUH} {_words(25, 900)}")]
    result = cluster.cluster(records)
    assert result["muslim:9"]["cluster_id"] == result["bukhari:30"]["cluster_id"] == "hc-bukhari-30"
    assert result["bukhari:31"]["members"] == ["bukhari:31"]


def test_ineligible_member_is_not_primary():
    matn = _words(25, 500)
    records = [_record("bukhari", "1", f"{PBUH} {matn}", eligible=False), _record("muslim", "2", f"{PBUH} {matn}")]
    assert cluster.cluster(records)["bukhari:1"]["primary"] == "muslim:2"


def test_nawawi_link_needs_the_takhrij_to_name_the_collection():
    matn = _words(25, 500)
    records = [_record("bukhari", "7", f"{PBUH} {matn}")]
    named = f"{PBUH} {matn} رواه البخاري"
    unnamed = f"{PBUH} {matn} رواه الترمذي"
    links = cluster.link_nawawi([("1", named), ("2", unnamed)], records)
    assert links["1"]["status"] == "linked" and links["1"]["ref"] == "bukhari:7"
    assert links["2"]["status"] == "not_linked" and links["2"]["ref"] is None


# --- candidate checks -----------------------------------------------------------------------------------

def _aliases(extra_title=None):
    prophets = [{"id": f"p{n}", "names_ar": [{"alias": f"اسم{n}", "evidence": "auto"}], "titles_ar": [],
                 "latin": ["X"], "arabizi": []} for n in range(25)]
    if extra_title:
        prophets[0]["titles_ar"] = [extra_title]
    return {"prophets": prophets}


def test_alias_evidence_found_or_needs_check():
    simple = {(1, 1): "اسم0 كلمة", (1, 2): "شيء اخر"}
    data, summary = candidates.check_aliases(_aliases({"alias": "لقب", "evidence": {"ref": "quran:1:2",
                                                                                      "phrase": "غير موجود"}}), simple)
    assert data["prophets"][0]["names_ar"][0]["status"] == "evidence_found"
    assert data["prophets"][0]["names_ar"][0]["found_in"]["first"] == ["quran:1:1"]
    assert data["prophets"][0]["titles_ar"][0]["status"] == "needs_check"
    assert data["prophets"][1]["names_ar"][0]["status"] == "needs_check"
    assert data["prophets"][0]["spellings_status"] == "needs_check"
    with pytest.raises(ValueError, match="expected the 25"):
        candidates.check_aliases({"prophets": _aliases()["prophets"][:3]}, simple)


def test_source_map_checks_existence_and_name():
    simple = {(1, 1): "اسم0", (1, 2): "كلمة", (1, 3): "كلمة"}
    data = {"prophet_id": "p0", "ranges": [{"ref": "quran:1:1-2", "confidence": "high"},
                                           {"ref": "quran:1:2-3", "confidence": "high"},
                                           {"ref": "quran:1:3-9", "confidence": "high"},
                                           {"ref": "quran:1:1", "confidence": "medium"}]}
    data, summary = candidates.check_source_map(data, simple, _aliases())
    assert [r["verification"] for r in data["ranges"]] == ["ok", "needs_check", "needs_check", "needs_check"]
    assert data["ranges"][2]["checks"]["exists"] is False and summary["missing_ayat"] == 1


def test_selection_lookup_allows_attached_prefix_and_flags_problems():
    records = {"bukhari:5": {"arabic_text": "و" + "كلمة1 كلمة2 كلمة3", "eligible": True},
               "bukhari:6": {"arabic_text": "كلمة8 كلمة9", "eligible": False}}
    clusters = {"bukhari:5": {"cluster_id": "hc-bukhari-5", "primary": "bukhari:5", "members": ["bukhari:5"]},
                "bukhari:6": {"cluster_id": "hc-bukhari-6", "primary": "bukhari:6", "members": ["bukhari:6"]}}
    entries = [{"collection": "bukhari", "lookup_phrase": "كلمة1 كلمة2"},
               {"collection": "bukhari", "lookup_phrase": "كلمة8 كلمة9"},
               {"collection": "bukhari", "lookup_phrase": "كلمة2 كلمة3"}]
    entries += [{"collection": "nawawi40", "number": str(n)} for n in range(37)]
    data, summary = candidates.check_selection({"hadith": entries}, records, clusters,
                                               {"0": {"status": "linked", "ref": "bukhari:5"}})
    first, second, third = data["hadith"][:3]
    assert first["number"] == "5" and not first["needs_check"]
    assert second["check_reasons"] == ["lookup_phrase_not_found_in_eligible_records"]
    assert third["check_reasons"] == ["same_cluster_as_entry_1"]
    assert data["hadith"][3]["check_reasons"] == ["same_cluster_as_entry_1"]
    assert data["hadith"][4]["check_reasons"] == ["nawawi_link_not_linked"]


# --- documents --------------------------------------------------------------------------------------------

def _registry():
    source = {"edition": "e", "publisher": "p", "license": "test", "sha256": "0" * 64}
    return Registry(None, "", [dict(source, source_id=sid) for sid in
                               ("fawazahmed0-ara-bukhari", "mhashim6-bukhari", "tanzil-quran-uthmani",
                                "alquran-cloud-muyassar")])


def test_hadith_documents_validate_and_keep_text_verbatim():
    text = ". ".join(_words(30, 100 * n) for n in range(4)) + "."
    rows = {"bukhari:5": {"arabic_text": text, "grading": "sahih", "grader": "collection rule: Sahih al-Bukhari",
                          "source_ids": ["fawazahmed0-ara-bukhari", "mhashim6-bukhari"],
                          "crosscheck_status": "match"},
            "bukhari:6": {"arabic_text": "x", "grading": "sahih", "grader": "g",
                          "source_ids": ["fawazahmed0-ara-bukhari"], "crosscheck_status": "match"}}
    clusters = {"bukhari:5": {"cluster_id": "hc-bukhari-5", "primary": "bukhari:5", "members": ["bukhari:5", "bukhari:6"]},
                "bukhari:6": {"cluster_id": "hc-bukhari-5", "primary": "bukhari:5", "members": ["bukhari:5", "bukhari:6"]}}
    built = ingest.hadith_documents(rows, clusters, {"3": {"status": "linked", "ref": "bukhari:6"}}, _registry())
    assert built.skipped == {"cluster_member_not_primary": 1}
    document, issues = parse_document(built.documents[0], "d.json")
    assert document is not None, [str(issue) for issue in issues]
    assert document.units[0].text == text and document.cluster_refs == ("bukhari:6", "nawawi40:3")
    assert "الأربعون النووية 3" in document.context_header
    parent, *children = chunk_document(document)
    assert parent.text == text and len(children) >= 2 and all(child.parent_id == parent.id for child in children)


def test_quran_and_tafsir_documents():
    ayat = {(1, a): {"text_uthmani": f"اية{a}"} for a in (1, 2)}
    tafsir = {(1, 1): "شرح", (1, 2): "شرح"}  # one explanation for two ayat is kept once, citing both
    built = ingest.quran_documents([Segment(1, 1, 2)], ayat, tafsir, {1: "الفاتحة"}, _registry(),
                                   {(1, 2): {"id": "adam", "name": "آدم"}})
    quran_doc, tafsir_doc = built.documents
    assert quran_doc["prophetId"] == "adam" and quran_doc["contextHeader"].startswith("قصة آدم")
    assert tafsir_doc["parentChunk"] == "quran-001-001-002#1"
    assert tafsir_doc["units"][0]["sourceRefs"] == ["quran:1:1", "quran:1:2"]
    for data in built.documents:
        document, issues = parse_document(data, "d.json")
        assert document is not None, [str(issue) for issue in issues]
