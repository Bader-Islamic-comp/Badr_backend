"""Document schema v1 and every validation rule in doc/rag-system.md section 3.2."""
import copy
import json

import pytest

from companion_api.rag.corpus import load_corpus, parse_document, parse_eval

DELETE = object()


def passage(**overrides):
    data = {"schemaVersion": 1, "id": "app-help-stars", "kind": "passage", "title": "How learning stars work",
            "language": "en", "ageBands": ["7-9", "10-11"], "contentType": "app_help", "madhhab": [],
            "curriculumPolicy": "dev-synthetic", "synthetic": True,
            "source": {"work": "Robert's guide", "edition": "dev-1", "publisher": "Companion team",
                       "translator": None, "license": "internal", "checksum": None},
            "grading": None, "review": {"status": "draft", "reviewer": None, "approvedOn": None, "supersedes": None},
            "units": [{"id": "u1", "text": "You earn stars by finishing lessons.", "reference": "part 1",
                       "section": "Earning", "keepWithNext": False},
                      {"id": "u2", "text": "Spend them on looks in the Style tab.", "reference": "part 2",
                       "section": "Spending", "keepWithNext": False}]}
    data.update(overrides)
    return data


def answer(**overrides):
    data = passage(id="answer-earn-stars", kind="answer", title="Earning stars",
                   questions=["How do I earn stars?", "How can I get more stars?"],
                   answer="You earn learning stars by finishing lessons.")
    del data["units"]
    data.update(overrides)
    return data


def real(content_type="lesson", **overrides):
    """A non-synthetic document shaped like reviewed content. Its text is an obvious placeholder."""
    data = passage(id="real-doc", contentType=content_type, synthetic=False, curriculumPolicy="placeholder-policy",
                   source={"work": "Placeholder work", "edition": "1st", "publisher": "Placeholder press",
                           "translator": None, "license": "placeholder-licence", "checksum": None},
                   units=[{"id": "u1", "text": "Placeholder unit one.", "reference": "1:1"},
                          {"id": "u2", "text": "Placeholder unit two.", "reference": "1:2"}])
    data.update(overrides)
    return data


def mutate(data, path, value):
    data = copy.deepcopy(data)
    *parents, leaf = [int(part) if part.isdigit() else part for part in path.split(".")]
    target = data
    for part in parents:
        target = target[part]
    if value is DELETE:
        del target[leaf]
    else:
        target[leaf] = value
    return data


def check(data):
    document, issues = parse_document(data, "documents/x.json")
    return document, {(issue.severity, issue.field) for issue in issues}, issues


def write_corpus(root, documents, eval_cases=None, corpus_id="test-corpus"):
    (root / "documents").mkdir(parents=True)
    (root / "corpus.json").write_text(json.dumps({"schemaVersion": 1, "id": corpus_id, "title": "Test corpus",
                                                  "description": "Synthetic test data"}), encoding="utf-8")
    for name, data in documents.items():
        text = data if isinstance(data, str) else json.dumps(data, indent=2)
        (root / "documents" / name).write_text(text, encoding="utf-8")
    if eval_cases is not None:
        (root / "eval.json").write_text(json.dumps({"schemaVersion": 1, "cases": eval_cases}), encoding="utf-8")
    return root


def test_valid_document_builds_with_only_canonical_changes():
    data = mutate(passage(), "units.0.text", "  Cafe\u0301 stars,  earned by  finishing lessons. \n")
    document, found, _ = check(data)
    assert document is not None and not found
    assert document.units[0].text == "Caf\u00e9 stars,  earned by  finishing lessons."
    assert document.units[1].section == "Spending" and not document.units[0].keep_with_next
    assert document.review.status == "draft" and document.source.work == "Robert's guide"
    rebuilt, found, _ = check(document.to_json())
    assert rebuilt == document and not found


