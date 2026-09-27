"""Age-band drafts (tier 2): templates and the automatic reading-level checker (corpus tasks Phase 3).

Children's text is human-written and human-reviewed. This module only creates
empty templates from the checked source maps and hadith selection, and checks
what people write: words per version, sentence length, source references, and
that no Quran or hadith text is typed into the child's text (sacred text is
shown by reference, with a `[[quote:<ref>]]` marker the server fills in).
"""
from collections import Counter
import json
from pathlib import Path
import re

import jsonschema

from .hadith import compare_tokens

BANDS = ("7-9", "10-11")
# doc/plan.md style rules (prompt 1 and 2B), aligned to the code's age bands.
WORDS = {"story_scene": {"7-9": (80, 150), "10-11": (150, 300)},
         "hadith_explanation": {"7-9": (30, 60), "10-11": (60, 120)}}
MAX_SENTENCE_WORDS = {"7-9": 14, "10-11": 21}  # "fewer than 15" / "fewer than 22"
SACRED_NGRAM = 5
FORMULAIC_DF = 50  # a 5-gram in more hadith than this is formula ("قال رسول الله صلى الله ..."), not a quote
MARKER = re.compile(r"\[\[quote:([^\]]+)\]\]")
SENTENCE_END = re.compile(r"[.!؟?]+|\n+")
HONORIFIC = "عليه السلام"
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "corpus/drafts/age_band/schema.json"


def _grams(words: list[str]) -> list[tuple]:
    return [tuple(words[i:i + SACRED_NGRAM]) for i in range(len(words) - SACRED_NGRAM + 1)]


class SacredIndex:
    """Hashed 5-grams of every ayah and hadith, minus formulaic ones, to catch typed sacred text."""

    def __init__(self, quran_texts, hadith_texts):
        self.grams: set[int] = set()
        for text in quran_texts:
            self.grams.update(hash(gram) for gram in _grams(compare_tokens(text)))
        frequency: Counter = Counter()
        for text in hadith_texts:
            frequency.update({hash(gram) for gram in _grams(compare_tokens(text))})
        self.grams.update(gram for gram, count in frequency.items() if count <= FORMULAIC_DF)

    def overlaps(self, text: str) -> list[int]:
        """Word positions in `text` where a sacred 5-gram starts (positions only, never the text)."""
        return [position for position, gram in enumerate(_grams(compare_tokens(text))) if hash(gram) in self.grams]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_END.split(text) if part.strip()]


def check_version(version: dict, kind: str, band: str, refs: list[str], index: SacredIndex,
                  prophet_name: str | None) -> dict:
    text = version["text"]
    errors, warnings = [], []
    if not text.strip():
        return {"status": "empty"}
    markers = MARKER.findall(text)
    bare = MARKER.sub(" ", text)
    words = len(bare.split())
    low, high = WORDS[kind][band]
    if not low <= words <= high:
        errors.append(f"word_count {words} outside {low}-{high} for {band}")
    longest = max((len(sentence.split()) for sentence in _sentences(bare)), default=0)
    if longest > MAX_SENTENCE_WORDS[band]:
        errors.append(f"a sentence has {longest} words; the limit for {band} is {MAX_SENTENCE_WORDS[band]}")
    for ref in markers:
        if ref not in refs:
            errors.append(f"quote marker {ref} is not one of this draft's source_refs")
    overlaps = index.overlaps(bare)
    if overlaps:
        errors.append(f"{len(overlaps)} five-word runs match Quran or hadith text (word positions "
                      f"{overlaps[:5]}); quote by reference with [[quote:<ref>]] instead")
    if kind == "story_scene" and prophet_name:
        name = compare_tokens(prophet_name)[0]
        tokens = compare_tokens(bare)
        first = next((i for i, token in enumerate(tokens) if token.endswith(name)), None)
        if first is not None and tokens[first + 1:first + 3] != compare_tokens(HONORIFIC):
            warnings.append("first mention of the prophet is not followed by عليه السلام")
    if version["author"] and version["reviewer"] and version["author"] == version["reviewer"]:
        errors.append("author and reviewer are the same person")
    if version["review_status"] == "approved" and not version["reviewer"]:
        errors.append("approved without a reviewer")
    if not version["lesson"].strip():
        warnings.append("lesson is empty")
    return {"status": "fail" if errors else "pass", "words": words, "longest_sentence": longest,
            "quote_markers": len(markers), "sacred_overlaps": len(overlaps), "errors": errors,
            "warnings": warnings}


def check_file(data: dict, index: SacredIndex, names: dict[str, str], schema: dict) -> list[str]:
    """Validates one draft against the schema and writes `reading_level_checks`; returns error lines."""
    problems = [f"schema: {error.message}" for error in jsonschema.Draft202012Validator(schema).iter_errors(data)]
    if problems:
        return problems
    for band in BANDS:
        version = data["versions"][band]
        result = check_version(version, data["kind"], band, data["source_refs"], index,
                               names.get(data["prophet_id"] or ""))
        version["reading_level_checks"] = result
        if version["review_status"] != "empty" and result["status"] == "empty":
            problems.append(f"{band}: review_status is {version['review_status']} but the text is empty")
        if version["review_status"] == "empty" and result["status"] != "empty":
            problems.append(f"{band}: text is written but review_status is still empty (set draft)")
        problems += [f"{band}: {error}" for error in result.get("errors", [])]
    return problems


def _empty_version() -> dict:
    return {"text": "", "lesson": "", "author": None, "reviewer": None, "review_status": "empty",
            "reading_level_checks": None}


def templates(source_maps: list[dict], selection: dict) -> list[dict]:
    out = []
    for data in source_maps:
        for number, item in enumerate(data["ranges"], 1):
            out.append({"schema_version": 1, "id": f"story-{data['prophet_id']}-s{number:02d}", "kind": "story_scene",
                        "prophet_id": data["prophet_id"], "title": item["topic"], "source_refs": [item["ref"]],
                        "source_status": item["verification"], "cluster_id": None, "disputed": False,
                        "excluded_details": [], "reviewer_notes": "",
                        "versions": {band: _empty_version() for band in BANDS}})
    for item in selection["hadith"]:
        ref = item["cluster_primary"]
        collection, number = ref.split(":", 1)
        refs = [ref] + ([f"nawawi40:{item['number']}"] if item["collection"] == "nawawi40" else [])
        out.append({"schema_version": 1, "id": f"hadith-{collection}-{number.replace('.', '-')}",
                    "kind": "hadith_explanation", "prophet_id": None, "title": item["topic"], "source_refs": refs,
                    "source_status": "needs_check" if item["needs_check"] else "ok", "cluster_id": item["cluster_id"],
                    "disputed": False, "excluded_details": [], "reviewer_notes": "",
                    "versions": {band: _empty_version() for band in BANDS}})
    return out


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
