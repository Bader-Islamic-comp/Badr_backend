"""Is the Quran transmitted faithfully? The canonical Tanzil text against the King Fahd Complex text (Quranpedia).

The reference package asks for the Quranic text "in its rasm and the approved text" (the King Fahd Complex
print or quranpedia.net) and says to make sure the ayat are transmitted faithfully. This module compares two
texts ayah by ayah, word by word, and never changes either: the comparison works on a folded copy made here
(`kfc-compare-v1`) that is not stored or shown.

Two Quranpedia texts serve as references:
  quranpedia-mushaf-hafs-text  mushafs-2, the Complex's Uthmani Hafs text  <- compared with Tanzil Uthmani
  quranpedia-mushaf-hafs       mushafs-1, the print's standard spelling  <- compared with Tanzil Simple

Folds, applied to both texts, one whitespace-separated word at a time:

  Level 1, writing conventions of the two digital editions
    1. Unicode NFC (Quranpedia writes ي + hamza as two characters in places; Tanzil writes ئ).
    2. U+FEFF removed (a byte-order mark opens most ayat of mushafs-1).
    3. Tatweel U+0640 removed (Tanzil draws a superscript alef or a hamza on a tatweel: ـٰ ـٔ).
    4. Removed: harakat, tanween in every form (Tanzil ً ٌ ٍ; the Complex's open tanween ٖ ٗ ٞ), shadda,
       sukun in both forms (ْ and the Complex's ۡ U+06E1), maddah U+0653, the other combining vowel signs
       U+0656-U+065E, superscript alef U+0670, the Quranic annotation signs U+06D6-U+06ED (pause marks,
       small high letters, small waw and ya of the silah, rub el-hizb ۞, sajdah ۩, small meem of iqlab) and
       the open tanween of Arabic Extended-A U+08F0-U+08F3.
    5. Alef wasla ٱ (U+0671) -> alef ا.
    6. Alef maksura ى (U+0649) -> ya ي: Tanzil's Uthmani text encodes the undotted final ya of the print as
       ى; the Complex encodes it as ي and its font draws it undotted.
    7. A word left empty (a pause mark or a sign standing between spaces in Tanzil) is not a word.
  Level 2, the hamza (only when level 1 still differs)
    8. Unicode NFD, then the hamza signs ء (U+0621), U+0654, U+0655 and U+065F removed: أ إ آ become ا,
       ؤ becomes و, ئ becomes ي. The two editions seat or draw the hamza differently in places (Tanzil
       ٱلْـَٔاخِرَةِ, the Complex ٱلۡأٓخِرَةِ); the letters around it are compared exactly.

Statuses:
  identical                      the two strings are the same, character for character
  identical_after_normalization  the same words after level 1
  identical_except_hamza         the same words after level 2 (they differ only in how a hamza is written)
  basmala_prefixed               the first ayah of a surah starts, in our text only, with the surah's opening
                                 basmala (Tanzil writes it into ayah 1 of 112 surahs; the print sets it
                                 above the surah, unnumbered); the rest is identical after level 1 or 2
  differs                        a word is added, missing or different after level 2; `diffs` gives where

Each difference has a `kind`: basmala, hamza, word_division (the same letters divided into words differently,
such as لَّوْ مَا and لَّوۡمَا) or words (a word added, missing or different).

Word positions count the words left after level 1 (a stand-alone pause mark is not a word), from 1, in each
text as stored (for a basmala_prefixed ayah, the basmala is words 1-4 of ours).
"""
from dataclasses import dataclass, field
import difflib
import re
import unicodedata

VERSION = "kfc-compare-v1"
STATUSES = ("identical", "identical_after_normalization", "identical_except_hamza", "basmala_prefixed", "differs")
_MARKS = re.compile("[\u064b-\u0653\u0656-\u065e\u0670\u06d6-\u06ed\u08f0-\u08f3\u0640\ufeff]")
_HAMZA = re.compile("[\u0621\u0654\u0655\u065f]")
_GLYPHS = str.maketrans({"\u0671": "\u0627", "\u0649": "\u064a"})


def fold(word: str, level: int = 1) -> str:
    """One word's comparison form at level 1 or 2 (see the module docstring)."""
    word = unicodedata.normalize("NFD" if level >= 2 else "NFC", word)
    word = _MARKS.sub("", word)
    if level >= 2:
        word = _HAMZA.sub("", word)
    return word.translate(_GLYPHS)


def words(text: str, level: int = 1) -> list[tuple[str, str]]:
    """(word as written, folded word) for each word that is not empty once folded at level 1."""
    out = []
    for raw in text.split():
        if fold(raw, 1):
            out.append((raw, fold(raw, level)))
    return out


