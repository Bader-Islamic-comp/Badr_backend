"""Source registry, fetch verification and canonical builders (corpus tasks Phase 1). Offline fixtures only.

The Arabic strings below are placeholder test tokens, not Quran or hadith text.
"""
import copy
import json
from pathlib import Path

import pytest
import yaml

from companion_api.corpusprep import fetch, hadith, quran, registry

ROOT = Path(__file__).resolve().parents[1]

SOURCE = {
    "source_id": "demo-source", "format": "txt", "title": "Demo", "edition": "1", "publisher": "Test",
    "url": "https://example.invalid/demo.txt", "license": "test", "license_url": None, "terms_summary": "test only",
    "retrieved_at": None, "sha256": None, "numbering_system": "n", "status": "pending_legal", "notes": None,
}


def _writer(content: bytes):
    def download(url, target, timeout):
        Path(target).write_bytes(content)
    return download


# --- registry ---------------------------------------------------------------------------------------------

def test_project_registry_is_valid_and_nothing_is_cleared():
    loaded = registry.load(ROOT / "corpus/sources/registry.yaml")
    assert {source["status"] for source in loaded.sources} <= {"candidate", "pending_legal"}
    for source in loaded.sources:
        if source["status"] == "candidate":
            assert source["notes"], source["source_id"]


def test_registry_reports_every_problem():
    bad = {"schema_version": 1, "sources": [dict(SOURCE, status="approved", format="pdf", sha256="xyz"),
                                            {"source_id": "demo-source"}]}
    problems = registry.validate(bad)
    text = "\n".join(problems)
    assert "status: must be one of" in text and "format: must be one of" in text
    assert "sha256: must be 64" in text and "used twice" in text and "is required" in text


def test_candidate_needs_a_reason():
    problems = registry.validate({"schema_version": 1, "sources": [dict(SOURCE, status="candidate")]})
    assert any("candidate source must say why" in problem for problem in problems)


