"""The Markdown authoring form (doc/rag-system.md section 3.3) and `import-markdown`."""
import json
from pathlib import Path

import pytest

from companion_api.rag import markdown
from companion_api.rag.corpus import load_corpus, parse_document
from companion_api.rag.pipeline import main

DEV_CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "dev-app-help"

PASSAGE = """---
schemaVersion: 1
id: app-help-looks
kind: passage
title: Choosing a look
language: en
ageBands: 7-9, 10-11
contentType: app_help
madhhab:
curriculumPolicy: dev-synthetic
synthetic: true
source.work: Robert's guide: second part
source.translator: null
review.status: draft
---

Before any heading. {ref: intro}

## The looks

Open the Style tab
to see the looks. {keep-with-next}{ref: looks 1}

Sunset Copper costs 5 stars.   {ref: looks 2}

## Changes ##
Robert's colours change {curly} text inside.

Last one.
"""

ANSWER = """---
schemaVersion: 1
id: answer-take-break
kind: answer
title: Taking a break
language: en
ageBands: 7-9
contentType: orientation
curriculumPolicy: dev-synthetic
synthetic: true
questions: Can I take a break? | How do I pause?|I feel tired, can I stop?
source.work: Robert's guide
review.status: draft
---

Yes. You can pause
whenever you need.

Come back later.
"""


def test_front_matter_sections_references_and_keep_with_next():
    parsed = markdown.parse(PASSAGE)
    data = parsed.data
    assert data["schemaVersion"] == 1 and data["synthetic"] is True
    assert data["ageBands"] == ["7-9", "10-11"] and data["madhhab"] == []
    assert data["source"] == {"work": "Robert's guide: second part", "translator": None}
    assert data["review"] == {"status": "draft"}
    assert [(unit["id"], unit["text"], unit["reference"], unit["section"], unit["keepWithNext"])
            for unit in data["units"]] == [
        ("u1", "Before any heading.", "intro", None, False),
        ("u2", "Open the Style tab to see the looks.", "looks 1", "The looks", True),
        ("u3", "Sunset Copper costs 5 stars.", "looks 2", "The looks", False),
        ("u4", "Robert's colours change {curly} text inside.", None, "Changes", False),
        ("u5", "Last one.", None, "Changes", False),
    ]
    assert parsed.lines["title"] == 5 and parsed.lines["source.work"] == 12 and parsed.lines["source"] == 12
    assert [parsed.lines[f"units[u{n}]"] for n in range(1, 6)] == [17, 21, 24, 27, 29]
    document, issues = parse_document(data, "documents/app-help-looks.md", parsed.lines)
    assert document is not None and not issues
    assert document.units[1].keep_with_next and document.units[3].section == "Changes"


def test_answer_documents_take_questions_and_the_body():
    parsed = markdown.parse(ANSWER)
    assert parsed.data["questions"] == ["Can I take a break?", "How do I pause?", "I feel tired, can I stop?"]
    assert parsed.data["answer"] == "Yes. You can pause whenever you need.\n\nCome back later."
    assert "units" not in parsed.data and parsed.lines["answer"] == 16
    document, issues = parse_document(parsed.data, "documents/answer-take-break.md", parsed.lines)
    assert document is not None and not issues and document.kind == "answer"


@pytest.mark.parametrize("text, line, fragment", [
    ("title: x\n", 1, "starts with a line '---'"),
    ("---\nid: x\n", 1, "never closed"),
    ("---\nid: x\nthis is not a key\n---\n", 3, "'key: value'"),
    ("---\nid: x\nid: y\n---\n", 3, "already set on line 2"),
    ("---\nunits: x\n---\n", 2, "comes from the text below"),
    ("---\nsynthetic: yes\n---\n", 2, "true or false"),
    ("---\nschemaVersion: one\n---\n", 2, "whole number"),
    ("---\nageBands: 7-9,\n---\n", 2, "empty item"),
    ("---\nquestions: One? || Two?\n---\n", 2, "' | '"),
    ("---\nsource: x\nsource.work: y\n---\n", 3, "cannot be combined"),
    ("---\nsource.work: y\nsource: x\n---\n", 3, "cannot be combined"),
    ("---\nsource.work.name: y\n---\n", 2, "'key: value'"),
    ("---\n---\n# Title\n", 3, "only '## Section name'"),
    ("---\n---\n\nText.\n\n### Sub\n", 6, "only '## Section name'"),
    ("---\n---\n##\n", 3, "only '## Section name'"),
    ("---\n---\n- first point\n", 3, "bullet lists"),
    ("---\n---\nText. {note: x}\n", 3, "unknown marker {note: x}"),
    ("---\n---\nText {ref: 1}\nmore text.\n", 3, "go at the end"),
    ("---\n---\nText. {ref: }\n", 3, "needs a reference"),
    ("---\n---\nFirst line\nText. {ref: a} {ref: b}\n", 4, "only one {ref"),
    ("---\n---\nText. {keep-with-next} {keep-with-next}\n", 3, "appears twice"),
    ("---\n---\n\n{keep-with-next}\n", 4, "no text"),
    ("---\n---\nText.\n---\n", 4, "only used around the front matter"),
    ("---\nkind: answer\n---\n## Heading\n", 4, "no sections"),
    ("---\nkind: answer\n---\n\nText {ref: 1}\n", 5, "no {ref: ...}"),
])
def test_errors_carry_line_numbers(text, line, fragment):
    with pytest.raises(markdown.MarkdownError) as error:
        markdown.parse(text)
    assert any(number == line and fragment in message for number, message in error.value.errors), error.value.errors


