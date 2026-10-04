"""Write src/companion_api/rag/data/query_aliases.json from corpus/aliases.yaml and corpus/glossary_cross_lingual.yaml.

    python scripts/export_query_aliases.py

The server rewrites an Arabizi question into Arabic search terms with this file (rag/arabizi.py); it holds names,
spellings and glossary words only, never corpus text. A test fails when the JSON is out of date.
"""
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from companion_api.rag import normalize  # noqa: E402

OUT = ROOT / "src/companion_api/rag/data/query_aliases.json"

# Glossary schema 2 (reference package task, 2026-10-02): the header of corpus/glossary_cross_lingual.yaml
# describes each field. Only `ar` and `latin` reach the JSON; the rest is provenance for reviewers.
GLOSSARY_SCHEMA = 2
FIELDS = ("ar", "latin", "origin", "sensitive", "query", "jamharah", "en", "usage_rule", "provenance")
ORIGINS = ("glossary", "package_page_7")
PROVENANCE = ("package_page_7", "jamharah", "model_proposed")
SENSES = ("differs", "unclear")  # a title match whose meaning differs, or needs a reviewer (model_proposed)


class GlossaryError(ValueError):
    pass


def check_glossary(glossary: dict) -> list[str]:
    """Every problem in the glossary, as `term: field: message`."""
    if not isinstance(glossary, dict) or glossary.get("schema_version") != GLOSSARY_SCHEMA:
        return [f"glossary: schema_version must be {GLOSSARY_SCHEMA}"]
    problems, seen = [], set()
    for position, term in enumerate(glossary.get("terms") or [], 1):
        name = term.get("ar") if isinstance(term, dict) and term.get("ar") else f"terms[{position}]"
        if not isinstance(term, dict):
            problems.append(f"{name}: must be a mapping")
            continue
        if name in seen:
            problems.append(f"{name}: listed twice")
        seen.add(name)
        problems += [f"{name}: {key}: unknown field" for key in term if key not in FIELDS]
        if not isinstance(term.get("latin"), list) or not term["latin"]:
            problems.append(f"{name}: latin: must be a non-empty list")
        origin = term.get("origin", "glossary")
        if origin not in ORIGINS:
            problems.append(f"{name}: origin: must be one of {', '.join(ORIGINS)}")
        match = term.get("jamharah")
        if match is not None and match != "unmatched" and not (
                isinstance(match, dict) and isinstance(match.get("id"), int) and str(match.get("url", "")).startswith(
                    "https://islamic-content.com/dictionary/word/") and set(match) <= {"id", "url", "en", "sense"}
                and match.get("sense", "differs") in SENSES):
            problems.append(f"{name}: jamharah: must be `unmatched` or {{id, url, en?, sense?}} with sense "
                            f"{' or '.join(SENSES)}")
        if origin == "package_page_7":
            for key in ("en", "usage_rule", "provenance"):
                if not term.get(key):
                    problems.append(f"{name}: {key}: is required for a page-7 term")
        for key, value in (term.get("provenance") or {}).items():
            if key not in FIELDS or value not in PROVENANCE:
                problems.append(f"{name}: provenance: {key}: must name a field and one of {', '.join(PROVENANCE)}")
    return problems


def _latin(word: str) -> str:
    return " ".join(normalize.search_text(word).split())


def build(aliases_path: Path = ROOT / "corpus/aliases.yaml",
          glossary_path: Path = ROOT / "corpus/glossary_cross_lingual.yaml") -> dict:
    aliases = yaml.safe_load(aliases_path.read_text(encoding="utf-8"))
    glossary = yaml.safe_load(glossary_path.read_text(encoding="utf-8"))
    problems = check_glossary(glossary)
    if problems:
        raise GlossaryError(f"{glossary_path.name} is invalid: " + "; ".join(problems))
    prophets = []
    for prophet in aliases["prophets"]:
        arabic = [normalize.search_text(entry["alias"]) for entry in prophet.get("names_ar") or []]
        latin = sorted({_latin(word) for word in (prophet.get("latin") or []) + (prophet.get("arabizi") or [])})
        if arabic and latin:
            prophets.append({"id": prophet["id"], "ar": arabic[0], "latin": latin})
    terms = [{"ar": normalize.search_text(term["ar"]), "latin": sorted({_latin(word) for word in term["latin"]})}
             for term in glossary["terms"]]
    return {"schema_version": 1, "source": "corpus/aliases.yaml + corpus/glossary_cross_lingual.yaml",
            "review_status": "draft", "prophets": prophets, "terms": terms}


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    OUT.write_text(render(build()), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