def test_save_keeps_header(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text("# header comment\nschema_version: 1\nsources:\n"
                    + yaml.safe_dump([SOURCE], sort_keys=False), encoding="utf-8")
    loaded = registry.load(path)
    loaded.sources[0]["notes"] = "changed"
    registry.save(loaded)
    assert path.read_text(encoding="utf-8").startswith("# header comment\n")
    assert registry.load(path).sources[0]["notes"] == "changed"


# --- fetch ------------------------------------------------------------------------------------------------

def test_first_download_requires_record(tmp_path):
    with pytest.raises(fetch.SourceChanged, match="--record"):
        fetch.ensure(dict(SOURCE), tmp_path, download=_writer(b"abc"))
    assert not fetch.raw_path(tmp_path, SOURCE).exists()


def test_record_then_cached_then_tamper_detected(tmp_path):
    source = dict(SOURCE)
    path, action = fetch.ensure(source, tmp_path, record=True, download=_writer(b"abc"))
    assert action == "recorded" and source["sha256"] == fetch.digest(path) and source["retrieved_at"]
    assert fetch.ensure(source, tmp_path, download=_writer(b"never called"))[1] == "cached"
    path.write_bytes(b"abd")
    with pytest.raises(fetch.SourceChanged, match="modified after download"):
        fetch.ensure(source, tmp_path)


def test_changed_upstream_fails_and_overwrites_nothing(tmp_path):
    source = dict(SOURCE)
    path, _ = fetch.ensure(source, tmp_path, record=True, download=_writer(b"abc"))
    recorded = copy.deepcopy(source)
    with pytest.raises(fetch.SourceChanged, match="SOURCE CHANGED"):
        fetch.ensure(source, tmp_path, refresh=True, download=_writer(b"new edition"))
    assert path.read_bytes() == b"abc" and source == recorded
    assert [item.name for item in path.parent.iterdir()] == [path.name]  # no temporary file left behind


# --- quran ------------------------------------------------------------------------------------------------

def _tanzil(tmp_path, name, lines):
    path = tmp_path / name
    path.write_bytes(("﻿" + "\n".join(lines) + "\n#\n#  notice line\n").encode("utf-8"))
    return path


def test_parse_tanzil_keeps_text_verbatim_and_notice(tmp_path):
    text = "بِسْمِ  ٱللَّهِ "  # marks and spacing kept
    ayat, notice = quran.parse_tanzil(_tanzil(tmp_path, "a.txt", [f"1|1|{text}", "1|2|x"]))
    assert ayat[(1, 1)] == text and notice == ["#", "#  notice line"]


def test_parse_tanzil_rejects_duplicates(tmp_path):
    with pytest.raises(quran.QuranError, match="twice"):
        quran.parse_tanzil(_tanzil(tmp_path, "a.txt", ["1|1|x", "1|1|y"]))


def test_verify_names_count_mismatches():
    ayat = {(1, 1): "a", (1, 2): "b", (2, 1): "c"}
    with pytest.raises(quran.QuranError) as error:
        quran.verify(ayat, dict(ayat), {"reference": {1: 2, 2: 2}})
    message = str(error.value)
    assert "expected 114" in message and "expected 6236" in message and "reference for surahs [2]" in message


def test_verify_rejects_simple_text_with_other_keys():
    with pytest.raises(quran.QuranError, match="differ in ayah keys"):
        quran.verify({(1, 1): "a"}, {(1, 2): "a"}, {})


def test_tafsir_refuses_entries_for_unknown_ayat():
    with pytest.raises(quran.QuranError, match="do not exist"):
        quran.tafsir_records({(1, 1): "t", (9, 999): "t"}, [(1, 1)], "demo")
    records, info = quran.tafsir_records({(1, 1): "t"}, [(1, 1), (1, 2)], "demo")
    assert records[0]["quran_ref"] == "quran:1:1" and info == {"records": 1, "missing_ayat": 1, "empty": 0}


# --- hadith -----------------------------------------------------------------------------------------------

WORDS = "كلمة"  # a placeholder token


def _text(n: int, offset: int = 0) -> str:
    return " ".join(f"{WORDS}{i}" for i in range(offset, offset + n))


def test_crosscheck_by_text_maps_numbering_and_containment():
    primary = [hadith.Entry("1", _text(20)), hadith.Entry("2", _text(20, 100)), hadith.Entry("3", _text(20, 500))]
    secondary = [hadith.Entry("7", _text(20, 100) + " " + _text(40, 300)),  # holds primary 2 inside a longer entry
                 hadith.Entry("9", _text(20))]
    matches = hadith.crosscheck_by_text(primary, secondary)
    assert matches["1"][0] == "9" and hadith.status_for(matches["1"]) == "match"
    assert matches["2"][0] == "7" and hadith.status_for(matches["2"]) == "contained_in_secondary"
    assert hadith.status_for(matches["3"]) == "not_matched"


def test_status_thresholds():
    assert hadith.status_for(("1", 0.95, 0.95)) == "match"
    assert hadith.status_for(("1", 0.5, 0.95)) == "contained_in_secondary"
    assert hadith.status_for(("1", 0.7, 0.7)) == "text_differs"
    assert hadith.status_for(("1", 0.3, 0.65)) == "text_differs"
    assert hadith.status_for(("1", 0.3, 0.3)) == "not_matched"
    assert hadith.status_for(None) == "not_matched"


def test_records_grading_eligibility_and_verbatim_text():
    text = _text(10) + "  ، "  # odd spacing and punctuation must survive
    parsed = hadith.Parsed([hadith.Entry("1", text)])
    sahih = hadith.records("bukhari", parsed, "fawazahmed0-ara-bukhari", "mhashim6-bukhari",
                           {"1": ("5", 0.97, 0.97)}, set())[0]
    assert sahih["arabic_text"] == text and sahih["grading"] == "sahih" and sahih["eligible"]
    assert sahih["source_ids"] == ["fawazahmed0-ara-bukhari", "mhashim6-bukhari"]
    assert sahih["crosscheck"]["number"] == "5" and sahih["review_status"] == "draft"
    other = hadith.records("riyadussalihin", parsed, "ahmedbaset-riyadussalihin", None, None,
                           {"ahmedbaset-riyadussalihin"})[0]
    assert other["grading"] is None and not other["eligible"]
    assert other["crosscheck_status"] == "single_source"
    assert set(other["ineligible_reasons"]) == {"no_grading_in_source", "primary_source_licence_unclear"}
    differs = hadith.records("muslim", parsed, "fawazahmed0-ara-muslim", "mhashim6-muslim",
                             {"1": ("5", 0.7, 0.7)}, set())[0]
    assert not differs["eligible"] and differs["ineligible_reasons"] == ["crosscheck_unresolved"]


def test_parsers_skip_and_report_empty_text(tmp_path):
    fa = tmp_path / "fa.json"
    fa.write_text(json.dumps({"hadiths": [{"hadithnumber": 1, "text": "a"}, {"hadithnumber": 402.2, "text": " "}]}),
                  encoding="utf-8")
    parsed = hadith.parse_fawazahmed0(fa)
    assert [entry.number for entry in parsed.entries] == ["1"] and parsed.empty_numbers == ["402.2"]
    mh = tmp_path / "mh.csv"
    mh.write_text('"1"," a b"\n"2",""\n', encoding="utf-8")
    parsed = hadith.parse_mhashim6(mh)
    assert [entry.text for entry in parsed.entries] == [" a b"] and parsed.empty_numbers == ["2"]


def test_compare_tokens_join_detached_waw_and_ignore_alef():
    waw, alef = "و", "ا"
    word = "حدثن" + alef  # a placeholder word ending in alef
    assert hadith.compare_tokens(f"{waw} {word}") == hadith.compare_tokens(f"{waw}{word}")
    assert hadith.compare_tokens("سح" + alef + "ق") == hadith.compare_tokens("سحق")


def test_crosscheck_by_text_finds_entry_split_over_consecutive_numbers():
    primary = [hadith.Entry("1", _text(40))]
    secondary = [hadith.Entry("10", _text(20, 900)), hadith.Entry("11", _text(21)),
                 hadith.Entry("12", _text(21, 19)), hadith.Entry("13", _text(20, 950))]
    match = hadith.crosscheck_by_text(primary, secondary)["1"]
    assert match[0] == "11-12" and hadith.status_for(match) == "contained_in_secondary"
