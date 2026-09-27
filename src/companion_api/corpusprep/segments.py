"""Quran segments for chunking: Tanzil's ruku divisions, split into runs of 1-8 whole ayat.

Ruku boundaries come from Tanzil metadata (quran-data.xml), so the thematic
division is sourced, not invented. A ruku longer than 8 ayat or than the word
budget is split into the fewest near-equal runs that satisfy both. An ayah is
never split: one ayah over the budget is a segment on its own.
"""
from dataclasses import dataclass
from math import ceil
from pathlib import Path
import xml.etree.ElementTree as ET

MAX_AYAT = 8


@dataclass(frozen=True)
class Segment:
    surah: int
    first: int
    last: int

    @property
    def id(self) -> str:
        return f"quran-{self.surah:03d}-{self.first:03d}-{self.last:03d}"

    @property
    def ref(self) -> str:
        return f"quran:{self.surah}:{self.first}" + (f"-{self.last}" if self.last != self.first else "")


def load_metadata(path: Path) -> tuple[dict[int, str], list[tuple[int, int]]]:
    """({surah: Arabic name}, [(surah, first ayah of each ruku)])."""
    root = ET.parse(path).getroot()
    names = {int(sura.get("index")): sura.get("name") for sura in root.iter("sura")}
    rukus = [(int(ruku.get("sura")), int(ruku.get("aya"))) for ruku in root.iter("ruku")]
    return names, rukus


def _split(ayat: list[int], words: dict[int, int], budget: int) -> list[list[int]]:
    parts = max(1, ceil(len(ayat) / MAX_AYAT))
    while True:
        size = ceil(len(ayat) / parts)
        runs = [ayat[i:i + size] for i in range(0, len(ayat), size)]
        if all(len(run) == 1 or sum(words[a] for a in run) <= budget for run in runs):
            return runs
        parts += 1


def segment(ayah_counts: dict[int, int], rukus: list[tuple[int, int]], words: dict[tuple[int, int], int],
            budget: int = 180) -> list[Segment]:
    starts: dict[int, list[int]] = {}
    for surah, ayah in rukus:
        starts.setdefault(surah, []).append(ayah)
    segments = []
    for surah, count in sorted(ayah_counts.items()):
        bounds = sorted(set(starts.get(surah, [1])) | {1})
        for position, first in enumerate(bounds):
            last = bounds[position + 1] - 1 if position + 1 < len(bounds) else count
            ayat = list(range(first, last + 1))
            for run in _split(ayat, {a: words[(surah, a)] for a in ayat}, budget):
                segments.append(Segment(surah, run[0], run[-1]))
    return segments


def verify_cover(segments: list[Segment], ayah_counts: dict[int, int]) -> None:
    """Every ayah is in exactly one segment of 1-8 ayat."""
    seen = set()
    for item in segments:
        if not 1 <= item.last - item.first + 1 <= MAX_AYAT:
            raise ValueError(f"segment {item.id} has more than {MAX_AYAT} ayat")
        for ayah in range(item.first, item.last + 1):
            if (item.surah, ayah) in seen:
                raise ValueError(f"ayah {item.surah}:{ayah} is in two segments")
            seen.add((item.surah, ayah))
    expected = {(surah, ayah) for surah, count in ayah_counts.items() for ayah in range(1, count + 1)}
    if seen != expected:
        raise ValueError(f"{len(expected - seen)} ayat are not in any segment")
