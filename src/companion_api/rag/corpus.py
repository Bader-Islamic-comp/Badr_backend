"""Corpus documents (schema v1), loading and the validation report (doc/rag-system.md §3).

Corpora are prepared by people who are not programmers, so validation reports
every problem it can find in one pass, each with its file, document, field and
a plain-language message, instead of stopping at the first exception. Errors
fail the build; warnings are advice.

Canonical text is only `normalize.canonical`'d here, never reworded, re-wrapped
or re-cased: it is what a reviewer approved and what a child is shown. Messages
name fields and ids but never quote document text, so a report can be pasted
into a ticket without leaking content.
"""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import difflib
import json
from pathlib import Path
import re

from . import markdown, normalize
from .types import SCHEMA_VERSION

DOCUMENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
UNIT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
KINDS = ("passage", "answer")
LANGUAGES = ("en", "ar")
AGE_BANDS = ("5-6", "7-9", "10-11", "12-14")
CONTENT_TYPES = ("app_help", "orientation", "lesson", "story", "quran", "tafsir", "hadith", "dua", "fiqh")
SYNTHETIC_CONTENT_TYPES = ("app_help", "orientation")
REVIEW_STATUSES = ("draft", "approved")
ANSWER_TYPES = ("unavailable", "grounded", "reviewed_answer", "abstained", "redirected", "safety")
MAX_QUESTIONS = 12
MAX_ANSWER_CHARACTERS = 1200  # a reviewed answer is returned verbatim as the turn text (§7)
MAX_QUESTION_CHARACTERS = 2000  # the API's own bound on a child's question
MAX_TITLE_CHARACTERS = 120  # a source's title as the app shows it under an answer (§7)
MAX_REFERENCE_CHARACTERS = 160  # a source's citation label, "<work> · <first>–<last>" (§4, §7)
NEAR_DUPLICATE_JACCARD = 0.9
DEFAULT_MAX_CHUNK_WORDS = 180

_CORPUS_KEYS = ("schemaVersion", "id", "title", "description")
_DOCUMENT_KEYS = ("schemaVersion", "id", "kind", "title", "language", "ageBands", "contentType", "madhhab",
                  "curriculumPolicy", "synthetic", "source", "grading", "review", "units", "questions", "answer")
_SOURCE_KEYS = ("work", "edition", "publisher", "translator", "license", "checksum")
_REVIEW_KEYS = ("status", "reviewer", "approvedOn", "supersedes")
_UNIT_KEYS = ("id", "text", "reference", "section", "keepWithNext")
_TYPE_NAMES = {bool: "true/false", int: "a number", float: "a number", str: "text", list: "a list",
               dict: "an object", type(None): "null"}


def word_count(text: str) -> int:
    """Words as a reader counts them: whitespace-separated. The chunk budget uses the same count."""
    return len(text.split())


@dataclass(frozen=True)
class Issue:
    file: str
    document: str | None
    field: str | None
    severity: str  # "error" fails the build, "warning" does not
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = self.file + (f":{self.line}" if self.line else "")
        subject = " ".join(part for part in (f"[{self.document}]" if self.document else "", self.field or "") if part)
        return f"{self.severity:<8} {where}" + (f" {subject}" if subject else "") + f": {self.message}"

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        errors, warnings = len(self.errors), len(self.warnings)
        text = f"{errors} error{'s' * (errors != 1)}, {warnings} warning{'s' * (warnings != 1)}."
        if errors:
            text += " Errors must be fixed before a release can be built; warnings are advice."
        return text

    def format(self) -> str:
        # Stable sort: issues stay in reading order within each file.
        return "\n".join([str(issue) for issue in sorted(self.issues, key=lambda issue: issue.file)]
                         + [self.summary()])

    def to_json(self) -> dict:
        return {"ok": self.ok, "errorCount": len(self.errors), "warningCount": len(self.warnings),
                "issues": [issue.to_json() for issue in self.issues]}


