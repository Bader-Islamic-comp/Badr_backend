"""Hadith collections: parse the source files, cross-check two sources, build canonical records.

`arabic_text` is copied verbatim from the primary source. The cross-check
compares normalized text only to report agreement; it never edits, merges or
fills text from the second source, and every disagreement stays unresolved for
a person to review (corpus/reports/hadith_crosscheck.md).
"""
import csv
from dataclasses import dataclass, field
import json
from pathlib import Path

from ..rag import normalize

MATCH = 0.9       # Dice similarity of word trigrams at or above this: the texts agree
DIFFERS = 0.6     # between DIFFERS and MATCH: same hadith, wording differs; below: not matched
CONTAINED = 0.9   # share of the primary's trigrams found in one longer second-source entry, which
                  # groups several narrations (islamware does): same text, different granularity
_RARE_DF = 30     # a trigram in more documents than this (isnad phrases) does not propose candidates
_CANDIDATES = 8
_SPAN_WINDOW = 3  # a primary entry may be split over up to this many neighbours of its best secondary entry

# Comparison-only view (never stored or shown): norm-v1 tokens, a detached conjunction waw joined to the
# next word ("و حدثنا" = "وحدثنا"), and alef dropped so classical spellings compare equal ("اسحق" = "اسحاق").
# Measured on 50 sampled Muslim text_differs records: 44 were these two spelling conventions, not wording.
COMPARE_VERSION = "crosscheck-norm-v1"

SAHIH_COLLECTIONS = {"bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim"}
# The grading basis of the two Sahihs: the collection rule (doc/governance/source-policy.md, criterion 4) is the
# challenge's reference package's own hadith rule (corpus/sources/reference_package.yaml, row «الحديث النبوي»).
# Recorded in every record's `grader`; it changes no record's eligibility. Hadith outside the two Sahihs stay
# ungraded and ineligible until a grading from Dorar or an approved edition is in the data.
PACKAGE_HADITH_RULE = "reference package 20/3/1448, hadith: «الأحاديث الصحيحة من الصحيحين»"


def grader(collection: str) -> str | None:
    """Who or what grades a record of `collection` sahih, or None when nothing does."""
    if collection not in SAHIH_COLLECTIONS:
        return None
    return f"collection rule: {SAHIH_COLLECTIONS[collection]}; {PACKAGE_HADITH_RULE}"


NUMBERING = {"fawazahmed0": "sunnah.com", "ahmedbaset": "sunnah.com", "mhashim6": "islamware"}


@dataclass
class Entry:
    number: str
    text: str
    narrator: str | None = None


@dataclass
class Parsed:
    entries: list[Entry]
    empty_numbers: list[str] = field(default_factory=list)


def _number(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def parse_fawazahmed0(path: Path) -> Parsed:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    parsed = Parsed([])
    for item in data["hadiths"]:
        number = _number(item["hadithnumber"])
        if item["text"].strip():
            parsed.entries.append(Entry(number, item["text"]))
        else:
            parsed.empty_numbers.append(number)
    return parsed


def parse_ahmedbaset(path: Path) -> Parsed:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    parsed = Parsed([])
    for item in data["hadiths"]:
        number = str(int(item["idInBook"]))
        narrator = ((item.get("english") or {}).get("narrator") or "").strip() or None
        if (item.get("arabic") or "").strip():
            parsed.entries.append(Entry(number, item["arabic"], narrator))
        else:
            parsed.empty_numbers.append(number)
    return parsed


def parse_mhashim6(path: Path) -> Parsed:
    parsed = Parsed([])
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) != 2:
                raise ValueError(f"{path}: expected two columns, found {len(row)}")
            number, text = row[0].strip(), row[1]
            (parsed.entries.append(Entry(number, text)) if text.strip() else parsed.empty_numbers.append(number))
    return parsed


def compare_tokens(text: str) -> list[str]:
    words: list[str] = []
    for word in normalize.tokens(text):
        if words and words[-1] == "\u0648":
            words[-1] += word
        else:
            words.append(word)
    return [word.replace("\u0627", "") or word for word in words]


def shingles(text: str) -> set:
    words = compare_tokens(text)
    if len(words) < 3:
        return set(words)
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def dice(a: set, b: set) -> float:
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def containment(a: set, b: set) -> float:
    """Share of `a` found in `b`."""
    return len(a & b) / len(a) if a else 0.0


def status_for(match: tuple | None) -> str:
    if match is None:
        return "not_matched"
    _, similarity, contained = match
    if similarity >= MATCH:
        return "match"
    if contained >= CONTAINED:
        return "contained_in_secondary"
    return "text_differs" if max(similarity, contained) >= DIFFERS else "not_matched"


def _compare(entry: Entry, other: Entry, mine: set | None = None, theirs: set | None = None) -> tuple:
    mine = shingles(entry.text) if mine is None else mine
    theirs = shingles(other.text) if theirs is None else theirs
    return other.number, dice(mine, theirs), containment(mine, theirs)


