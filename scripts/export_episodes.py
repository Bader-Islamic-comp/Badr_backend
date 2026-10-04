"""Write src/companion_api/rag/data/episodes.json from the Wave 1 source maps and their English labels.

    python scripts/export_episodes.py

The scene check (src/companion_api/rag/scene.py) reads which episode of a prophet's story an ayah belongs to
from this file: the source maps' ranges and Arabic episode labels (corpus/candidate/prophets/*_source_map.yaml)
and the English labels written for them (corpus/candidate/prophets/episode_labels_en.yaml). It holds ranges
and our own labels only, never corpus text. A test fails when the JSON is out of date.
"""
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "src/companion_api/rag/data/episodes.json"
MAPS = ROOT / "corpus/candidate/prophets"
_REF = re.compile(r"^quran:(\d+):(\d+)(?:-(\d+))?$")


class ExportError(ValueError):
    pass


def build(maps: Path = MAPS) -> dict:
    english = yaml.safe_load((maps / "episode_labels_en.yaml").read_text(encoding="utf-8"))["labels"]
    episodes, seen = [], set()
    for path in sorted(maps.glob("*_source_map.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for item in data["ranges"]:
            match = _REF.match(item["ref"])
            if not match:
                raise ExportError(f"{path.name}: unreadable range {item['ref']!r}")
            surah, first = int(match.group(1)), int(match.group(2))
            key = f"{data['prophet_id']} {item['ref']}"
            seen.add(key)
            if key not in english:
                raise ExportError(f"{key}: no English label in episode_labels_en.yaml")
            episodes.append({"prophet": data["prophet_id"], "ref": item["ref"], "surah": surah, "first": first,
                             "last": int(match.group(3) or first), "label_ar": item["topic"],
                             "label_en": english[key], "verification": item.get("verification", "")})
    unknown = sorted(set(english) - seen)
    if unknown:
        raise ExportError(f"English labels for ranges the source maps do not have: {', '.join(unknown)}")
    return {"schema_version": 1, "review_status": "draft",
            "source": "corpus/candidate/prophets/*_source_map.yaml + episode_labels_en.yaml",
            "episodes": episodes}


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    OUT.write_text(render(build()), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