@pytest.mark.parametrize("path, value, field", [
    ("id", DELETE, "id"),
    ("id", "Stars_1", "id"),
    ("schemaVersion", 2, "schemaVersion"),
    ("schemaVersion", True, "schemaVersion"),
    ("kind", "article", "kind"),
    ("title", DELETE, "title"),
    ("title", "   ", "title"),
    ("title", 7, "title"),
    ("language", "fr", "language"),
    ("ageBands", ["6-8"], "ageBands[#1]"),
    ("ageBands", ["7-9", "7-9"], "ageBands[#2]"),
    ("ageBands", [], "ageBands"),
    ("ageBands", "7-9", "ageBands"),
    ("contentType", "blog", "contentType"),
    ("madhhab", [""], "madhhab[#1]"),
    ("curriculumPolicy", DELETE, "curriculumPolicy"),
    ("synthetic", "true", "synthetic"),
    ("synthetic", DELETE, "synthetic"),
    ("titel", "typo", "titel"),
    ("source", DELETE, "source"),
    ("source", "Robert's guide", "source"),
    ("source.wrok", "typo", "source.wrok"),
    ("source.work", 3, "source.work"),
    ("review", DELETE, "review"),
    ("review.status", "published", "review.status"),
    ("units", DELETE, "units"),
    ("units", [], "units"),
    ("units.1", "just text", "units[#2]"),
    ("units.1.id", DELETE, "units[#2].id"),
    ("units.1.id", "u 2", "units[#2].id"),
    ("units.1.id", "u1", "units[#2].id"),
    ("units.1.text", "", "units[u2].text"),
    ("units.1.text", DELETE, "units[u2].text"),
    ("units.0.keepWithNext", "yes", "units[u1].keepWithNext"),
    ("units.0.colour", "teal", "units[u1].colour"),
    ("questions", ["How?"], "questions"),
    ("answer", "Text.", "answer"),
])
def test_schema_errors_fail_the_document(path, value, field):
    document, found, _ = check(mutate(passage(), path, value))
    assert document is None
    assert ("error", field) in found


def test_unknown_fields_suggest_the_intended_name():
    _, _, issues = check(mutate(passage(), "colour", "teal"))
    _, _, unit_issues = check(mutate(passage(), "units.0.keepwithNext", True))
    assert issues[0].message.startswith("unknown field; allowed fields are schemaVersion, id, kind")
    assert "did you mean 'keepWithNext'?" in unit_issues[0].message
    assert "did you mean 'title'?" in check(mutate(passage(), "titel", "x"))[2][0].message


def test_answer_documents_use_questions_and_answer():
    document, found, _ = check(answer())
    assert document is not None and not found
    assert document.questions == ("How do I earn stars?", "How can I get more stars?") and document.units == ()


@pytest.mark.parametrize("path, value, field", [
    ("units", passage()["units"], "units"),
    ("questions", DELETE, "questions"),
    ("questions", [], "questions"),
    ("questions", [f"Question number {n}?" for n in range(13)], "questions"),
    ("questions", ["How do I earn stars?", "how do I earn STARS"], "questions[#2]"),
    ("answer", DELETE, "answer"),
    ("answer", " ", "answer"),
    ("answer", "word " * 300, "answer"),
])
def test_answer_document_errors(path, value, field):
    document, found, _ = check(mutate(answer(), path, value))
    assert document is None and ("error", field) in found


@pytest.mark.parametrize("content_type", ["lesson", "story", "quran", "tafsir", "hadith", "dua", "fiqh"])
def test_synthetic_content_is_never_religious(content_type):
    document, found, issues = check(passage(contentType=content_type, grading="placeholder"))
    assert document is None and ("error", "contentType") in found
    assert "synthetic documents may only be app_help or orientation" in issues[0].message


@pytest.mark.parametrize("content_type", ["app_help", "orientation"])
def test_synthetic_app_help_and_orientation_are_allowed(content_type):
    assert check(passage(contentType=content_type))[0] is not None


def test_real_content_requires_full_source_provenance():
    assert check(real())[0] is not None
    document, found, _ = check(real(source={"work": None, "translator": "Someone"}))
    assert document is None
    assert {("error", f"source.{key}") for key in ("work", "edition", "publisher", "license")} <= found
    # Synthetic copy may leave provenance out; a missing work only changes the citation label.
    document, found, _ = check(passage(source={}))
    assert document is not None and found == {("warning", "source.work")}


def test_hadith_requires_grading():
    document, found, _ = check(real("hadith"))
    assert document is None and ("error", "grading") in found
    assert check(real("hadith", grading="placeholder grade (placeholder grader)"))[0] is not None


def test_quran_units_require_a_reference():
    document, found, _ = check(mutate(real("quran"), "units.1.reference", None))
    assert document is None and found == {("error", "units[u2].reference")}
    assert check(real("quran"))[0] is not None