def crosscheck_by_number(primary: list[Entry], secondary: list[Entry]) -> dict[str, tuple | None]:
    """Same numbering system: compare the entry with the same number."""
    by_number = {entry.number: entry for entry in secondary}
    return {entry.number: _compare(entry, by_number[entry.number]) if entry.number in by_number else None
            for entry in primary}


def crosscheck_by_text(primary: list[Entry], secondary: list[Entry], progress=None) -> dict[str, tuple | None]:
    """Different numbering systems: find each primary entry's most similar secondary entry."""
    grams = [shingles(entry.text) for entry in secondary]
    positions = {entry.number: position for position, entry in enumerate(secondary)}
    index: dict = {}
    for position, gram_set in enumerate(grams):
        for gram in gram_set:
            index.setdefault(gram, []).append(position)
    result = {}
    for count, entry in enumerate(primary, 1):
        mine = shingles(entry.text)
        votes: dict[int, int] = {}
        for gram in mine:
            postings = index.get(gram)
            if postings and len(postings) <= _RARE_DF:
                for position in postings:
                    votes[position] = votes.get(position, 0) + 1
        compared = [_compare(entry, secondary[position], mine, grams[position])
                    for position in sorted(votes, key=lambda p: (-votes[p], p))[:_CANDIDATES]]  # ties by position: runs repeat
        best = max(compared, key=lambda match: match[1], default=None)
        if best is not None and best[1] < MATCH:
            # A primary entry can sit inside a longer second-source entry; prefer that entry if it holds it all.
            holder = max(compared, key=lambda match: match[2])
            if holder[2] >= CONTAINED:
                best = holder
            else:
                best = _span(mine, best, holder, secondary, grams, positions)
        result[entry.number] = best
        if progress and count % 1000 == 0:
            progress(count, len(primary))
    return result


def _span(mine: set, best: tuple, holder: tuple, secondary: list[Entry], grams: list[set],
          positions: dict) -> tuple:
    """Tries consecutive secondary entries around the best one; returns a `first-last` span if they hold it."""
    centre = positions[holder[0]]
    top = (holder[2], centre, centre)
    for low in range(max(0, centre - _SPAN_WINDOW), centre + 1):
        union: set = set()
        for high in range(low, min(len(grams), centre + _SPAN_WINDOW + 1)):
            union |= grams[high]
            if high >= centre and high > low:
                share = containment(mine, union)
                if share > top[0]:
                    top = (share, low, high)
    share, low, high = top
    while low < high and not mine & grams[low]:  # drop neighbours that add nothing
        low += 1
    while high > low and not mine & grams[high]:
        high -= 1
    if share >= CONTAINED and low != high:
        return f"{secondary[low].number}-{secondary[high].number}", best[1], share
    return best


def records(collection: str, primary: Parsed, primary_id: str, secondary_id: str | None,
            matches: dict | None, candidate_ids: set[str]) -> list[dict]:
    """Canonical records for one collection. `candidate_ids` are sources whose licence is unclear."""
    dataset = primary_id.split("-", 1)[0]
    rows = []
    for entry in primary.entries:
        match = matches.get(entry.number) if matches is not None else None
        if secondary_id is None:
            status = "single_source"
        else:
            status = status_for(match)
        sahih = collection in SAHIH_COLLECTIONS
        reasons = []
        if not sahih:
            reasons.append("no_grading_in_source")
        if primary_id in candidate_ids:
            reasons.append("primary_source_licence_unclear")
        if status in ("text_differs", "not_matched"):
            reasons.append("crosscheck_unresolved")
        rows.append({
            "collection": collection, "number": entry.number, "numbering_system": NUMBERING[dataset],
            "narrator": entry.narrator, "arabic_text": entry.text,
            "grading": "sahih" if sahih else None,
            "grader": grader(collection),
            "source_ids": [primary_id] + ([secondary_id] if secondary_id and match else []),
            "crosscheck_status": status,
            "crosscheck": ({"source_id": secondary_id, "number": match[0], "similarity": round(match[1], 3),
                            "containment": round(match[2], 3)} if match else None),
            "eligible": not reasons, "ineligible_reasons": reasons, "review_status": "draft",
        })
    return rows


def summary(collection: str, primary: Parsed, secondary: Parsed | None, rows: list[dict]) -> dict:
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row["crosscheck_status"]] = statuses.get(row["crosscheck_status"], 0) + 1
    matched_secondary = [row["crosscheck"]["number"] for row in rows
                         if row["crosscheck"] and row["crosscheck_status"] != "not_matched"]
    reused = len(matched_secondary) - len(set(matched_secondary))
    return {
        "collection": collection, "records": len(rows), "primary_empty_text": len(primary.empty_numbers),
        "primary_empty_numbers": primary.empty_numbers,
        "secondary_entries": len(secondary.entries) if secondary else None,
        "secondary_unmatched": (len({e.number for e in secondary.entries} - set(matched_secondary))
                                if secondary else None),
        "secondary_matched_more_than_once": reused if secondary else None,
        "statuses": statuses, "eligible": sum(row["eligible"] for row in rows),
    }
