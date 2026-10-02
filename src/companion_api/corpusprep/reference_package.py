"""The challenge's reference package (`corpus/sources/reference_package.yaml`) checked against the registry.

The package («المرجعية والحزمة العلمية والبيانات», version 20/3/1448) lists the approved sources and a binding
output standard. This module loads the package file, checks it against the source registry and renders
`doc/governance/reference-package.md`; `scripts/check_reference_package.py` runs both.

A check fails when:
  * a registry source has no `package_rule`;
  * the package file names a registry id that does not exist (in a row, `already_present_outside_rule`, a
    ruling or an open question; `prefix-001..114` is a range of zero-padded ids);
  * a source whose rule is outside_rule, borderline or not_listed is `cleared` without an organizers' ruling
    that admits it (`rulings`, below);
  * a ruling is incomplete (who answered, when, the answer, where the written answer is kept);
  * a row's acquisition disagrees with its registry sources' (downloaded = download, crawled = crawl,
    manual = manual; blocked and reference rows name no registry source);
  * a file cited by the standard or levels mapping does not exist.

A ruling is necessary, not sufficient: clearing a source stays a signed governance decision
(doc/decisions/README.md). Nothing here changes a source's status.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re

import yaml

from .registry import PACKAGE_RULES

SCHEMA_VERSION = 1
NEEDS_RULING = ("outside_rule", "borderline", "not_listed")
ANSWERS = ("admitted", "admitted_with_conditions", "not_admitted")
ADMITTING = ("admitted", "admitted_with_conditions")
ROW_ACQUISITIONS = {"downloaded": "download", "crawled": "crawl", "manual": "manual", "blocked": None,
                    "reference": None}
_RANGE = re.compile(r"^(?P<prefix>[a-z0-9-]*?-)(?P<first>\d+)\.\.(?P<last>\d+)$")


class PackageError(ValueError):
    pass


def expand(ids) -> list[str]:
    """Registry ids, with `prefix-001..114` expanded to every zero-padded id in the range."""
    expanded = []
    for item in ids or []:
        match = _RANGE.match(str(item))
        if match is None:
            expanded.append(str(item))
            continue
        width, first, last = len(match["first"]), int(match["first"]), int(match["last"])
        if last < first:
            raise PackageError(f"{item}: a range must not run backwards")
        expanded += [f"{match['prefix']}{number:0{width}d}" for number in range(first, last + 1)]
    return expanded


def load(path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise PackageError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    return data


def named_ids(package: dict) -> dict[str, list[str]]:
    """Every registry id the package file names, with where it names it."""
    where: dict[str, list[str]] = {}
    for row in package.get("rows") or []:
        for source in row.get("sources") or []:
            for sid in expand(source.get("registry")):
                where.setdefault(sid, []).append(f"{row['field']} / {source['name']}")
        for sid in expand(row.get("already_present_outside_rule")):
            where.setdefault(sid, []).append(f"{row['field']} / already present, outside the rule")
    for ruling in package.get("rulings") or []:
        for sid in expand(ruling.get("sources")):
            where.setdefault(sid, []).append(f"ruling {ruling.get('ruling_id')}")
    for question in package.get("open_questions") or []:
        for sid in expand(question.get("sources")):
            where.setdefault(sid, []).append(f"open question {question.get('id')}")
    return where


def admitting_rulings(package: dict) -> dict[str, list[str]]:
    admitted: dict[str, list[str]] = {}
    for ruling in package.get("rulings") or []:
        if ruling.get("answer") in ADMITTING:
            for sid in expand(ruling.get("sources")):
                admitted.setdefault(sid, []).append(str(ruling.get("ruling_id")))
    return admitted


def _ruling_problems(package: dict) -> list[str]:
    problems, seen = [], set()
    for position, ruling in enumerate(package.get("rulings") or [], 1):
        name = f"rulings[{position}]"
        if not isinstance(ruling, dict):
            problems.append(f"{name}: must be a mapping")
            continue
        rid = ruling.get("ruling_id")
        if not rid:
            problems.append(f"{name}: ruling_id: is required")
        elif rid in seen:
            problems.append(f"{name}: ruling_id {rid} is used twice")
        seen.add(rid)
        name = f"ruling {rid or position}"
        if not expand(ruling.get("sources")):
            problems.append(f"{name}: sources: names no registry source")
        if ruling.get("answer") not in ANSWERS:
            problems.append(f"{name}: answer: must be one of {', '.join(ANSWERS)}")
        if ruling.get("answer") == "admitted_with_conditions" and not ruling.get("conditions"):
            problems.append(f"{name}: conditions: required when the answer is admitted_with_conditions")
        for key in ("question", "by", "date", "evidence"):
            if not str(ruling.get(key) or "").strip():
                problems.append(f"{name}: {key}: is required (who answered, when, and where the written "
                                "answer is kept)")
        if ruling.get("date") and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(ruling["date"])):
            problems.append(f"{name}: date: must be YYYY-MM-DD")
    return problems


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    by_rule: dict[str, dict] = field(default_factory=dict)


def check(sources: list[dict], package: dict, root: Path | None = None) -> Report:
    report = Report()
    by_id = {source["source_id"]: source for source in sources}
    for source in sources:
        rule = source.get("package_rule")
        if rule is None:
            report.problems.append(f"{source['source_id']}: package_rule: is required "
                                   f"({', '.join(PACKAGE_RULES)})")
            rule = "missing"
        entry = report.by_rule.setdefault(rule, {"sources": 0, "status": {}, "acquisition": {}})
        entry["sources"] += 1
        entry["status"][source["status"]] = entry["status"].get(source["status"], 0) + 1
        acquisition = source.get("acquisition", "download")
        entry["acquisition"][acquisition] = entry["acquisition"].get(acquisition, 0) + 1
    try:
        named = named_ids(package)
        admitted = admitting_rulings(package)
    except PackageError as error:
        report.problems.append(str(error))
        return report
    for sid, places in sorted(named.items()):
        if sid not in by_id:
            report.problems.append(f"{sid}: named in reference_package.yaml ({places[0]}) but not in the registry")
    report.problems += _ruling_problems(package)
    for source in sources:
        if source.get("package_rule") in NEEDS_RULING and source["status"] == "cleared" \
                and source["source_id"] not in admitted:
            report.problems.append(
                f"{source['source_id']}: status cleared, package_rule {source['package_rule']}, but no organizers' "
                "ruling in reference_package.yaml admits it")
    for row in package.get("rows") or []:
        for item in row.get("sources") or []:
            acquisition = item.get("acquisition")
            if acquisition not in ROW_ACQUISITIONS:
                report.problems.append(f"{row['field']} / {item['name']}: acquisition: must be one of "
                                       f"{', '.join(ROW_ACQUISITIONS)}")
                continue
            expected, ids = ROW_ACQUISITIONS[acquisition], expand(item.get("registry"))
            if expected is None and ids:
                report.problems.append(f"{row['field']} / {item['name']}: a {acquisition} source names registry "
                                       f"ids ({ids[0]}…)")
            for sid in ids:
                if sid in by_id and by_id[sid].get("acquisition", "download") != expected:
                    report.problems.append(f"{sid}: registry acquisition {by_id[sid].get('acquisition', 'download')}"
                                           f", but reference_package.yaml says {acquisition}")
    if root is not None:
        for path in sorted(cited_files(package)):
            if not (root / path).exists():
                report.problems.append(f"{path}: cited by the standard or levels mapping, but it does not exist")
    content_rules = ("listed", "in_rule", "conditional", "borderline", "outside_rule")
    unnamed = [s["source_id"] for s in sources if s.get("package_rule") in content_rules and s["source_id"] not in named]
    if unnamed:
        report.warnings.append(f"{len(unnamed)} sources with a package rule are not named in reference_package.yaml "
                               f"(e.g. {', '.join(unnamed[:3])})")
    if not (package.get("package") or {}).get("permission_evidence"):
        report.warnings.append("the organizers' permission is reported but its written confirmation is not "
                               "recorded (package.permission_evidence)")
    return report


_FILE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|yaml|json|jsonl|csv))`")


def cited_files(package: dict) -> set[str]:
    """Repository paths cited in the standard and levels mapping (`path` in backquotes or `files`)."""
    paths: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "files":
                    paths.update(str(path) for path in item or [])
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            paths.update(_FILE.findall(value))

    walk(package.get("standard"))
    walk(package.get("levels"))
    return paths


# --- doc/governance/reference-package.md ------------------------------------------------------------------

RULE_MEANING = {
    "listed": "the package names this source or its publisher",
    "in_rule": "the package's rule admits it (a tafsir of the first three Hijri centuries, the two Sahihs)",
    "conditional": "admitted per record once a condition holds (a hadith with an approved grading in the data)",
    "borderline": "needs the organizers' reading",
    "outside_rule": "the rule as written does not admit it",
    "not_listed": "the package does not name it for this role; kept for cross-checking",
    "not_applicable": "licence texts and metadata",
}
ACQUIRED = {"download": "downloaded", "crawl": "crawled", "manual": "manual"}
_DIGITS = re.compile(r"\d+")


def _cell(text) -> str:
    return " ".join(str(text if text is not None else "").split()).replace("|", "\\|")


def counts(values: dict) -> str:
    return ", ".join(f"{key} {value}" for key, value in sorted(values.items()))


def _groups(sources: list[dict]) -> list[list[dict]]:
    """Consecutive sources that differ only by a number in the title (the 114 per-surah files) share a row."""
    groups: list[list[dict]] = []
    keys: list[tuple] = []
    for source in sources:
        key = (source.get("dataset"), source.get("package_basis"), source["status"],
               source.get("acquisition", "download"), _DIGITS.sub("#", source["title"]))
        if groups and keys[-1] == key:
            groups[-1].append(source)
        else:
            groups.append([source])
            keys.append(key)
    return groups


def _link(path: str) -> str:
    return f"[`{path}`](../../{path})"


def _plural(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _words(text) -> str:
    return " ".join(str(text or "").split())


def render(sources: list[dict], package: dict, report: Report) -> str:
    meta = package.get("package") or {}
    lines = [
        "# The challenge's reference package (draft)", "",
        "Generated by `python scripts/check_reference_package.py --write` from `corpus/sources/reference_package.yaml`",
        "and `corpus/sources/registry.yaml`; do not edit by hand. Status: **draft for the governance owner (Mousa",
        "al-Rashdan) and the scholarly board.** Nothing here clears a source or changes its registry status: the",
        "organizers' answers are recorded as `rulings` in `reference_package.yaml`, and clearing a source stays a",
        "signed governance decision (`doc/decisions/README.md`).", "",
        f"Package: «{meta.get('title')}», version {meta.get('version')}. Permission: {meta.get('permission')}. "
        f"Where the written confirmation is kept: {meta.get('permission_evidence') or 'not recorded yet'}.", "",
        "## Check", "",
        "`python scripts/check_reference_package.py` fails when a registry source has no `package_rule`, when",
        "`reference_package.yaml` names a registry id that does not exist, when a source whose rule is",
        "`outside_rule`, `borderline` or `not_listed` is `cleared` without an organizers' ruling that admits it, when a",
        "ruling is incomplete, when a row's acquisition disagrees with the registry, or when a file cited below does",
        f"not exist. Today: {_plural(len(report.problems), 'problem')}, {_plural(len(report.warnings), 'warning')}.", "",
        "| package rule | meaning | sources | registry status | acquisition |", "| --- | --- | ---: | --- | --- |"]
    for rule in (*PACKAGE_RULES, "missing"):
        if rule in report.by_rule:
            entry = report.by_rule[rule]
            acquired = {ACQUIRED.get(key, key): value for key, value in entry["acquisition"].items()}
            lines.append(f"| `{rule}` | {_cell(RULE_MEANING.get(rule, 'no package_rule'))} | {entry['sources']} | "
                         f"{counts(entry['status'])} | {counts(acquired)} |")
    for warning in report.warnings:
        lines += ["", f"Warning: {warning}."]
    lines += ["", "## Sources by package rule", "",
              "Acquisition: downloaded (`scripts/fetch_sources.py`), crawled (`scripts/crawl_jamharah.py`) or manual",
              "(a person downloads it). The package's sources that refuse scripts (blocked) follow in the next section."]
    for rule in PACKAGE_RULES:
        members = [source for source in sources if source.get("package_rule") == rule]
        if not members:
            continue
        lines += ["", f"### `{rule}`: {RULE_MEANING[rule]}", "",
                  "| source | title | status | acquisition | basis |", "| --- | --- | --- | --- | --- |"]
        for group in _groups(members):
            first = group[0]
            ids = f"`{first['source_id']}`" if len(group) == 1 else \
                f"`{first['source_id']}` … `{group[-1]['source_id']}` ({len(group)} files)"
            title = first["title"] if len(group) == 1 else                 f"{first['title']} … {' '.join(_DIGITS.findall(group[-1]['title'])) or group[-1]['title']}"
            lines.append(f"| {ids} | {_cell(title)} | {first['status']} | "
                         f"{ACQUIRED[first.get('acquisition', 'download')]} | {_cell(first.get('package_basis'))} |")
    lines += ["", "## The package's sources outside the registry", "",
              "| field | source | acquisition | why |", "| --- | --- | --- | --- |"]
    for row in package.get("rows") or []:
        for item in row.get("sources") or []:
            if not item.get("registry"):
                name = f"[{_cell(item['name'])}]({item['url']})" if item.get("url") else _cell(item["name"])
                lines.append(f"| {_cell(row['field'])} | {name} | {item['acquisition']} | {_cell(item.get('why'))} |")
        for item in row.get("not_taken") or []:
            lines.append(f"| {_cell(row['field'])} | {_cell(item['name'])} | not taken | {_cell(item.get('why'))} |")
    lines += ["", "## The output standard (page 5)", "",
              "Each clause as the package states it (paraphrased), how this repository implements it, and the gaps",
              "found on `test/corpus-tasks` (2026-10-02)."]
    for clause in package.get("standard") or []:
        lines += ["", f"### {clause['clause']}. {clause['title']}", "", f"> {_words(clause['rule'])}", "",
                  "Implemented:", ""]
        for item in clause.get("implemented") or []:
            lines.append(f"- {_words(item['text'])} ({', '.join(_link(path) for path in item['files'])})")
        lines += ["", "Gaps:", ""]
        lines += [f"- {_words(gap)}" for gap in clause.get("gaps") or []] or ["- None found."]
    lines += ["", "## Content levels (page 2) and Robert's routes", "",
              "| level | the package asks | Robert | answer types | gap |", "| --- | --- | --- | --- | --- |"]
    for level in package.get("levels") or []:
        types = ", ".join(f"`{name}`" for name in level.get("answer_types") or [])
        lines.append(f"| {_cell(level['level'])}: {_cell(level['name'])} | {_cell(level['package'])} | "
                     f"{_cell(level['robert'])} | {types} | {_cell(level.get('gap'))} |")
    lines += ["", "## Open questions for the organizers", ""]
    for question in package.get("open_questions") or []:
        named = ""
        if question.get("sources"):
            named = " Sources: " + ", ".join(f"`{sid}`" for sid in question["sources"]) + "."
        lines.append(f"- **{question['id']}. {question['topic']}.** {_words(question['question'])}{named}")
    lines += ["", "## The organizers' rulings", ""]
    rulings = package.get("rulings") or []
    if not rulings:
        lines.append("None recorded yet. The format is above `rulings` in `corpus/sources/reference_package.yaml`.")
    else:
        lines += ["| ruling | sources | answer | conditions | by | date | evidence |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for ruling in rulings:
            covered = ", ".join(f"`{sid}`" for sid in ruling.get("sources") or [])
            lines.append(f"| {_cell(ruling.get('ruling_id'))} | {covered} | {_cell(ruling.get('answer'))} | "
                         f"{_cell(ruling.get('conditions'))} | {_cell(ruling.get('by'))} | {_cell(ruling.get('date'))} | "
                         f"{_cell(ruling.get('evidence'))} |")
    return "\n".join(lines) + "\n"
