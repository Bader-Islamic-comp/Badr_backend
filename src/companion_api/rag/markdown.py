"""The Markdown authoring form of a document (doc/rag-system.md §3.3).

People writing content by hand should not have to balance JSON braces, so this
form is a flat front matter block plus paragraphs. It is deliberately small and
strict: anything it does not recognise is an error with a line number, never a
guess, because a misread marker would change what a child is shown.

    ---
    schemaVersion: 1
    id: app-help-looks
    kind: passage
    ageBands: 7-9, 10-11
    source.work: Robert's guide
    ...
    ---

    A paragraph is one unit. {ref: part 1}

    ## A section heading

    Another unit, kept with the next one. {ref: part 2} {keep-with-next}

Lines of one paragraph are joined with single spaces, as Markdown displays
them; the text is otherwise taken as written. This module only turns the file
into the document's JSON shape. `corpus.parse_document` validates it, using the
line numbers recorded here to point at the right line.
"""
from dataclasses import dataclass, field
import re

from . import normalize

_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9]*)?$")
_MARKER = re.compile(r"\{([^{}]*)\}\s*$")
_BODY_MARKER = re.compile(r"\{\s*(ref\s*:|keep-with-next)")
_HEADING = re.compile(r"^(#+)\s*(.*?)\s*#*$")
_BULLET = re.compile(r"^[-*+]\s")
_INTEGERS = {"schemaVersion"}
_BOOLEANS = {"synthetic"}
_LISTS = {"ageBands": ",", "madhhab": ",", "questions": "|"}
_FROM_BODY = {"units", "answer"}


class MarkdownError(ValueError):
    """Every problem found in one file, as (line, message) pairs."""

    def __init__(self, errors: list[tuple[int, str]]):
        self.errors = errors
        super().__init__("; ".join(f"line {line}: {message}" for line, message in errors))


@dataclass(frozen=True)
class ParsedMarkdown:
    data: dict
    # Field path -> line, for example "title", "source.work", "units[u3]", "answer".
    lines: dict = field(default_factory=dict)


def _value(key: str, raw: str, line: int, errors: list):
    if key in _LISTS:
        if not raw:
            return []
        items = [item.strip() for item in raw.split(_LISTS[key])]
        if any(not item for item in items):
            separator = "' | '" if _LISTS[key] == "|" else "commas"
            errors.append((line, f"{key} has an empty item; separate items with {separator} and no trailing separator"))
        return [item for item in items if item]
    if raw in ("", "null"):
        return None
    if key in _INTEGERS:
        if not raw.isdigit():
            errors.append((line, f"{key} must be a whole number like 1"))
            return None
        return int(raw)
    if key in _BOOLEANS:
        if raw not in ("true", "false"):
            errors.append((line, f"{key} must be true or false"))
            return None
        return raw == "true"
    return raw


def _front_matter(lines: list[str], errors: list) -> tuple[dict, dict, int]:
    """Parses the block between the `---` fences. Returns data, line map and the first body line index."""
    if not lines or lines[0].strip() != "---":
        errors.append((1, "a Markdown document starts with a line '---', then 'key: value' lines, then '---'"))
        return {}, {}, 0
    data, where, given = {}, {}, {}
    for index in range(1, len(lines)):
        number, text = index + 1, lines[index].strip()
        if text == "---":
            return data, where, index + 1
        if not text:
            continue
        key, colon, raw = text.partition(":")
        key, raw = key.strip(), raw.strip()
        if not colon or not _KEY.match(key):
            errors.append((number, "front matter lines are 'key: value', for example 'title: How stars work' "
                                   "or 'source.work: Robert's guide'"))
            continue
        if key in _FROM_BODY:
            errors.append((number, f"{key} comes from the text below the front matter, not from a '{key}:' line"))
            continue
        if key in given:
            errors.append((number, f"{key} is already set on line {given[key]}"))
            continue
        given[key] = where[key] = number
        value = _value(key, raw, number, errors)
        if "." in key:
            parent, leaf = key.split(".")
            if parent in data and not isinstance(data[parent], dict):
                errors.append((number, f"{key} cannot be combined with a plain '{parent}:' line"))
                continue
            data.setdefault(parent, {})[leaf] = value
            where.setdefault(parent, number)
        elif isinstance(data.get(key), dict):
            errors.append((number, f"'{key}:' cannot be combined with '{key}.<field>:' lines"))
        else:
            data[key] = value
    errors.append((1, "the front matter is never closed; add a line '---' after the last 'key: value' line"))
    return data, where, len(lines)