@pytest.mark.parametrize("review, fields", [
    ({"status": "approved"}, {"review.reviewer", "review.approvedOn"}),
    ({"status": "approved", "reviewer": "Board member", "approvedOn": "25/09/2026"}, {"review.approvedOn"}),
    ({"status": "approved", "reviewer": " ", "approvedOn": "2026-09-25"}, {"review.reviewer"}),
    ({"status": "draft", "approvedOn": "yesterday"}, {"review.approvedOn"}),
])
def test_approval_requires_reviewer_and_iso_date(review, fields):
    document, found, _ = check(real(review=review))
    assert document is None and {("error", field) for field in fields} <= found


@pytest.mark.parametrize("approved_on", ["2026-09-25", "2026-09-25T10:30:00Z", "2026-09-25T10:30:00+03:00"])
def test_approved_documents_with_reviewer_and_date_build(approved_on):
    document, found, _ = check(real(review={"status": "approved", "reviewer": "Board member",
                                            "approvedOn": approved_on}))
    assert document is not None and not found and document.review.approved_on == approved_on


def test_keep_with_next_never_crosses_a_section():
    document, found, issues = check(mutate(passage(), "units.0.keepWithNext", True))
    assert document is None and found == {("error", "units[u1].keepWithNext")}
    assert "new section" in issues[0].message
    document, found, _ = check(mutate(passage(), "units.1.keepWithNext", True))
    assert document is not None and found == {("warning", "units[u2].keepWithNext")}


def test_language_mismatch_is_a_warning():
    arabic = ("\u062a\u0639\u0644\u0645 \u0627\u0644\u0646\u062c\u0648\u0645 "
              "\u0645\u0646 \u0627\u0644\u062f\u0631\u0648\u0633")
    document, found, _ = check(mutate(passage(), "units.0.text", arabic))
    assert document is not None and found == {("warning", "units[u1].text")}
    arabic_document = mutate(mutate(passage(language="ar"), "units.0.text", arabic), "units.1.text", arabic + " 2")
    assert check(arabic_document)[1] == set()


def test_document_ids_are_unique_across_files(tmp_path):
    root = write_corpus(tmp_path / "c", {"a.json": passage(id="same-id"), "b.json": answer(id="same-id")})
    corpus, report = load_corpus(root)
    errors = [issue for issue in report.errors if issue.field == "id"]
    assert len(errors) == 1 and errors[0].file == "documents/b.json" and "documents/a.json" in errors[0].message
    assert [document.id for document in corpus.documents] == ["same-id"]


def test_identical_text_is_an_error_and_near_duplicates_warn(tmp_path):
    long = ("Robert keeps his answers short and simple so that everyone can read them, and he shows "
            "the source he used under every answer he gives")
    other = mutate(passage(id="other-doc"), "units.0.text", "you EARN stars - by finishing lessons!")
    other = mutate(other, "units.1.text", long)
    first = mutate(passage(), "units.1.text", long + " today")
    root = write_corpus(tmp_path / "c", {"app-help-stars.json": first, "other-doc.json": other})
    _, report = load_corpus(root)
    errors, warnings = report.errors, report.warnings
    assert [(issue.document, issue.field) for issue in errors] == [("other-doc", "units[u1]")]
    assert "units[u1] in app-help-stars" in errors[0].message
    assert [(issue.severity, issue.document, issue.field) for issue in warnings] == [
        ("warning", "other-doc", "units[u2]")]


def test_identical_answers_and_shared_questions_are_errors(tmp_path):
    root = write_corpus(tmp_path / "c", {
        "answer-one.json": answer(id="answer-one"),
        "answer-two.json": answer(id="answer-two", questions=["How do I EARN stars"], answer="Finish lessons."),
        "answer-three.json": answer(id="answer-three", questions=["Where are the looks?"],
                                    answer="you earn learning stars by finishing lessons")})
    _, report = load_corpus(root)
    assert {(issue.document, issue.field) for issue in report.errors} == {
        ("answer-two", "questions[#1]"), ("answer-three", "answer")}


def test_oversized_units_are_warnings_not_errors(tmp_path):
    big = " ".join(f"word{n}" for n in range(200))
    document = mutate(passage(), "units.1.text", big)
    root = write_corpus(tmp_path / "c", {"app-help-stars.json": document})
    corpus, report = load_corpus(root)
    assert report.ok and [issue.field for issue in report.warnings] == ["units[u2]"]
    assert "200 words" in report.warnings[0].message and len(corpus.documents) == 1
    assert not load_corpus(root, max_chunk_words=250)[1].warnings
    pair = mutate(mutate(passage(), "units.1.section", "Earning"), "units.0.keepWithNext", True)
    root = write_corpus(tmp_path / "d", {"app-help-stars.json": pair})
    _, report = load_corpus(root, max_chunk_words=10)
    assert [issue.field for issue in report.warnings] == ["units[u1]"] and "kept together" in report.warnings[0].message


