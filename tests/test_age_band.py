"""Age-band draft checker (corpus tasks Phase 3). Placeholder tokens only: no child text, no sacred text."""
import copy

from companion_api.corpusprep import age_band


def _w(n: int, offset: int = 0) -> list[str]:
    return [f"كلمة{i}" for i in range(offset, offset + n)]


def _text(words: int, per_sentence: int, offset: int = 0) -> str:
    tokens = _w(words, offset)
    return " ".join(" ".join(tokens[i:i + per_sentence]) + "." for i in range(0, words, per_sentence))


QURAN = " ".join(_w(12, 9000))
FORMULA = " ".join(_w(5, 7000))
INDEX = age_band.SacredIndex([QURAN], [FORMULA + f" {n}" for n in range(age_band.FORMULAIC_DF + 1)]
                             + [" ".join(_w(8, 8000))])
SCHEMA = age_band.load_schema()


def _draft(kind="hadith_explanation", **version):
    base = {"text": "", "lesson": "", "author": None, "reviewer": None, "review_status": "empty",
            "reading_level_checks": None}
    return {"schema_version": 1, "id": "hadith-bukhari-10", "kind": kind, "prophet_id": None, "title": "t",
            "source_refs": ["bukhari:10"], "source_status": "ok", "cluster_id": None, "disputed": False,
            "excluded_details": [], "reviewer_notes": "",
            "versions": {"7-9": dict(base, **version), "10-11": dict(base)}}


def test_empty_templates_pass_and_draft_status_needs_text():
    assert age_band.check_file(_draft(), INDEX, {}, SCHEMA) == []
    problems = age_band.check_file(_draft(review_status="draft"), INDEX, {}, SCHEMA)
    assert problems == ["7-9: review_status is draft but the text is empty"]


def test_written_text_with_empty_status_is_refused():
    problems = age_band.check_file(_draft(text=_text(40, 8), lesson="x"), INDEX, {}, SCHEMA)
    assert problems == ["7-9: text is written but review_status is still empty (set draft)"]


def test_word_count_and_sentence_length_by_band():
    ok = age_band.check_version(dict(text=_text(40, 8), lesson="x", author="a", reviewer=None, review_status="draft"),
                                "hadith_explanation", "7-9", ["bukhari:10"], INDEX, None)
    assert ok["status"] == "pass" and ok["words"] == 40 and ok["longest_sentence"] == 8
    long_sentence = age_band.check_version(dict(text=_text(40, 20), lesson="x", author="a", reviewer=None,
                                                review_status="draft"), "hadith_explanation", "7-9", [], INDEX, None)
    assert any("limit for 7-9 is 14" in error for error in long_sentence["errors"])
    too_short = age_band.check_version(dict(text=_text(40, 8), lesson="x", author="a", reviewer=None,
                                            review_status="draft"), "hadith_explanation", "10-11", [], INDEX, None)
    assert any("outside 60-120" in error for error in too_short["errors"])


def test_typed_sacred_text_is_caught_but_formula_and_markers_are_not():
    typed = _text(30, 8) + " " + " ".join(_w(6, 9003)) + "."
    result = age_band.check_version(dict(text=typed, lesson="x", author="a", reviewer=None, review_status="draft"),
                                    "hadith_explanation", "7-9", [], INDEX, None)
    assert result["sacred_overlaps"] >= 1 and any("[[quote:" in error for error in result["errors"])
    formula = _text(35, 7) + " " + FORMULA + "."
    marker = _text(35, 7) + " [[quote:bukhari:10]]"
    for text in (formula, marker):
        result = age_band.check_version(dict(text=text, lesson="x", author="a", reviewer=None, review_status="draft"),
                                        "hadith_explanation", "7-9", ["bukhari:10"], INDEX, None)
        assert result["sacred_overlaps"] == 0 and result["status"] == "pass", result


def test_marker_must_cite_the_drafts_own_refs_and_reviewer_differs():
    result = age_band.check_version(dict(text=_text(35, 7) + " [[quote:quran:1:1]]", lesson="x", author="a",
                                         reviewer="a", review_status="in_review"),
                                    "hadith_explanation", "7-9", ["bukhari:10"], INDEX, None)
    assert "quote marker quran:1:1 is not one of this draft's source_refs" in result["errors"]
    assert "author and reviewer are the same person" in result["errors"]


def test_schema_refuses_unknown_fields_and_missing_band():
    data = _draft()
    data["child_text"] = "x"
    assert any(problem.startswith("schema:") for problem in age_band.check_file(data, INDEX, {}, SCHEMA))
    data = _draft()
    del data["versions"]["10-11"]
    assert any(problem.startswith("schema:") for problem in age_band.check_file(data, INDEX, {}, SCHEMA))


def test_templates_are_empty_and_cite_sources():
    maps = [{"prophet_id": "yusuf", "ranges": [{"ref": "quran:12:4-6", "topic": "t", "verification": "ok"}]}]
    selection = {"hadith": [{"collection": "nawawi40", "number": "1", "cluster_primary": "bukhari:54",
                             "cluster_id": "hc-bukhari-54", "topic": "t", "needs_check": False}]}
    scene, hadith = age_band.templates(maps, selection)
    assert scene["id"] == "story-yusuf-s01" and scene["source_refs"] == ["quran:12:4-6"]
    assert hadith["id"] == "hadith-bukhari-54" and hadith["source_refs"] == ["bukhari:54", "nawawi40:1"]
    for item in (scene, hadith):
        assert all(v["text"] == "" and v["review_status"] == "empty" for v in item["versions"].values())
        assert age_band.check_file(copy.deepcopy(item), INDEX, {}, SCHEMA) == []