@dataclass(frozen=True)
class Unit:
    id: str
    text: str
    reference: str | None = None
    section: str | None = None
    keep_with_next: bool = False


@dataclass(frozen=True)
class Source:
    work: str | None = None
    edition: str | None = None
    publisher: str | None = None
    translator: str | None = None
    license: str | None = None
    checksum: str | None = None


@dataclass(frozen=True)
class Review:
    status: str = "draft"
    reviewer: str | None = None
    approved_on: str | None = None
    supersedes: str | None = None


@dataclass(frozen=True)
class Document:
    id: str
    kind: str
    title: str
    language: str
    age_bands: tuple[str, ...]
    content_type: str
    madhhab: tuple[str, ...]
    curriculum_policy: str
    synthetic: bool
    source: Source
    grading: str | None
    review: Review
    units: tuple[Unit, ...] = ()
    questions: tuple[str, ...] = ()
    answer: str | None = None
    # Where it came from, for messages only: the relative file and, for Markdown, field -> line.
    file: str = field(default="", compare=False)
    lines: dict = field(default_factory=dict, compare=False, repr=False)

    def to_json(self) -> dict:
        """The canonical JSON form (§3.1), in the documented key order."""
        data = {
            "schemaVersion": SCHEMA_VERSION, "id": self.id, "kind": self.kind, "title": self.title,
            "language": self.language, "ageBands": list(self.age_bands), "contentType": self.content_type,
            "madhhab": list(self.madhhab), "curriculumPolicy": self.curriculum_policy, "synthetic": self.synthetic,
            "source": asdict(self.source), "grading": self.grading,
            "review": {"status": self.review.status, "reviewer": self.review.reviewer,
                       "approvedOn": self.review.approved_on, "supersedes": self.review.supersedes},
        }
        if self.kind == "answer":
            data.update(questions=list(self.questions), answer=self.answer)
        else:
            data["units"] = [{"id": unit.id, "text": unit.text, "reference": unit.reference, "section": unit.section,
                              "keepWithNext": unit.keep_with_next} for unit in self.units]
        return data


@dataclass(frozen=True)
class Corpus:
    id: str
    title: str
    description: str
    path: Path
    documents: tuple[Document, ...]


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    answer_types: tuple[str, ...]
    documents: tuple[str, ...] = ()


def _kind_of(value) -> str:
    return _TYPE_NAMES.get(type(value), type(value).__name__)


