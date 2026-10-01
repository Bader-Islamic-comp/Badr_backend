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


def _latin(word: str) -> str:
    return " ".join(normalize.search_text(word).split())


def build(aliases_path: Path = ROOT / "corpus/aliases.yaml",
          glossary_path: Path = ROOT / "corpus/glossary_cross_lingual.yaml") -> dict:
    aliases = yaml.safe_load(aliases_path.read_text(encoding="utf-8"))
    glossary = yaml.safe_load(glossary_path.read_text(encoding="utf-8"))
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