def _paragraph(block: list[tuple[int, str]], errors: list) -> tuple[str, str | None, bool]:
    """Joins one paragraph's lines and takes its trailing `{ref: ...}` and `{keep-with-next}` markers."""
    text = " ".join(line for _, line in block)
    last = block[-1][0]
    reference, keep = None, False
    while True:
        match = _MARKER.search(text)
        if not match:
            break
        marker = match.group(1).strip()
        if marker == "keep-with-next":
            if keep:
                errors.append((last, "{keep-with-next} appears twice in one paragraph"))
            keep = True
        elif re.match(r"ref\s*:", marker):
            value = marker.split(":", 1)[1].strip()
            if not value:
                errors.append((last, "{ref: ...} needs a reference, for example {ref: part 1}"))
            elif reference is not None:
                errors.append((last, "a paragraph can have only one {ref: ...}"))
            reference = value if reference is None else reference
        else:
            errors.append((last, f"unknown marker {{{marker}}}; use {{ref: ...}} or {{keep-with-next}}"))
        text = text[:match.start()].rstrip()
    for number, line in block:
        if _BODY_MARKER.search(line) and text and _BODY_MARKER.search(text):
            errors.append((number, "{ref: ...} and {keep-with-next} go at the end of a paragraph"))
            break
    if not text:
        errors.append((block[0][0], "this paragraph has markers but no text"))
    return text, reference, keep


def parse(text: str) -> ParsedMarkdown:
    """The document dict and a line map, or `MarkdownError` listing every problem found."""
    errors: list[tuple[int, str]] = []
    lines = text.lstrip("\ufeff").splitlines()
    data, where, start = _front_matter(lines, errors)
    answer = data.get("kind") == "answer"
    paragraphs: list[tuple[str | None, list[tuple[int, str]]]] = []  # (section, lines)
    section, block = None, []

    def flush():
        if block:
            paragraphs.append((section, list(block)))
            block.clear()

    for index in range(start, len(lines)):
        number, line = index + 1, lines[index].strip()
        if not line:
            flush()
        elif line.startswith("#"):
            flush()
            heading = _HEADING.match(line)
            if answer:
                errors.append((number, "answer documents have no sections; remove the heading"))
            elif len(heading.group(1)) != 2 or not heading.group(2):
                errors.append((number, "only '## Section name' headings are allowed; a '#' at the start of a line "
                                       "always means a heading"))
            else:
                section = normalize.canonical(heading.group(2))
        elif line == "---":
            errors.append((number, "'---' is only used around the front matter"))
        elif _BULLET.match(line):
            errors.append((number, "bullet lists are not supported; write each point as its own paragraph, "
                                   "separated by a blank line"))
        else:
            block.append((number, line))
    flush()

    if answer:
        for _, paragraph in paragraphs:
            if any(_BODY_MARKER.search(line) for _, line in paragraph):
                errors.append((paragraph[0][0], "answer documents have no {ref: ...} or {keep-with-next} markers"))
        data["answer"] = "\n\n".join(" ".join(line for _, line in paragraph) for _, paragraph in paragraphs)
        if paragraphs:
            where["answer"] = paragraphs[0][1][0][0]
    else:
        units = []
        for position, (section_name, paragraph) in enumerate(paragraphs, 1):
            unit_text, reference, keep = _paragraph(paragraph, errors)
            units.append({"id": f"u{position}", "text": unit_text, "reference": reference, "section": section_name,
                          "keepWithNext": keep})
            where[f"units[u{position}]"] = paragraph[0][0]
        data["units"] = units
        where.setdefault("units", start + 1)
    if errors:
        raise MarkdownError(sorted(errors))
    return ParsedMarkdown(data, where)
