"""The Arabic competition package: its corpus documents (corpusprep/competition.py) and its validator
(corpus/competition-ar/validate.py).

Arabic words in the made-up items are placeholders, not Quran or hadith text; the repository's content.json is
read as it is.
"""
from collections import defaultdict
import gzip
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil

import pytest
import yaml

from companion_api.corpusprep import competition
from companion_api.corpusprep.registry import Registry, load as load_registry
from companion_api.rag.chunking import chunk_documents
from companion_api.rag.corpus import corpus_issues, parse_document

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "corpus/competition-ar"
BOM = chr(0xFEFF)


def _entry(source_id, digest, fmt="json"):
    return {"source_id": source_id, "format": fmt, "title": source_id, "edition": "test edition",
            "publisher": "Test publisher", "url": f"https://example.org/{source_id}", "license": "test licence",
            "license_url": None, "terms_summary": "test terms", "retrieved_at": "2026-10-04T00:00:00+00:00",
            "sha256": digest, "numbering_system": "test", "status": "pending_legal", "notes": "test"}


def _content():
    def scene(item_id, refs, **extra):
        return {"id": item_id, "text": f"نص المشهد {item_id}", "lesson": f"درس {item_id}", "refs": refs,
                "review_status": "draft", **extra}
    return {
        "package_id": "test-package",
        "stories": [{"id": "story-adam", "title": "قصة تجريبية", "scenes": [
            scene("adam-01", ["quran:2:30-31"]),
            scene("adam-02", ["quran:2:34", "hadith:bukhari:3"], grading="صحيح", evidence_url="https://dorar.net/x/1")]}],
        "adhkar": [{"id": "dhikr-a", "occasions": ["morning", "evening"], "kind": "hadith_invocation",
                    "display": "ذكر تجريبي", "repeat": 3, "refs": ["hadith:muslim-abdulbaqi:591"],
                    "grading": "صحيح مسلم", "child_note": "ملاحظة للطفل", "review_status": "draft"},
                   {"id": "dhikr-b", "occasions": ["after_obligatory_prayer"], "kind": "quran_recitation",
                    "display": "سور تجريبية", "repeat": 100, "refs": ["hadith:abu-dawud:5082", "quran:112:1-2"],
                    "grading": "حسن", "child_note": "ملاحظة أخرى", "review_status": "draft"}],
        "daily_duas": [{"id": "dua-a", "occasion": "before_sleep", "kind": "quran_recitation", "display": "دعاء",
                        "quote_ref": "quran:17:24", "refs": ["quran:17:24"], "child_note": "ملاحظة ثالثة",
                        "review_status": "draft"}],
        "prayer_learning": {
            "fiqh_source": "https://dorar.net/feqhia/880/", "madhhab_applicability": "shared_basics_only",
            "evidence_urls": {"wudu_order": "https://dorar.net/feqhia/289/"},
            "preparation": [{"id": "prep-1", "text": "خطوة أولى", "refs": ["fiqh:prayer:preconditions"]}],
            "wudu": [{"id": "wudu-1", "text": "خطوة ثانية", "refs": ["fiqh:wudu:order"]}],
            "prayer_steps": [{"id": "step-1", "text": "خطوة ثالثة", "refs": ["hadith:bukhari:757", "fiqh:prayer:x"],
                              "evidence_url": "https://dorar.net/hadith/sharh/70527", "grading": "صحيح البخاري"}],
            "prayer_counts": [{"id": "rakah-fajr", "prayer": "الفجر", "rakah": 2, "context": "سياق",
                               "refs": ["fiqh:prayer:counts"], "evidence_url": "https://dorar.net/feqhia/1448/"}]},
    }


QURAN = {(2, 30): "آية", (2, 31): "آية", (2, 34): "آية", (112, 1): BOM + "آية أولى", (112, 2): BOM + "آية ثانية",
         (17, 24): BOM + "آية ثالثة"}


def _docs(content=None):
    entry = _entry(competition.SOURCE_ID, "a" * 64)
    return {doc["id"]: doc for doc in competition.documents(content or _content(), entry, QURAN)}


