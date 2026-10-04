"""The challenge's reference package: the compliance check, its generated page, the glossary's schema, the hadith
grading basis, the Dorar sample and the rights table (test/corpus-tasks, 2026-10-02). Offline only."""
import copy
import csv
import importlib.util
import io
from pathlib import Path
import sys

import pytest
import yaml

from companion_api.corpusprep import hadith, reference_package, registry

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str):
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))  # the scripts import their shared _common module
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(sid, rule="in_rule", status="candidate", acquisition=None):
    source = {"source_id": sid, "title": sid, "status": status, "package_rule": rule, "dataset": "d"}
    if acquisition:
        source["acquisition"] = acquisition
    return source


PACKAGE = {"schema_version": 1, "package": {"version": "20/3/1448", "permission_evidence": "letter.pdf"},
           "rows": [{"field": "tafsir", "sources": [
               {"name": "early", "acquisition": "downloaded", "registry": ["tafsir-001..002"]},
               {"name": "dorar", "acquisition": "blocked"}], "already_present_outside_rule": ["late"]}],
           "rulings": []}
SOURCES = [_source("tafsir-001"), _source("tafsir-002"), _source("late", rule="outside_rule")]
RULING = {"ruling_id": "R-001", "sources": ["late"], "question": "May it be used?", "answer": "admitted",
          "by": "Organizer, role", "date": "2026-10-03", "evidence": "doc/governance/organizers/r-001.pdf"}


def test_the_project_passes_the_check_and_its_page_is_up_to_date():
    sources = registry.load(ROOT / "corpus/sources/registry.yaml").sources
    package = reference_package.load(ROOT / "corpus/sources/reference_package.yaml")
    report = reference_package.check(sources, package, ROOT)
    assert report.problems == []
    assert sum(entry["sources"] for entry in report.by_rule.values()) == len(sources)
    page = (ROOT / "doc/governance/reference-package.md").read_text(encoding="utf-8")
    assert page == reference_package.render(sources, package, report), (
        "run python scripts/check_reference_package.py --write")


def test_ranges_expand_to_zero_padded_ids():
    assert reference_package.expand(["ibn-kathir-ar-001..003", "x"]) == [
        "ibn-kathir-ar-001", "ibn-kathir-ar-002", "ibn-kathir-ar-003", "x"]
    with pytest.raises(reference_package.PackageError):
        reference_package.expand(["a-5..1"])


def test_a_clean_package_passes():
    report = reference_package.check(SOURCES, PACKAGE)
    assert report.problems == [] and report.warnings == []
    assert report.by_rule["in_rule"]["sources"] == 2 and report.by_rule["outside_rule"]["status"] == {"candidate": 1}


def test_a_source_without_a_package_rule_fails():
    sources = copy.deepcopy(SOURCES)
    del sources[2]["package_rule"]
    problems = reference_package.check(sources, PACKAGE).problems
    assert any("late: package_rule: is required" in problem for problem in problems)


def test_a_named_id_missing_from_the_registry_fails():
    package = copy.deepcopy(PACKAGE)
    package["rows"][0]["sources"][0]["registry"] = ["tafsir-001..003"]
    package["open_questions"] = [{"id": "Q1", "sources": ["ghost"]}]
    problems = reference_package.check(SOURCES, package).problems
    assert any(problem.startswith("tafsir-003: named") for problem in problems)
    assert any(problem.startswith("ghost: named") and "open question Q1" in problem for problem in problems)


@pytest.mark.parametrize("rule", ["outside_rule", "borderline", "not_listed"])
def test_clearing_a_source_outside_the_rule_needs_an_admitting_ruling(rule):
    sources = copy.deepcopy(SOURCES)
    sources[2].update(package_rule=rule, status="cleared")
    assert any("no organizers' ruling" in p for p in reference_package.check(sources, PACKAGE).problems)
    package = copy.deepcopy(PACKAGE)
    package["rulings"] = [RULING]
    assert reference_package.check(sources, package).problems == []
    package["rulings"] = [dict(RULING, answer="not_admitted")]
    assert any("no organizers' ruling" in p for p in reference_package.check(sources, package).problems)


def test_an_in_rule_source_may_be_cleared_without_a_ruling():
    sources = copy.deepcopy(SOURCES)
    sources[0]["status"] = "cleared"
    assert reference_package.check(sources, PACKAGE).problems == []


def test_an_incomplete_ruling_fails():
    package = copy.deepcopy(PACKAGE)
    package["rulings"] = [dict(RULING, evidence="", answer="admitted_with_conditions", date="3/10/2026"),
                          dict(RULING)]
    problems = "\n".join(reference_package.check(SOURCES, package).problems)
    assert "evidence: is required" in problems and "conditions: required" in problems
    assert "date: must be YYYY-MM-DD" in problems and "used twice" in problems


def test_acquisition_must_agree_with_the_registry():
    sources = copy.deepcopy(SOURCES)
    sources[0]["acquisition"] = "crawl"
    package = copy.deepcopy(PACKAGE)
    package["rows"][0]["sources"][1]["registry"] = ["late"]
    problems = "\n".join(reference_package.check(sources, package).problems)
    assert "tafsir-001: registry acquisition crawl" in problems and "a blocked source names registry ids" in problems


