"""Quran text and tafsir: parse the downloaded files, verify structure, build canonical records.

`text_uthmani` and `text_simple` are copied byte for byte from the Tanzil files
(only the line ending is removed). `text_normalized` is a search-only view made
by the existing `norm-v1` normalizer and is never displayed.
"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from ..rag import normalize

EXPECTED_SURAHS = 114
EXPECTED_AYAT = 6236


class QuranError(ValueError):
    pass


def parse_tanzil(path: Path) -> tuple[dict[tuple[int, int], str], list[str]]:
    """({(surah, ayah): text}, notice lines) from a Tanzil `txt-2` file (`surah|ayah|text`)."""
    ayat: dict[tuple[int, int], str] = {}
    notice: list[str] = []
    text = Path(path).read_bytes().decode("utf-8-sig")
    for number, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        if not line.strip():
            continue
        if line.startswith("#"):
            notice.append(line)
            continue
        parts = line.split("|", 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit() or not parts[2]:
            raise QuranError(f"{path}: line {number} is not 'surah|ayah|text'")
        key = (int(parts[0]), int(parts[1]))
        if key in ayat:
            raise QuranError(f"{path}: {key[0]}:{key[1]} appears twice")
        ayat[key] = parts[2]
    return ayat, notice


def parse_tanzil_metadata(path: Path) -> dict[int, int]:
    root = ET.parse(path).getroot()
    return {int(sura.get("index")): int(sura.get("ayas")) for sura in root.iter("sura")}


def parse_qurancom_chapters(path: Path) -> dict[int, int]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {int(chapter["id"]): int(chapter["verses_count"]) for chapter in data["chapters"]}


def per_surah(ayat) -> dict[int, int]:
    counts: dict[int, int] = {}
    for surah, _ in ayat:
        counts[surah] = counts.get(surah, 0) + 1
    return counts


def verify(uthmani: dict, simple: dict, references: dict[str, dict[int, int]]) -> dict:
    """Structural checks; raises `QuranError` naming every failure."""
    problems = []
    counts = per_surah(uthmani)
    if len(counts) != EXPECTED_SURAHS:
        problems.append(f"{len(counts)} surahs, expected {EXPECTED_SURAHS}")
    if len(uthmani) != EXPECTED_AYAT:
        problems.append(f"{len(uthmani)} ayat, expected {EXPECTED_AYAT}")
    if set(uthmani) != set(simple):
        problems.append(f"uthmani and simple texts differ in ayah keys ({len(set(uthmani) ^ set(simple))} keys)")
    for surah, count in counts.items():
        if set(range(1, count + 1)) != {ayah for s, ayah in uthmani if s == surah}:
            problems.append(f"surah {surah}: ayah numbers are not 1..{count}")
    for name, reference in references.items():
        mismatched = sorted(s for s in set(reference) | set(counts) if reference.get(s) != counts.get(s))
        if mismatched:
            problems.append(f"per-surah counts differ from {name} for surahs {mismatched[:10]}")
    if problems:
        raise QuranError("Quran verification failed: " + "; ".join(problems))
    return {"surahs": len(counts), "ayat": len(uthmani), "per_surah_checked_against": sorted(references)}


def ayat_records(uthmani: dict, simple: dict, uthmani_id: str, simple_id: str) -> list[dict]:
    return [{"surah": surah, "ayah": ayah, "text_uthmani": uthmani[(surah, ayah)],
             "text_simple": simple[(surah, ayah)], "text_normalized": normalize.search_text(simple[(surah, ayah)]),
             "normalizer": normalize.VERSION, "source_id": uthmani_id, "text_simple_source_id": simple_id}
            for surah, ayah in sorted(uthmani)]


def parse_alquran_cloud(path: Path) -> dict[tuple[int, int], str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))["data"]
    entries: dict[tuple[int, int], str] = {}
    for surah in data["surahs"]:
        for ayah in surah["ayahs"]:
            key = (int(surah["number"]), int(ayah["numberInSurah"]))
            if key in entries:
                raise QuranError(f"{path}: tafsir for {key[0]}:{key[1]} appears twice")
            entries[key] = ayah["text"]
    return entries


def tafsir_records(tafsir: dict, quran_keys, source_id: str) -> tuple[list[dict], dict]:
    missing = sorted(set(quran_keys) - set(tafsir))
    extra = sorted(set(tafsir) - set(quran_keys))
    empty = sorted(key for key, text in tafsir.items() if not text.strip())
    if extra:
        raise QuranError(f"tafsir {source_id} has entries for {len(extra)} ayat that do not exist, e.g. {extra[:3]}")
    records = [{"surah": s, "ayah": a, "quran_ref": f"quran:{s}:{a}", "text": tafsir[(s, a)], "source_id": source_id}
               for s, a in sorted(tafsir) if tafsir[(s, a)].strip()]
    return records, {"records": len(records), "missing_ayat": len(missing), "empty": len(empty)}