def test_every_problem_in_a_file_is_reported_at_once():
    with pytest.raises(markdown.MarkdownError) as error:
        markdown.parse("---\nsynthetic: maybe\nbad line\n---\n# One\n\n- two\n")
    assert [line for line, _ in error.value.errors] == [2, 3, 5, 7]
    assert "line 2:" in str(error.value)


def test_validation_issues_point_at_markdown_lines(tmp_path):
    root = tmp_path / "corpus"
    (root / "documents").mkdir(parents=True)
    (root / "corpus.json").write_text('{"schemaVersion": 1, "id": "md-test", "title": "Markdown test"}',
                                      encoding="utf-8")
    real = (PASSAGE.replace("language: en", "language: fr").replace("synthetic: true", "synthetic: false")
            .replace("contentType: app_help", "contentType: quran"))
    (root / "documents" / "app-help-looks.md").write_text(real, encoding="utf-8")
    (root / "documents" / "broken.md").write_text("---\nid: broken\nsynthetic: maybe\n", encoding="utf-8")
    _, report = load_corpus(root)
    found = {(issue.file, issue.field, issue.line) for issue in report.errors}
    assert ("documents/app-help-looks.md", "language", 6) in found
    assert ("documents/app-help-looks.md", "source.edition", 12) in found  # absent: points at the source block
    assert ("documents/app-help-looks.md", "units[u4].reference", 27) in found
    assert ("documents/broken.md", None, 3) in found and ("documents/broken.md", None, 1) in found
    assert "documents/app-help-looks.md:6 [app-help-looks] language:" in report.format()


def test_import_markdown_writes_canonical_json(tmp_path, capsys):
    source, out = tmp_path / "md", tmp_path / "json"
    source.mkdir()
    (source / "app-help-looks.md").write_text(PASSAGE, encoding="utf-8")
    (source / "answer-take-break.md").write_text(ANSWER, encoding="utf-8")
    assert main(["import-markdown", str(source), str(out)]) == 0
    assert sorted(path.name for path in out.iterdir()) == ["answer-take-break.json", "app-help-looks.json"]
    written = json.loads((out / "app-help-looks.json").read_text(encoding="utf-8"))
    assert list(written)[:4] == ["schemaVersion", "id", "kind", "title"]
    assert written["source"]["edition"] is None and written["units"][1]["keepWithNext"] is True
    assert written["units"][2]["keepWithNext"] is False and written["units"][2]["reference"] == "looks 2"
    parsed = markdown.parse(PASSAGE)
    assert parse_document(written, "x.json")[0] == parse_document(parsed.data, "x.md", parsed.lines)[0]

    assert main(["import-markdown", str(source / "app-help-looks.md"), str(out)]) == 1
    assert "already exists" in capsys.readouterr().out
    assert main(["import-markdown", str(source / "app-help-looks.md"), str(out), "--overwrite"]) == 0


def test_import_markdown_writes_nothing_when_any_file_has_errors(tmp_path, capsys):
    source, out = tmp_path / "md", tmp_path / "json"
    source.mkdir()
    (source / "a-good.md").write_text(PASSAGE, encoding="utf-8")
    (source / "b-bad.md").write_text(PASSAGE.replace("kind: passage", "kind: article"), encoding="utf-8")
    (source / "c-broken.md").write_text("no front matter\n", encoding="utf-8")
    assert main(["import-markdown", str(source), str(out)]) == 1
    output = capsys.readouterr()
    assert "b-bad.md:4 [app-help-looks] kind:" in output.out and "c-broken.md:1:" in output.out
    assert "Nothing was written" in output.err and not out.exists()
    assert main(["import-markdown", str(tmp_path / "missing.md"), str(out)]) == 1
    twins = tmp_path / "twins"
    twins.mkdir()
    (twins / "one.md").write_text(PASSAGE, encoding="utf-8")
    (twins / "two.md").write_text(PASSAGE, encoding="utf-8")
    assert main(["import-markdown", str(twins), str(out)]) == 1
    assert "also used by another file" in capsys.readouterr().out and not out.exists()


def test_dev_corpus_markdown_matches_its_json_form(tmp_path):
    out = tmp_path / "json"
    assert main(["import-markdown", str(DEV_CORPUS / "documents"), str(out)]) == 0
    corpus, _ = load_corpus(DEV_CORPUS)
    loaded = {document.id: document for document in corpus.documents}
    converted = sorted(out.glob("*.json"))
    assert converted and all(document.file.endswith(".md") for document in
                             (loaded[path.stem] for path in converted))
    for path in converted:
        assert parse_document(json.loads(path.read_text(encoding="utf-8")), path.name)[0] == loaded[path.stem]