def test_documents_are_valid_schema_v2_stories_duas_and_lessons_with_comp_ids():
    docs = _docs()
    assert sorted(docs) == ["comp-adam-01", "comp-adam-02", "comp-dhikr-a", "comp-dhikr-b", "comp-dua-a",
                            "comp-prayer-counts", "comp-prayer-preparation", "comp-prayer-steps", "comp-prayer-wudu"]
    assert {docs[i]["contentType"] for i in ("comp-adam-01", "comp-adam-02")} == {"story"}
    assert {docs[i]["contentType"] for i in ("comp-dhikr-a", "comp-dhikr-b", "comp-dua-a")} == {"dua"}
    assert {d["contentType"] for i, d in docs.items() if i.startswith("comp-prayer-")} == {"lesson"}
    parsed = []
    for data in docs.values():
        assert data["tier"] == 2 and data["review"]["status"] == "draft" and data["language"] == "ar"
        assert data["source"]["checksum"] == "a" * 64 and data["source"]["edition"] == "test-package"
        assert data["units"][-1]["keepWithNext"] is False and all(u["keepWithNext"] for u in data["units"][:-1])
        assert all(unit["sourceRefs"] and unit["reference"] == unit["sourceRefs"][0] for unit in data["units"])
        document, issues = parse_document(data, data["id"] + ".json")
        assert document is not None and not [i for i in issues if i.severity == "error"], [str(i) for i in issues]
        parsed.append(document)
    assert not corpus_issues(parsed)
    assert len(chunk_documents(parsed)) == len(parsed)  # each document stays one chunk


def test_a_story_scene_is_its_text_then_its_lesson_under_an_arabic_header():
    data = _docs()["comp-adam-02"]
    assert [unit["id"] for unit in data["units"]] == ["scene", "lesson"]
    assert data["units"][1]["text"] == "الدرس: درس adam-02"
    assert data["title"] == "قصة تجريبية — المشهد 2" and data["prophetId"] == "adam"
    assert data["contextHeader"] == "قصة — قصة تجريبية — المشهد 2 (مسودة حزمة المسابقة)"
    assert data["grading"] == "صحيح" and data["sourceIds"] == [competition.SOURCE_ID]


def test_references_map_to_corpus_source_refs():
    prayer = _content()["prayer_learning"]
    refs = competition.source_refs
    assert refs({"id": "a", "refs": ["quran:2:30-31", "hadith:bukhari:3"]}) == ["quran:2:30-31", "bukhari:3"]
    # Abdul-Baqi's Muslim numbers stay apart from the canonical corpus's muslim:<n> (sunnah.com numbering).
    assert refs({"id": "a", "refs": ["hadith:muslim-abdulbaqi:591"]}) == ["muslim_abdulbaqi:591"]
    assert refs({"id": "a", "refs": ["hadith:abu-dawud:5068", "hadith:abu-dawud:5068"]}) == ["abu_dawud:5068"]
    # fiqh: the item's feqhia page, else the section's evidence URL, else the prayer section's fiqh source;
    # a hadith page is never taken for a fiqh page.
    assert refs({"id": "a", "refs": ["fiqh:prayer:counts"], "evidence_url": "https://dorar.net/feqhia/1448/"},
                prayer) == ["dorar_fiqh:1448"]
    assert refs({"id": "a", "refs": ["fiqh:wudu:order"]}, prayer) == ["dorar_fiqh:289"]
    assert refs({"id": "a", "refs": ["fiqh:prayer:x"], "evidence_url": "https://dorar.net/hadith/sharh/70527"},
                prayer) == ["dorar_fiqh:880"]
    with pytest.raises(competition.CompetitionError, match="no dorar.net/feqhia page"):
        refs({"id": "a", "refs": ["fiqh:prayer:x"]})
    with pytest.raises(competition.CompetitionError, match="unknown reference"):
        refs({"id": "a", "refs": ["tafsir:1:1"]})


def test_occasions_are_labelled_in_arabic_in_the_header():
    assert competition.occasion_label({"occasions": ["morning", "evening"]}) == "أذكار الصباح، أذكار المساء"
    assert competition.occasion_label({"occasion": "before_sleep"}) == "قبل النوم"
    assert set(competition.OCCASIONS_AR) >= {o for item in json.loads((PACKAGE / "content.json").read_text(
        encoding="utf-8"))["adhkar"] for o in item["occasions"]}
    docs = _docs()
    assert docs["comp-dhikr-a"]["contextHeader"] == "أذكار — أذكار الصباح، أذكار المساء (مسودة حزمة المسابقة)"
    assert docs["comp-dua-a"]["contextHeader"] == "أدعية يومية — قبل النوم (مسودة حزمة المسابقة)"
    assert docs["comp-dhikr-b"]["contextHeader"].startswith("أذكار — بعد الصلاة المفروضة")


