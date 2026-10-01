"""The knowledge graph (knowledge/graph.py, kg-v1) on a tiny invented corpus. Placeholder text only."""
import json

import pytest

from companion_api.knowledge import graph as kg

AYAT = {
    (1, 1): "كلمات تجريبية أولى عن القارب الكبير والماء والجبل البعيد",
    (1, 2): "قال نوح لقومه اركبوا القارب الكبير قبل أن يأتي المطر الغزير",
    (2, 1): "هذه آية تجريبية أخرى عن الشجرة الخضراء في الحديقة الواسعة",
}
HADITH = {
    "1": "حدثنا نوح بن فلان عن فلان عن رسول الله قال إن الصدق يهدي إلى البر وإن البر يهدي إلى الجنة دائما",
    "2": "حدثنا فلان عن فلان أن النبي قال كلمة تجريبية عن الصبر والشكر والرحمة بين الناس في كل يوم وليلة",
}
SECTION = ("شرح تجريبي للآية الأولى. وقد قال تعالى: قال نوح لقومه اركبوا القارب الكبير قبل أن يأتي المطر الغزير. "
           "وروى البخاري أن النبي قال كلمة تجريبية عن الصبر والشكر والرحمة بين الناس في كل يوم وليلة "
           "[[صحيح البخاري برقم (٢)]] [[صحيح مسلم برقم (١٠٠)]]")


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    _write(root / "canonical/quran/ayat.jsonl",
           [{"surah": s, "ayah": a, "text_normalized": kg.normalize.search_text(t), "text_uthmani": t}
            for (s, a), t in AYAT.items()])
    _write(root / "canonical/hadith/bukhari.jsonl",
           [{"collection": "bukhari", "number": n, "arabic_text": t, "grading": "sahih", "eligible": True}
            for n, t in HADITH.items()])
    _write(root / "canonical/tafsir/ibn-kathir.jsonl",
           [{"section_id": "ibn-kathir:1:1", "surah": 1, "from_ayah": 1, "to_ayah": 1, "quran_refs": ["quran:1:1"],
             "text": SECTION, "source_id": "ibn-kathir-ar-001", "editor_notes": 2, "words": 50}])
    (root / "aliases.yaml").write_text(
        "prophets:\n- id: nuh\n  names_ar:\n  - {alias: نوح}\n  latin: [Nuh]\n", encoding="utf-8")
    (root / "candidate/prophets").mkdir(parents=True)
    (root / "candidate/prophets/nuh_source_map.yaml").write_text(
        "prophet_id: nuh\nranges:\n- {ref: 'quran:1:1-2', topic: the boat}\n", encoding="utf-8")
    return root


def _edges(graph, kind):
    return {(edge["source"], edge["target"]): edge for edge in graph.edges.values() if edge["type"] == kind}


def test_structure_and_curated_story_links(corpus):
    graph = kg.build(corpus, {1: "أولى", 2: "ثانية"})
    assert {node["type"] for node in graph.nodes.values()} == {"surah", "ayah", "hadith", "prophet", "tafsir_section"}
    assert ("quran:1:2", "surah:1") in _edges(graph, "IN_SURAH")
    assert set(_edges(graph, "STORY_IN")) == {("prophet:nuh", "quran:1:1"), ("prophet:nuh", "quran:1:2")}
    assert set(_edges(graph, "EXPLAINS")) == {("ibn-kathir:1:1", "quran:1:1")}


def test_a_section_quoting_another_ayah_is_linked_to_it(corpus):
    quotes = _edges(kg.build(corpus), "QUOTES_AYAH")
    assert quotes[("ibn-kathir:1:1", "quran:1:2")]["coverage"] == 1.0
    assert ("ibn-kathir:1:1", "quran:1:1") not in quotes  # its own ayah is EXPLAINS, not a quotation


def test_the_editors_citation_is_linked_and_confirmed_by_text(corpus):
    graph = kg.build(corpus)
    cited = _edges(graph, "CITES_HADITH")[("ibn-kathir:1:1", "bukhari:2")]
    assert cited["status"] == "text_confirmed" and "editor_note" in cited["method"] and cited["editor_number"] == 2
    assert [u["editor_number"] for u in graph.unresolved] == [100]  # Muslim by Abdul-Baqi, no Muslim text here


def test_names_count_except_narrators(corpus):
    mentions = _edges(kg.build(corpus), "MENTIONS_PROPHET")
    assert ("quran:1:2", "prophet:nuh") in mentions
    assert ("bukhari:1", "prophet:nuh") not in mentions  # "حدثنا نوح بن فلان" is a narrator, and in the isnad


def test_takhrij_reads_bukhari_and_muslim_numbers_only():
    assert kg.takhrij("وصحيح البخاري برقم (٤٦٨٨) .") == [("bukhari", 4688)]
    assert kg.takhrij("صحيح مسلم برقم (٢٢٤٣، ٢٢٤٤)") == [("muslim", 2243), ("muslim", 2244)]
    assert kg.takhrij("الأدب المفرد للبخاري برقم (١٢)") == []


def test_the_matn_starts_at_the_first_mention_of_the_prophet():
    tokens = "حدثنا يونس عن الزهري ان رسول الله قال يرحم الله يونس".split()
    assert kg.matn(tokens)[:2] == ["رسول", "الله"]


def test_the_graph_files_hold_ids_and_counts_not_text(corpus, tmp_path):
    graph = kg.build(corpus)
    summary = kg.write(graph, tmp_path / "out", inputs_sha256=kg.inputs_digest(corpus))
    written = (tmp_path / "out/nodes.jsonl").read_text(encoding="utf-8") + \
        (tmp_path / "out/edges.jsonl").read_text(encoding="utf-8")
    assert "القارب" not in written and "الصبر" not in written
    assert summary["graph_version"] == "kg-v1" and summary["edges"]["EXPLAINS"] == 1