def test_report_is_precise_and_never_quotes_document_text(tmp_path):
    secret = "SYNTHETIC_UNIT_TEXT_MARKER finishing lessons"
    broken = mutate(mutate(passage(), "units.0.text", secret), "language", "english")
    root = write_corpus(tmp_path / "c", {"app-help-stars.json": broken})
    _, report = load_corpus(root)
    assert not report.ok
    line = report.format().splitlines()[0]
    assert line.startswith("error") and "documents/app-help-stars.json [app-help-stars] language:" in line
    assert 'is "english"; use one of: en, ar' in line
    assert "SYNTHETIC_UNIT_TEXT_MARKER" not in report.format() + json.dumps(report.to_json())
    assert report.to_json()["issues"][0] == {"file": "documents/app-help-stars.json", "document": "app-help-stars",
                                             "field": "language", "severity": "error",
                                             "message": 'is "english"; use one of: en, ar', "line": None}
    assert "Errors must be fixed" in report.summary()


def test_files_are_read_strictly_and_reported_with_locations(tmp_path):
    duplicate_keys = '{"id": "app-help-stars",\n "id": "app-help-other"}'
    root = write_corpus(tmp_path / "c", {"broken.json": '{\n  "id": "x",\n  "title": \n}', "dup.json": duplicate_keys,
                                         "notes.txt": "ignored", "renamed.json": answer()})
    (root / "documents" / "bom.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(passage(id="bom")).encode("utf-8"))
    corpus, report = load_corpus(root)
    by_file = {issue.file: issue for issue in report.issues}
    assert by_file["documents/broken.json"].severity == "error" and by_file["documents/broken.json"].line == 4
    assert by_file["documents/dup.json"].field == "id" and "twice" in by_file["documents/dup.json"].message
    assert by_file["documents/notes.txt"].severity == "warning"
    assert by_file["documents/renamed.json"].severity == "warning" and "answer-earn-stars.json" in \
        by_file["documents/renamed.json"].message
    assert "documents/bom.json" not in {issue.file for issue in report.errors}
    assert {document.id for document in corpus.documents} == {"bom", "answer-earn-stars"}


def test_missing_corpus_files_are_errors(tmp_path):
    assert load_corpus(tmp_path / "nowhere")[0] is None
    (tmp_path / "empty").mkdir()
    corpus, report = load_corpus(tmp_path / "empty")
    assert {issue.file for issue in report.errors} == {"corpus.json", "documents/"}
    root = write_corpus(tmp_path / "c", {})
    assert [issue.message for issue in load_corpus(root)[1].errors] == ["has no .json or .md documents"]
    (root / "corpus.json").write_text('{"schemaVersion": 1, "id": "Bad Id", "title": ""}', encoding="utf-8")
    assert {issue.field for issue in load_corpus(root)[1].errors} >= {"id", "title"}


def test_eval_cases_reference_existing_documents(tmp_path):
    cases = [{"id": "stars-1", "question": "How do I earn stars?",
              "expect": {"answerTypes": ["grounded", "reviewed_answer"], "documents": ["app-help-stars"]}},
             {"id": "missing-1", "question": "Where?", "expect": {"answerTypes": ["grounded"],
                                                                   "documents": ["no-such-doc"]}},
             {"id": "type-1", "question": "Is it allowed?", "expect": {"answerTypes": ["refused"]}},
             {"id": "stars-1", "question": "Duplicate id", "expect": {"answerTypes": ["abstained"]}}]
    root = write_corpus(tmp_path / "c", {"app-help-stars.json": passage()}, cases)
    _, report = load_corpus(root)
    assert {(issue.file, issue.field) for issue in report.errors} == {
        ("eval.json", "cases[missing-1].expect.documents[#1]"), ("eval.json", "cases[type-1].expect.answerTypes[#1]"),
        ("eval.json", "cases[#4].id")}
    parsed, issues = parse_eval({"schemaVersion": 1, "cases": cases[:1]}, {"app-help-stars"})
    assert not issues and parsed[0].answer_types == ("grounded", "reviewed_answer")
    assert parsed[0].documents == ("app-help-stars",)