def test_a_quranic_supplication_carries_its_ayat_and_cites_the_mushaf_source():
    docs = _docs()
    recited = docs["comp-dhikr-b"]
    assert [unit["id"] for unit in recited["units"]] == ["display", "q1", "note"]
    assert recited["units"][0]["text"] == "سور تجريبية — يُقال 100 مرة"
    assert recited["units"][1]["text"] == "﴿آية أولى﴾ (1) ﴿آية ثانية﴾ (2)"  # the dump's byte-order mark dropped
    assert recited["units"][1]["sourceRefs"] == ["quran:112:1-2"]
    assert recited["sourceIds"] == [competition.SOURCE_ID, competition.QURAN_SOURCE_ID]
    assert recited["units"][0]["sourceRefs"] == ["abu_dawud:5082", "quran:112:1-2"]
    invocation = docs["comp-dhikr-a"]
    assert [unit["id"] for unit in invocation["units"]] == ["display", "note"]
    assert invocation["units"][0]["text"] == "ذكر تجريبي — يُقال 3 مرات"
    assert invocation["sourceIds"] == [competition.SOURCE_ID] and invocation["grading"] == "صحيح مسلم"


def test_prayer_sections_are_lessons_of_shared_basics():
    docs = _docs()
    counts = docs["comp-prayer-counts"]
    assert counts["units"][0]["id"] == "rakah-fajr" and counts["units"][0]["text"] == "صلاة الفجر: ركعتان (سياق)"
    assert counts["madhhabScope"] == "common" and counts["title"] == "تعليم الصلاة: عدد ركعات الصلوات المفروضة"
    assert docs["comp-prayer-steps"]["units"][0]["sourceRefs"] == ["bukhari:757", "dorar_fiqh:880"]
    assert docs["comp-prayer-steps"]["grading"] == "صحيح البخاري"
    assert docs["comp-prayer-wudu"]["grading"] is None


def _registry(tmp_path, content_digest, mushaf_digest):
    return Registry(tmp_path / "registry.yaml", "", [
        _entry(competition.SOURCE_ID, content_digest),
        _entry(competition.QURAN_SOURCE_ID, mushaf_digest, fmt="json.gz")])