@dataclass
class Result:
    status: str
    basmala_prefix: bool = False
    diffs: list[dict] = field(default_factory=list)  # {"ours": [first, last], "theirs": [...], "*_words": [...]}

    def public(self) -> dict:
        """The result without any words of the texts (positions and status only), for reports kept in git."""
        return {"status": self.status, "basmala_prefix": self.basmala_prefix,
                "diffs": [{"ours": diff["ours"], "theirs": diff["theirs"], "kind": diff["kind"]}
                          for diff in self.diffs]}


def _span(start: int, end: int) -> list[int]:
    return [start + 1, end] if end > start else []


def _kind(ours: list[tuple[str, str]], theirs: list[tuple[str, str]]) -> str:
    """hamza (the same words at level 2), word_division (the same letters, divided into words differently) or
    words (a word added, missing or different)."""
    ours2, theirs2 = [fold(raw, 2) for raw, _ in ours], [fold(raw, 2) for raw, _ in theirs]
    if ours2 == theirs2:
        return "hamza"
    if ours2 and theirs2 and "".join(ours2) == "".join(theirs2):
        return "word_division"
    return "words"


def _diffs(ours: list[tuple[str, str]], theirs: list[tuple[str, str]], skip: int = 0) -> list[dict]:
    """Where the words differ; the first `skip` words of ours (the basmala) are one span of their own."""
    out = [{"ours": [1, skip], "theirs": [], "kind": "basmala", "ours_words": [raw for raw, _ in ours[:skip]],
            "theirs_words": []}] if skip else []
    matcher = difflib.SequenceMatcher(a=[w for _, w in ours[skip:]], b=[w for _, w in theirs], autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op != "equal":
            mine, other = ours[skip + i1:skip + i2], theirs[j1:j2]
            out.append({"ours": _span(skip + i1, skip + i2), "theirs": _span(j1, j2), "kind": _kind(mine, other),
                        "ours_words": [raw for raw, _ in mine], "theirs_words": [raw for raw, _ in other]})
    return out


def compare_ayah(ours: str, theirs: str, basmala: list[str] | None = None) -> Result:
    """Compare one ayah. `basmala`: the opening basmala's level-2 words, checked at the start of `ours` only."""
    if ours == theirs:
        return Result("identical")
    ours1, theirs1 = words(ours, 1), words(theirs, 1)
    ours2, theirs2 = words(ours, 2), words(theirs, 2)
    prefix = bool(basmala) and [w for _, w in ours2[:len(basmala)]] == basmala \
        and [w for _, w in theirs2[:len(basmala)]] != basmala
    skip = len(basmala) if prefix else 0
    if [w for _, w in ours1[skip:]] == [w for _, w in theirs1]:
        return Result("basmala_prefixed" if prefix else "identical_after_normalization", prefix,
                      _diffs(ours1, theirs1, skip))
    if [w for _, w in ours2[skip:]] == [w for _, w in theirs2]:
        return Result("basmala_prefixed" if prefix else "identical_except_hamza", prefix,
                      _diffs(ours1, theirs1, skip))
    return Result("differs", prefix, _diffs(ours2, theirs2, skip))


def compare(ours: dict[tuple[int, int], str], theirs: dict[tuple[int, int], str]) -> tuple[dict, dict]:
    """({(surah, ayah): Result}, summary) over every ayah of `ours`; ayat missing on one side are reported."""
    basmala = [w for _, w in words(ours.get((1, 1), ""), 2)] if (1, 1) in ours else None
    results = {}
    for key in sorted(set(ours) & set(theirs)):
        results[key] = compare_ayah(ours[key], theirs[key], basmala if key[1] == 1 and key[0] != 1 else None)
    counts = {status: 0 for status in STATUSES}
    for result in results.values():
        counts[result.status] += 1
    per_surah = lambda texts: {s: sum(1 for surah, _ in texts if surah == s) for s in sorted({s for s, _ in texts})}
    ours_counts, theirs_counts = per_surah(ours), per_surah(theirs)
    ref = lambda key: f"quran:{key[0]}:{key[1]}"
    summary = {
        "compare_version": VERSION, "ayat_compared": len(results), "statuses": counts,
        "surahs": len(theirs_counts), "ayat_in_reference": len(theirs),
        "per_surah_counts_match": ours_counts == theirs_counts,
        "per_surah_count_differences": {str(s): [ours_counts.get(s), theirs_counts.get(s)]
                                        for s in sorted(set(ours_counts) | set(theirs_counts))
                                        if ours_counts.get(s) != theirs_counts.get(s)},
        "missing_in_reference": [ref(key) for key in sorted(set(ours) - set(theirs))],
        "missing_in_ours": [ref(key) for key in sorted(set(theirs) - set(ours))],
        "basmala_prefixed_also_differs": [ref(key) for key, r in results.items()
                                          if r.basmala_prefix and r.status == "differs"],
        "identical_except_hamza_words": sum(len(r.diffs) for r in results.values()
                                            if r.status == "identical_except_hamza"),
        "differs": {ref(key): r.public()["diffs"] for key, r in results.items() if r.status == "differs"},
    }
    return results, summary
