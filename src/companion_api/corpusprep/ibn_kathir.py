"""Tafsir Ibn Kathir (Arabic): the spa5k/tafsir_api mirror of Tarteel QUL resource 22 (test/corpus-tasks).

One file per surah (`ibn-kathir-ar-001` ... `-114` in the registry), one record
per ayah. Ibn Kathir explains a passage at a time, so every ayah of a passage
carries the passage's whole text; consecutive ayat with identical text are one
**section** here (1,911 sections over 6,236 ayat). A section keeps its text
exactly as downloaded, including the editor's notes in [[double brackets]]
(manuscript variants and takhrij, such as "صحيح البخاري برقم (٤٦٨٨)"), which
the knowledge graph reads to link sections to hadith. `display_text` removes
those notes for the corpus documents; the canonical file keeps them.

The source is `candidate` (no licence stated for the text), so its documents
never enter a release (`governance.releases`); they serve the knowledge graph
and reviewers.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re

DATASET = "spa5k-tafsir-api"
SOURCE_PREFIX = "ibn-kathir-ar-"
_NOTE = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)
_SPACES = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n\s*\n")


class TafsirError(ValueError):
    pass


def source_id(surah: int) -> str:
    return f"{SOURCE_PREFIX}{surah:03d}"


def available(registry) -> bool:
    """Whether the registry holds all 114 Ibn Kathir sources (they are optional for the canonical build)."""
    ids = {source["source_id"] for source in registry.sources}
    return all(source_id(surah) in ids for surah in range(1, 115))


def parse_surah(path: Path, surah: int) -> dict[tuple[int, int], str]:
    """(surah, ayah) -> text for one downloaded file; refuses a record from another surah or a repeated ayah."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise TafsirError(f"{path}: expected a list of ayah records")
    out: dict[tuple[int, int], str] = {}
    for row in rows:
        try:
            key = (int(row["surah"]), int(row["ayah"]))
            text = row["text"]
        except (KeyError, TypeError, ValueError):
            raise TafsirError(f"{path}: a record lacks surah, ayah or text") from None
        if key[0] != surah:
            raise TafsirError(f"{path}: record for surah {key[0]} in the file for surah {surah}")
        if key in out:
            raise TafsirError(f"{path}: ayah {key[0]}:{key[1]} appears twice")
        if not isinstance(text, str):
            raise TafsirError(f"{path}: text of {key[0]}:{key[1]} is not a string")
        out[key] = text
    return out


@dataclass(frozen=True)
class Section:
    surah: int
    first: int
    last: int
    text: str

    @property
    def id(self) -> str:
        return f"ibn-kathir:{self.surah}:{self.first}" + (f"-{self.last}" if self.last != self.first else "")

    @property
    def quran_refs(self) -> list[str]:
        return [f"quran:{self.surah}:{ayah}" for ayah in range(self.first, self.last + 1)]


def sections(texts: dict[tuple[int, int], str], quran_keys) -> tuple[list[dict], dict]:
    """Canonical records, one per section, and a summary. Every Quran ayah must be covered exactly once."""
    quran_keys = set(quran_keys)
    extra = sorted(set(texts) - quran_keys)
    if extra:
        raise TafsirError(f"Ibn Kathir has records for ayat that do not exist, e.g. {extra[:3]}")
    missing = sorted(quran_keys - set(texts))
    built: list[Section] = []
    for surah, ayah in sorted(texts):
        text = texts[(surah, ayah)]
        previous = built[-1] if built else None
        if previous and previous.surah == surah and previous.last == ayah - 1 and previous.text == text:
            built[-1] = Section(surah, previous.first, ayah, text)
        else:
            built.append(Section(surah, ayah, ayah, text))
    records = [{"section_id": item.id, "surah": item.surah, "from_ayah": item.first, "to_ayah": item.last,
                "quran_refs": item.quran_refs, "text": item.text, "source_id": source_id(item.surah),
                "editor_notes": len(_NOTE.findall(item.text)), "words": len(item.text.split())}
               for item in built if item.text.strip()]
    summary = {"ayat": len(texts), "sections": len(records), "missing_ayat": len(missing),
               "empty_sections": sum(1 for item in built if not item.text.strip()),
               "words": sum(record["words"] for record in records),
               "longest_section_words": max((record["words"] for record in records), default=0),
               "editor_notes": sum(record["editor_notes"] for record in records)}
    return records, summary


def editor_notes(text: str) -> list[str]:
    """The editor's notes in [[double brackets]], in order."""
    return [note.strip() for note in _NOTE.findall(text)]


def display_text(text: str) -> str:
    """The section without the editor's notes, whitespace tidied, paragraphs kept."""
    cleaned = _NOTE.sub("", text)
    return "\n\n".join(" ".join(_SPACES.sub(" ", line).strip() for line in paragraph.splitlines() if line.strip())
                       for paragraph in _BLANK_LINES.split(cleaned) if paragraph.strip())


def paragraphs(text: str) -> list[str]:
    return [paragraph for paragraph in display_text(text).split("\n\n") if paragraph.strip()]