def _mushaf(path, ayat, version="test"):
    surahs = {}
    for (surah, number), text in ayat.items():
        surahs.setdefault(surah, []).append({"surah": surah, "number": number, "text": text})
    data = {"license": {"version": version},
            "data": {"id": 1, "surahs": [{"id": s, "ayahs": rows} for s, rows in sorted(surahs.items())]}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8")))
    return sha256(path.read_bytes()).hexdigest()


def test_build_checks_content_and_mushaf_against_the_registry(tmp_path):
    content = tmp_path / "content.json"
    content.write_text(json.dumps(_content(), ensure_ascii=False), encoding="utf-8")
    mushaf = tmp_path / "raw" / competition.QURAN_SOURCE_ID / f"{competition.QURAN_SOURCE_ID}.json.gz"
    digest = _mushaf(mushaf, QURAN)
    registry = _registry(tmp_path, sha256(content.read_bytes()).hexdigest(), digest)
    assert len(competition.build(content, registry, tmp_path / "raw")) == 9
    edited = _registry(tmp_path, "0" * 64, digest)
    with pytest.raises(competition.CompetitionError, match="record the new digest"):
        competition.build(content, edited, tmp_path / "raw")
    changed = _registry(tmp_path, sha256(content.read_bytes()).hexdigest(), "0" * 64)
    with pytest.raises(competition.CompetitionError, match="does not match the registry"):
        competition.build(content, changed, tmp_path / "raw")
    with pytest.raises(competition.CompetitionError, match="fetch_sources"):
        competition.build(content, registry, tmp_path / "elsewhere")


def test_the_repository_package_builds_and_the_registry_records_its_digest():
    registry = load_registry(ROOT / "corpus/sources/registry.yaml")
    content, entry = competition.load_content(PACKAGE / "content.json", registry)  # fails when content.json changed
    assert entry["status"] == "pending_legal" and entry["acquisition"] == "authored"
    docs = competition.documents(content, entry, defaultdict(lambda: "آية"))
    assert {doc["contentType"]: sum(d["contentType"] == doc["contentType"] for d in docs) for doc in docs} == \
        {"story": 17, "dua": 22, "lesson": 4}
    assert all(doc["id"].startswith("comp-") for doc in docs)
    assert not [ref for doc in docs for unit in doc["units"] for ref in unit["sourceRefs"] if ref.startswith("muslim:")]
    parsed = [parse_document(doc, doc["id"] + ".json")[0] for doc in docs]
    assert all(parsed) and not corpus_issues(parsed)


# --- corpus/competition-ar/validate.py ---------------------------------------------------------------------

def _validator():
    spec = importlib.util.spec_from_file_location("competition_validate", PACKAGE / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def package(tmp_path):
    """A copy of the package, a registry naming a made-up mushaf (114 surahs, 6236 ayat) and its licence."""
    folder = tmp_path / "package"
    folder.mkdir()
    for name in ("content.json", "sources.json", "evaluation.json", "approvals.json"):
        shutil.copyfile(PACKAGE / name, folder / name)
    used = {int(k): v for k, v in json.loads((folder / "sources.json").read_text(encoding="utf-8"))
            ["quran_verse_counts_used"].items()}
    others = [s for s in range(1, 115) if s not in used]
    left = 6236 - sum(used.values())
    counts = {**used, **{s: left // len(others) + (i < left % len(others)) for i, s in enumerate(others)}}
    raw = tmp_path / "raw"
    mushaf = raw / "quranpedia-mushaf-hafs" / "quranpedia-mushaf-hafs.json.gz"
    digest = _mushaf(mushaf, {(s, n): "آية" for s, count in counts.items() for n in range(1, count + 1)},
                     version="2026-09-30")
    licence = raw / "quranpedia-license" / "quranpedia-license.txt"
    licence.parent.mkdir(parents=True)
    licence.write_text("licence placeholder", encoding="utf-8")
    sources = [_entry("quranpedia-mushaf-hafs", digest, fmt="json.gz"),
               _entry("quranpedia-license", sha256(licence.read_bytes()).hexdigest(), fmt="txt")]
    sources[0]["status"] = sources[1]["status"] = "candidate"
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"schema_version": 1, "sources": sources}, allow_unicode=True),
                        encoding="utf-8")
    return folder, registry, raw


def _edit(folder, change):
    content = json.loads((folder / "content.json").read_text(encoding="utf-8"))
    change(content)
    (folder / "content.json").write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")


def _item(content, item_id):
    return next(item for item in content["adhkar"] + content["daily_duas"] if item["id"] == item_id)


def test_the_validator_passes_the_package_and_counts_items_awaiting_a_check(package):
    folder, registry, raw = package
    errors, summary = _validator().validate(folder, False, registry, raw)
    assert errors == [] and "items awaiting a check" in summary


def test_release_refuses_while_items_need_a_check_or_evidence_does_not_match(package):
    folder, registry, raw = package
    # Every Dorar link was matched to its cited entry on 2026-10-04; a mismatch is made here to test the gate.
    _edit(folder, lambda c: _item(c, "after-prayer-salam").update(evidence_status="mismatch"))
    errors, _ = _validator().validate(folder, True, registry, raw)
    assert any(e.startswith("release blocked:") and "items need a check" in e and "evening-by-god" in e
               for e in errors)
    assert any("evidence link does not show the cited text (after-prayer-salam)" in e for e in errors)
    assert "release blocked: registry source quranpedia-mushaf-hafs is candidate, not cleared" in errors


@pytest.mark.parametrize("change, message", [
    (lambda c: _item(c, "dua-sleep").update(reviewer_guess="x"), "dua-sleep: unknown field reviewer_guess"),
    (lambda c: _item(c, "dua-sleep").update(needs_check=True), "dua-sleep: needs_check needs a change_note"),
    (lambda c: _item(c, "dua-sleep").update(needs_check="yes", change_note="x"), "needs_check must be true or false"),
    (lambda c: _item(c, "dua-sleep").update(evidence_status="unsure", evidence_note="x"),
     "dua-sleep: evidence_status must be one of"),
    (lambda c: (_item(c, "dua-sleep").update(evidence_status="mismatch"), _item(c, "dua-sleep").pop("evidence_note")),
     "evidence_status needs evidence_url and evidence_note"),
    (lambda c: _item(c, "dua-mosque-enter").update(refs=["hadith:muslim:713"]),
     "dua-mosque-enter: hadith:muslim:713: numbering muslim is not declared"),
])
def test_review_flags_and_hadith_numbering_are_checked(package, change, message):
    folder, registry, raw = package
    _edit(folder, change)
    errors, _ = _validator().validate(folder, False, registry, raw)
    assert any(message in error for error in errors), errors


def test_the_quran_is_verified_by_the_registry_sha256(package):
    folder, registry, raw = package
    mushaf = raw / "quranpedia-mushaf-hafs" / "quranpedia-mushaf-hafs.json.gz"
    mushaf.write_bytes(mushaf.read_bytes() + b"\0")
    errors, _ = _validator().validate(folder, False, registry, raw)
    assert any("does not match the registry's sha256" in error for error in errors)
    mushaf.unlink()
    errors, _ = _validator().validate(folder, False, registry, raw)
    assert any("is missing; run scripts/fetch_sources.py" in error for error in errors)


def test_the_package_keeps_no_third_party_dump():
    assert not (PACKAGE / "sources").exists()
    quran = next(s for s in json.loads((PACKAGE / "sources.json").read_text(encoding="utf-8"))["sources"]
                 if s["id"] == "quranpedia-quran")
    assert (quran["registry_source_id"], quran["registry_license_source_id"]) == \
        ("quranpedia-mushaf-hafs", "quranpedia-license")
    assert not {"source_file", "license_file"} & set(quran)