def _show(value, limit: int = 40) -> str:
    """Echoes a short field value (an id, a language code), never document text."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return '"' + (text if len(text) <= limit else text[:limit - 3] + "...") + '"'


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        pass
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


class _Checker:
    """Collects issues for one file so every problem is reported, not only the first."""

    def __init__(self, file: str, lines: dict | None = None, document: str | None = None):
        self.file, self.lines, self.document = file, lines or {}, document
        self.issues: list[Issue] = []

    def _line(self, name: str | None) -> int | None:
        # "units[u2].text" falls back to "units[u2]", then "units".
        while name:
            if name in self.lines:
                return self.lines[name]
            cut = max(name.rfind("."), name.rfind("["))
            name = name[:cut] if cut > 0 else ""
        return None

    def add(self, severity: str, name: str | None, message: str, line: int | None = None):
        self.issues.append(Issue(self.file, self.document, name, severity, message, line or self._line(name)))

    def error(self, name: str | None, message: str, line: int | None = None):
        self.add("error", name, message, line)

    def warning(self, name: str | None, message: str):
        self.add("warning", name, message)

    @property
    def failed(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def keys(self, data: dict, allowed: tuple[str, ...], prefix: str = ""):
        for key in data:
            if key not in allowed:
                close = difflib.get_close_matches(key, allowed, n=1)
                hint = f"did you mean {close[0]!r}?" if close else "allowed fields are " + ", ".join(allowed)
                self.error(prefix + key, f"unknown field; {hint}")

    def text(self, data: dict, key: str, name: str, *, required: bool = True) -> str | None:
        value = data.get(key)
        if value is None:
            if required:
                self.error(name, "is required" if key not in data else "must not be null")
            return None
        if not isinstance(value, str):
            self.error(name, f"must be text, not {_kind_of(value)}")
            return None
        value = normalize.canonical(value)
        if not value and required:
            self.error(name, "must not be empty")
        return value or None

    def choice(self, data: dict, key: str, name: str, allowed: tuple[str, ...]) -> str | None:
        value = data.get(key)
        if value is None:
            self.error(name, "is required; use one of: " + ", ".join(allowed))
            return None
        if value not in allowed:
            self.error(name, f"is {_show(value)}; use one of: " + ", ".join(allowed))
            return None
        return value

    def flag(self, data: dict, key: str, name: str, default: bool | None = None) -> bool | None:
        value = data.get(key, default)
        if value is None:
            self.error(name, "is required; use true or false")
        elif not isinstance(value, bool):
            self.error(name, f"must be true or false (without quotes), not {_show(value)}")
            return None
        return value

    def strings(self, data: dict, key: str, name: str, *, allowed: tuple[str, ...] | None = None,
                required: bool = True) -> tuple[str, ...] | None:
        value = data.get(key)
        if value is None:
            if required:
                self.error(name, "is required" + ("; use a list of: " + ", ".join(allowed) if allowed else ""))
                return None
            return ()
        if not isinstance(value, list):
            self.error(name, f"must be a list [...], not {_kind_of(value)}")
            return None
        items: list[str] = []
        for position, item in enumerate(value, 1):
            item_name = f"{name}[#{position}]"
            item = normalize.canonical(item) if isinstance(item, str) else item
            if not isinstance(item, str) or not item:
                self.error(item_name, "must be non-empty text")
            elif allowed and item not in allowed:
                self.error(item_name, f"is {_show(item)}; use one of: " + ", ".join(allowed))
            elif item in items:
                self.error(item_name, "is listed twice")
            else:
                items.append(item)
        return tuple(items)


def _check_language(check: _Checker, name: str, text: str, language: str | None):
    """Retrieval filters by language, so a mislabelled document would silently never be found."""
    if language in LANGUAGES and any(character.isalpha() for character in text):
        detected = normalize.detect_language(text)
        if detected != language:
            check.warning(name, f"looks like {detected} text but the document language is {language}")


def _parse_source(check: _Checker, value) -> Source | None:
    if not isinstance(value, dict):
        check.error("source", "is required: an object with work, edition, publisher, translator, license and "
                              "checksum (null where unknown)" if value is None else
                    f"must be an object {{...}}, not {_kind_of(value)}")
        return None
    check.keys(value, _SOURCE_KEYS, "source.")
    return Source(**{key: check.text(value, key, f"source.{key}", required=False) for key in _SOURCE_KEYS})


def _parse_review(check: _Checker, value) -> Review | None:
    if not isinstance(value, dict):
        check.error("review", 'is required, for example {"status": "draft"}' if value is None else
                    f"must be an object {{...}}, not {_kind_of(value)}")
        return None
    check.keys(value, _REVIEW_KEYS, "review.")
    status = check.choice(value, "status", "review.status", REVIEW_STATUSES)
    reviewer = check.text(value, "reviewer", "review.reviewer", required=False)
    approved_on = check.text(value, "approvedOn", "review.approvedOn", required=False)
    supersedes = check.text(value, "supersedes", "review.supersedes", required=False)
    if approved_on and not _is_iso_date(approved_on):
        check.error("review.approvedOn", f"must be an ISO date like 2026-09-25, not {_show(approved_on)}")
    if status == "approved":  # §3.2 rule 4
        if not reviewer:
            check.error("review.reviewer", "is required when review.status is approved: record who approved it")
        if not approved_on:
            check.error("review.approvedOn", "is required when review.status is approved: the ISO date it was "
                                             "approved, like 2026-09-25")
    return Review(status or "draft", reviewer, approved_on, supersedes)


def _parse_units(check: _Checker, data: dict, language: str | None) -> tuple[Unit, ...]:
    for key in ("questions", "answer"):
        if key in data:
            check.error(key, "belongs to answer documents (kind: answer); passage documents use units")
    value = data.get("units")
    if not isinstance(value, list) or not value:
        check.error("units", "must list at least one unit" if value in (None, []) else
                    f"must be a list [...], not {_kind_of(value)}")
        return ()
    units: list[Unit] = []
    seen: set[str] = set()
    for position, raw in enumerate(value, 1):
        name = f"units[#{position}]"
        if not isinstance(raw, dict):
            check.error(name, f"must be an object with id and text, not {_kind_of(raw)}")
            continue
        unit_id = raw.get("id")
        if not isinstance(unit_id, str) or not UNIT_ID.match(unit_id):
            check.error(name + ".id", "is required" if unit_id is None else
                        "must be 1-64 characters of letters, digits, '.', '_' or '-'")
            unit_id = None
        elif unit_id in seen:
            check.error(name + ".id", f"{_show(unit_id)} is already used by another unit in this document")
            unit_id = None
        else:
            seen.add(unit_id)
            name = f"units[{unit_id}]"
        check.keys(raw, _UNIT_KEYS, name + ".")
        text = check.text(raw, "text", name + ".text")
        reference = check.text(raw, "reference", name + ".reference", required=False)
        section = check.text(raw, "section", name + ".section", required=False)
        keep = check.flag(raw, "keepWithNext", name + ".keepWithNext", default=False)
        if text:
            _check_language(check, name + ".text", text, language)
        if unit_id and text and keep is not None:
            units.append(Unit(unit_id, text, reference, section, keep))
    for index, unit in enumerate(units):
        if not unit.keep_with_next:
            continue
        if index + 1 == len(units):
            check.warning(f"units[{unit.id}].keepWithNext",
                          "is set on the last unit, so there is nothing to keep it with")
        elif units[index + 1].section != unit.section:
            check.error(f"units[{unit.id}].keepWithNext",
                        "is set but the next unit starts a new section, and a chunk never crosses a section; "
                        "move the section heading or remove keepWithNext")
    return tuple(units)


def _parse_answer(check: _Checker, data: dict, language: str | None) -> tuple[tuple[str, ...], str | None]:
    if "units" in data:
        check.error("units", "belongs to passage documents; answer documents use questions and answer instead")
    questions = check.strings(data, "questions", "questions")
    if questions is not None:
        if not 1 <= len(questions) <= MAX_QUESTIONS:
            check.error("questions", f"must list 1 to {MAX_QUESTIONS} phrasings, not {len(questions)}")
        seen: dict[str, int] = {}
        for position, question in enumerate(questions, 1):
            key = normalize.search_text(question)
            if key in seen:
                check.error(f"questions[#{position}]", f"is the same question as questions[#{seen[key]}] once case "
                                                       "and punctuation are ignored")
            seen.setdefault(key, position)
    answer = check.text(data, "answer", "answer")
    if answer:
        _check_language(check, "answer", answer, language)
        if len(answer) > MAX_ANSWER_CHARACTERS:
            check.error("answer", f"has {len(answer)} characters; a reviewed answer is shown as it is and the app "
                                  f"shows at most {MAX_ANSWER_CHARACTERS}")
    return questions or (), answer


def parse_document(data, file: str, lines: dict | None = None) -> tuple[Document | None, list[Issue]]:
    """Checks one document on its own (§3.2 rules 1-4) and builds it when there are no errors.

    Rules that compare documents (unique ids, duplicates) and the chunk budget
    are in `corpus_issues`, because they need the whole corpus.
    """
    check = _Checker(file, lines)
    if not isinstance(data, dict):
        check.error(None, f"a document must be one JSON object {{...}}, not {_kind_of(data)}")
        return None, check.issues
    raw_id = data.get("id")
    if isinstance(raw_id, str) and DOCUMENT_ID.match(raw_id):
        check.document = raw_id
    else:
        check.error("id", "is required" if raw_id is None else
                    "must be 2-64 characters of lowercase a-z, 0-9 and '-', starting with a letter or digit")
    check.keys(data, _DOCUMENT_KEYS)
    version = data.get("schemaVersion")
    if version != SCHEMA_VERSION or isinstance(version, bool):
        check.error("schemaVersion",
                    f"must be {SCHEMA_VERSION}" + ("" if version is None else f", not {_show(version)}"))
    kind = check.choice(data, "kind", "kind", KINDS)
    title = check.text(data, "title", "title")
    language = check.choice(data, "language", "language", LANGUAGES)
    age_bands = check.strings(data, "ageBands", "ageBands", allowed=AGE_BANDS)
    if data.get("ageBands") == []:
        check.error("ageBands", "must list at least one of: " + ", ".join(AGE_BANDS))
    content_type = check.choice(data, "contentType", "contentType", CONTENT_TYPES)
    madhhab = check.strings(data, "madhhab", "madhhab", required=False)
    curriculum_policy = check.text(data, "curriculumPolicy", "curriculumPolicy")
    synthetic = check.flag(data, "synthetic", "synthetic")
    source = _parse_source(check, data.get("source"))
    grading = check.text(data, "grading", "grading", required=False)
    review = _parse_review(check, data.get("review"))
    units, questions, answer = (), (), None
    if kind == "passage":
        units = _parse_units(check, data, language)
    elif kind == "answer":
        questions, answer = _parse_answer(check, data, language)

    # §3.2 rule 2: invented religious text is the one thing this pipeline must not make easy.
    if synthetic is True and content_type and content_type not in SYNTHETIC_CONTENT_TYPES:
        check.error("contentType", f"is {content_type}, but synthetic documents may only be app_help or orientation. "
                                   "Religious content must be real, with full source details and scholarly review")
    # §3.2 rule 3: real content carries its provenance.
    if synthetic is False and source is not None:
        for key in ("work", "edition", "publisher", "license"):
            if not getattr(source, key):
                check.error(f"source.{key}", "is required for real (non-synthetic) content")
    if content_type == "hadith" and not grading:
        check.error("grading", "is required for hadith: record the grading and who graded it")
    if content_type == "quran":
        for unit in units:
            if not unit.reference:
                check.error(f"units[{unit.id}].reference", "is required for quran: every verse needs its reference")
    if synthetic is True and source is not None and not source.work:
        check.warning("source.work", "is empty, so citations will show the document title instead of a source name")
    # §7: the app refuses a whole reply whose source title or reference is too long to show,
    # so a document that could produce one is stopped here rather than at answer time.
    if title and len(title) > MAX_TITLE_CHARACTERS:
        check.error("title", f"has {len(title)} characters; a source title shows at most {MAX_TITLE_CHARACTERS}")
    if title and source is not None:
        longest = max((len(unit.reference) for unit in units if unit.reference), default=0)
        label = len(source.work or title) + (len(" · –") + 2 * longest if longest else 0)
        if label > MAX_REFERENCE_CHARACTERS:
            check.error("source.work", f"with the longest unit reference, a citation label could reach {label} "
                                       f"characters; the app shows at most {MAX_REFERENCE_CHARACTERS}. Shorten the "
                                       "work name or the references")

    if check.failed:
        return None, check.issues
    return Document(id=raw_id, kind=kind, title=title, language=language, age_bands=age_bands,
                    content_type=content_type, madhhab=madhhab, curriculum_policy=curriculum_policy,
                    synthetic=synthetic, source=source, grading=grading, review=review, units=units,
                    questions=questions, answer=answer, file=file, lines=dict(lines or {})), check.issues


def keep_groups(units) -> list[list[Unit]]:
    """Runs of units joined by keepWithNext, never across a section. The chunker packs these whole."""
    groups: list[list[Unit]] = []
    for unit in units:
        joined = groups and groups[-1][-1].keep_with_next and groups[-1][-1].section == unit.section
        if joined:
            groups[-1].append(unit)
        else:
            groups.append([unit])
    return groups


def corpus_issues(documents, max_chunk_words: int = DEFAULT_MAX_CHUNK_WORDS) -> list[Issue]:
    """§3.2 rules 5 and 6 across the whole corpus: duplicates and the chunk budget."""
    checks = {document.id: _Checker(document.file, document.lines, document.id) for document in documents}
    items = []  # (order, document, field, search text), in document order
    for document in documents:
        check = checks[document.id]
        for unit in document.units:
            words = word_count(unit.text)
            if words > max_chunk_words:
                check.warning(f"units[{unit.id}]", f"has {words} words, more than the {max_chunk_words}-word chunk "
                                                  "budget; it becomes one oversized chunk (units are never split)")
            items.append((len(items), document, f"units[{unit.id}]", normalize.search_text(unit.text)))
        for group in keep_groups(document.units):
            words = sum(word_count(unit.text) for unit in group)
            if len(group) > 1 and words > max_chunk_words:
                check.warning(f"units[{group[0].id}]",
                              f"units {group[0].id} to {group[-1].id} are kept together by keepWithNext and have "
                              f"{words} words, more than the {max_chunk_words}-word budget; they become one "
                              "oversized chunk")
        if document.answer:
            items.append((len(items), document, "answer", normalize.search_text(document.answer)))

    first: dict[str, tuple] = {}
    for order, document, name, search in items:
        if not search:
            continue
        if search in first:
            _, other, other_name, _ = first[search]
            checks[document.id].error(name, f"has the same text as {other_name} in {other.id} "
                                            "(ignoring case and punctuation); remove one of them")
        else:
            first[search] = (order, document, name, search)
    # Near duplicates: Jaccard >= t needs the smaller set to be at least t of the larger,
    # so after sorting by size each item is only compared with a short window after it.
    distinct = sorted(((len(set(search.split())), set(search.split()), item) for search, item in first.items()),
                      key=lambda entry: (entry[0], entry[2][0]))
    for index, (size, tokens, item) in enumerate(distinct):
        for other_size, other_tokens, other in distinct[index + 1:]:
            if not size or size < NEAR_DUPLICATE_JACCARD * other_size:
                break
            if len(tokens & other_tokens) / len(tokens | other_tokens) >= NEAR_DUPLICATE_JACCARD:
                earlier, later = sorted((item, other), key=lambda entry: entry[0])
                checks[later[1].id].warning(later[2], f"is nearly the same as {earlier[2]} in {earlier[1].id}; "
                                                      "check that both are needed")

    owners: dict[str, tuple[str, int]] = {}
    for document in documents:
        for position, question in enumerate(document.questions, 1):
            key = normalize.search_text(question)
            if key in owners and owners[key][0] != document.id:
                checks[document.id].error(f"questions[#{position}]", f"is also a question of {owners[key][0]}; each "
                                                                     "phrasing may belong to one reviewed answer")
            owners.setdefault(key, (document.id, position))
    return [issue for check in checks.values() for issue in check.issues]


def _read_json(path: Path, name: str, report: Report):
    """Returns the parsed value, or `None` after reporting why it could not be read."""
    try:
        text = path.read_text(encoding="utf-8-sig")  # Windows editors often add a byte-order mark
    except UnicodeDecodeError:
        report.issues.append(Issue(name, None, None, "error", "is not saved as UTF-8 text; save it again as UTF-8"))
        return None
    except OSError as exception:
        report.issues.append(Issue(name, None, None, "error", f"could not be read ({type(exception).__name__})"))
        return None
    duplicates: list[str] = []

    def unique_keys(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                duplicates.append(key)
            data[key] = value
        return data

    try:
        data = json.loads(text, object_pairs_hook=unique_keys)
    except json.JSONDecodeError as error:
        report.issues.append(Issue(name, None, None, "error", f"is not valid JSON: {error.msg} at line {error.lineno}, "
                                                             f"column {error.colno}", error.lineno))
        return None
    for key in dict.fromkeys(duplicates):
        report.issues.append(Issue(name, None, key, "error", "appears twice in the same object; keep only one"))
    return None if duplicates else data


def _read_document(path: Path, name: str, report: Report):
    """(data, lines) for a .json or .md document, or `None` after reporting the problem."""
    if path.suffix.lower() == ".json":
        data = _read_json(path, name, report)
        return None if data is None else (data, {})
    try:
        parsed = markdown.parse(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        report.issues.append(Issue(name, None, None, "error", "is not saved as UTF-8 text; save it again as UTF-8"))
        return None
    except markdown.MarkdownError as error:
        report.issues.extend(Issue(name, None, None, "error", message, line) for line, message in error.errors)
        return None
    return parsed.data, parsed.lines


def _load_metadata(root: Path, report: Report) -> tuple[str, str, str]:
    if not (root / "corpus.json").is_file():
        report.issues.append(Issue("corpus.json", None, None, "error",
                                   'is missing; create it with {"schemaVersion": 1, "id": "...", "title": "...", '
                                   '"description": "..."}'))
        return "", "", ""
    data = _read_json(root / "corpus.json", "corpus.json", report)
    if data is None:
        return "", "", ""
    check = _Checker("corpus.json")
    if not isinstance(data, dict):
        check.error(None, f"must be one JSON object {{...}}, not {_kind_of(data)}")
        report.issues.extend(check.issues)
        return "", "", ""
    check.keys(data, _CORPUS_KEYS)
    if data.get("schemaVersion") != SCHEMA_VERSION or isinstance(data.get("schemaVersion"), bool):
        check.error("schemaVersion", f"must be {SCHEMA_VERSION}")
    corpus_id = data.get("id")
    if not isinstance(corpus_id, str) or not DOCUMENT_ID.match(corpus_id):
        check.error("id", "must be 2-64 characters of lowercase a-z, 0-9 and '-', starting with a letter or digit")
        corpus_id = ""
    title = check.text(data, "title", "title") or ""
    description = check.text(data, "description", "description", required=False) or ""
    report.issues.extend(check.issues)
    return corpus_id, title, description


def parse_eval(data, document_ids=None, file: str = "eval.json") -> tuple[list[EvalCase], list[Issue]]:
    """Evaluation cases (§8). With `document_ids`, expected documents must exist in the corpus."""
    check = _Checker(file)
    if not isinstance(data, dict):
        check.error(None, f"must be one JSON object {{...}}, not {_kind_of(data)}")
        return [], check.issues
    check.keys(data, ("schemaVersion", "cases"))
    if data.get("schemaVersion") != SCHEMA_VERSION or isinstance(data.get("schemaVersion"), bool):
        check.error("schemaVersion", f"must be {SCHEMA_VERSION}")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        check.error("cases", "must be a non-empty list of cases")
        return [], check.issues
    cases, seen = [], set()
    for position, raw in enumerate(raw_cases, 1):
        name = f"cases[#{position}]"
        if not isinstance(raw, dict):
            check.error(name, "must be an object with id, question and expect")
            continue
        case_id = raw.get("id")
        if not isinstance(case_id, str) or not DOCUMENT_ID.match(case_id) or case_id in seen:
            check.error(name + ".id", "must be a unique id of lowercase a-z, 0-9 and '-'")
            case_id = None
        else:
            seen.add(case_id)
            name = f"cases[{case_id}]"
        check.keys(raw, ("id", "question", "expect"), name + ".")
        question = check.text(raw, "question", name + ".question")
        if question and len(question) > MAX_QUESTION_CHARACTERS:
            check.error(name + ".question", f"is longer than the {MAX_QUESTION_CHARACTERS} characters the app accepts")
        expect = raw.get("expect")
        if not isinstance(expect, dict):
            check.error(name + ".expect", 'must be an object like {"answerTypes": ["grounded"]}')
            continue
        check.keys(expect, ("answerTypes", "documents"), name + ".expect.")
        answer_types = check.strings(expect, "answerTypes", name + ".expect.answerTypes", allowed=ANSWER_TYPES)
        if expect.get("answerTypes") == []:
            check.error(name + ".expect.answerTypes", "must list at least one answer type")
        documents = check.strings(expect, "documents", name + ".expect.documents", required=False)
        for position_in_list, document_id in enumerate(documents or (), 1):
            if document_ids is not None and document_id not in document_ids:
                check.error(f"{name}.expect.documents[#{position_in_list}]",
                            f"{_show(document_id)} is not a document in this corpus")
        if documents and answer_types and not {"grounded", "reviewed_answer"} & set(answer_types):
            check.warning(name + ".expect.documents", "is only checked for grounded or reviewed_answer cases")
        if case_id and question and answer_types and documents is not None:
            cases.append(EvalCase(case_id, question, answer_types, documents))
    return cases, check.issues


def load_corpus(path, *, max_chunk_words: int = DEFAULT_MAX_CHUNK_WORDS) -> tuple[Corpus | None, Report]:
    """Loads and validates a corpus directory. Only documents without errors are in the corpus.

    The report is authoritative: callers build only when `report.ok`.
    """
    root = Path(path)
    report = Report()
    if not root.is_dir():
        report.issues.append(Issue(str(root), None, None, "error", "is not a folder; point at a corpus folder that "
                                                                  "contains corpus.json and documents/"))
        return None, report
    corpus_id, title, description = _load_metadata(root, report)
    documents: list[Document] = []
    owners: dict[str, str] = {}  # document id -> file, including documents that have errors
    folder = root / "documents"
    files = sorted(folder.iterdir(), key=lambda item: item.name) if folder.is_dir() else []
    candidates = 0
    if not folder.is_dir():
        report.issues.append(Issue("documents/", None, None, "error", "folder is missing"))
    for item in files:
        name = f"documents/{item.name}"
        if item.name.startswith("."):
            continue
        if not item.is_file() or item.suffix.lower() not in (".json", ".md"):
            report.issues.append(Issue(name, None, None, "warning", "is not a .json or .md document and is ignored"))
            continue
        candidates += 1
        loaded = _read_document(item, name, report)
        if loaded is None:
            continue
        data, lines = loaded
        document, issues = parse_document(data, name, lines)
        report.issues.extend(issues)
        raw_id = data.get("id") if isinstance(data, dict) else None
        if isinstance(raw_id, str) and DOCUMENT_ID.match(raw_id):
            if raw_id in owners:
                report.issues.append(Issue(name, raw_id, "id", "error",
                                           f"is already used by {owners[raw_id]}; ids must be unique (keep either "
                                           "the Markdown or the JSON form, not both)"))
                document = None
            else:
                owners[raw_id] = name
                if item.stem != raw_id:
                    report.issues.append(Issue(name, raw_id, "id", "warning", f"does not match the file name; name the "
                                               f"file {raw_id}{item.suffix.lower()} so it is easy to find"))
        if document is not None:
            documents.append(document)
    if folder.is_dir() and not candidates:
        report.issues.append(Issue("documents/", None, None, "error", "has no .json or .md documents"))
    documents.sort(key=lambda document: document.id)
    report.issues.extend(corpus_issues(documents, max_chunk_words))
    if (root / "eval.json").is_file():
        data = _read_json(root / "eval.json", "eval.json", report)
        if data is not None:
            report.issues.extend(parse_eval(data, set(owners))[1])
    return Corpus(corpus_id, title, description, root, tuple(documents)), report