def test_cited_files_must_exist(tmp_path):
    package = copy.deepcopy(PACKAGE)
    package["standard"] = [{"clause": 1, "implemented": [{"text": "see `src/missing.py`", "files": ["AGENTS.md"]}]}]
    (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
    problems = reference_package.check(SOURCES, package, tmp_path).problems
    assert problems == ["src/missing.py: cited by the standard or levels mapping, but it does not exist"]


def test_the_script_fails_on_a_problem(tmp_path, capsys):
    script = _script("check_reference_package")
    registry_path = tmp_path / "registry.yaml"
    text = (ROOT / "corpus/sources/registry.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    del data["sources"][0]["package_rule"]
    registry_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert script.main(["--registry", str(registry_path)]) == 1
    assert "package_rule: is required" in capsys.readouterr().err
    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert "outside_rule" in out and "check passed" in out


# --- glossary -----------------------------------------------------------------------------------------------

PAGE_7 = {"الإسلام", "التوحيد", "العبادة", "النبوة", "الوحي", "الشريعة", "الحديث", "السنة", "الفتوى", "الدعوة"}


def test_the_glossary_is_valid_and_holds_the_page_7_terms():
    exporter = _script("export_query_aliases")
    glossary = yaml.safe_load((ROOT / "corpus/glossary_cross_lingual.yaml").read_text(encoding="utf-8"))
    assert exporter.check_glossary(glossary) == []
    page_7 = {term["ar"]: term for term in glossary["terms"] if term.get("origin") == "package_page_7"}
    assert set(page_7) == PAGE_7
    assert page_7["التوحيد"]["en"] == "Tawhid / Oneness of God"
    assert all(term["provenance"]["en"] == "package_page_7" for term in page_7.values())
    assert all("jamharah" in term for term in glossary["terms"])  # every term was looked up


def test_the_glossary_check_names_its_problems():
    exporter = _script("export_query_aliases")
    bad = {"schema_version": 2, "terms": [
        {"ar": "x", "latin": ["x"], "colour": "red"},
        {"ar": "y", "latin": [], "origin": "package_page_7", "jamharah": {"id": "1"}},
        {"ar": "x", "latin": ["x"], "provenance": {"latin": "guessed"}}]}
    problems = "\n".join(exporter.check_glossary(bad))
    assert "colour: unknown field" in problems and "latin: must be a non-empty list" in problems
    assert "jamharah: must be" in problems and "en: is required for a page-7 term" in problems
    assert "listed twice" in problems and "provenance: latin" in problems
    with pytest.raises(exporter.GlossaryError):
        exporter.build(glossary_path=_write(bad))


def _write(data) -> Path:
    import tempfile
    path = Path(tempfile.mkdtemp()) / "glossary.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


# --- hadith grading basis -----------------------------------------------------------------------------------

def test_the_two_sahihs_cite_the_package_rule_and_eligibility_is_unchanged():
    parsed = hadith.Parsed([hadith.Entry("1", "نص تجريبي للاختبار فقط")])
    for collection in ("bukhari", "muslim"):
        row = hadith.records(collection, parsed, f"fawazahmed0-ara-{collection}", None, None, set())[0]
        assert row["grading"] == "sahih" and row["eligible"]
        assert "collection rule" in row["grader"] and "الأحاديث الصحيحة من الصحيحين" in row["grader"]
        assert "20/3/1448" in row["grader"]
    other = hadith.records("nawawi40", parsed, "fawazahmed0-ara-nawawi", None, None, set())[0]
    assert other["grading"] is None and other["grader"] is None and not other["eligible"]


def test_the_dorar_sample_is_seeded_stratified_and_numbers_only():
    sampler = _script("sample_hadith_check")
    statuses = ["match"] * 60 + ["contained_in_secondary"] * 20 + ["text_differs"] * 12 + ["not_matched"] * 4
    rows = {collection: [{"collection": collection, "number": str(n), "numbering_system": "sunnah.com",
                          "crosscheck_status": status, "eligible": status in ("match", "contained_in_secondary"),
                          "crosscheck": {"source_id": "second", "number": str(n + 1)}, "arabic_text": "نص"}
                         for n, status in enumerate(statuses, 1)] for collection in ("bukhari", "muslim")}
    first = sampler.sample(rows, 7, 100)
    assert first == sampler.sample(rows, 7, 100) and first != sampler.sample(rows, 8, 100)
    counted = {}
    for row in first:
        counted[(row["collection"], row["crosscheck_status"])] = counted.get((row["collection"],
                                                                             row["crosscheck_status"]), 0) + 1
    assert counted[("bukhari", "not_matched")] == 4 and counted[("bukhari", "match")] == 26  # 20 + 6 unfilled
    assert counted[("muslim", "text_differs")] == 10 and len(first) == 100
    table = list(csv.reader(io.StringIO(sampler.render(first, None))))
    assert table[0] == list(sampler.COLUMNS) and len(table) == 101
    assert "arabic_text" not in table[0] and all("نص" not in cell for line in table for cell in line)


def test_the_committed_dorar_sample_has_100_records_without_text():
    with (ROOT / "corpus/reports/hadith_dorar_check.csv").open(encoding="utf-8", newline="") as handle:
        table = list(csv.DictReader(handle))
    assert len(table) == 100 and {row["collection"] for row in table} == {"bukhari", "muslim"}
    assert all(set(row) == set(_script("sample_hadith_check").COLUMNS) for row in table)


# --- rights table -------------------------------------------------------------------------------------------

def test_the_rights_table_has_a_reading_for_every_dataset_and_is_up_to_date():
    rights = _script("rights_table")
    datasets = {source["dataset"] for source in registry.load(ROOT / "corpus/sources/registry.yaml").sources}
    assert datasets <= set(rights.READING)
    page = (ROOT / "doc/governance/rights-clearance.md").read_text(encoding="utf-8")
    assert "| source | registry status | package rule | licence | clearance |" in page
    assert "## quranpedia-dumps" in page and "## jamharah" in page
