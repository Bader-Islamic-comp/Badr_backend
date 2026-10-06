"""The duas of the Learn page: the `adhkar` and `daily_duas` items of `corpus/competition-ar/content.json`.

Every item is a draft (the package's own `review_status`). Practice segments are offered only for a
`hadith_invocation` item, and only when their word counts equal the service's `/v1/duas`, segment by segment.
They are cut at the same clause breaks as Dua-a_stt's `scripts/export_duas_from_backend.py` (`_split_clauses` on
«،» «؛» and «ثم:») and merged in order up to 12 words, but the two splits are not the same: the export counts words
after its `text_imlai`, which also spells numbers out ("33" becomes «ثلاث وثلاثون»), while this module counts the
display text. Where they differ the item has no segments, and that is the safe answer, not a gap to close:
`after-prayer-tasbih` reads «سبحان الله 33 مرة، …», and "33 مرة" is how many times to say it, not words a child
recites, so a segment holding it would score the child on words they should not say.
Anything else, including every Quranic item, has no segments: its text is not served here.

The file is read directly as JSON (no corpus pipeline import: this module is on the child's request path).
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata

CONTENT = Path(__file__).resolve().parents[3] / "corpus" / "competition-ar" / "content.json"
GROUPS = ("adhkar", "daily_duas")
# Dua-a_stt scripts/export_duas_from_backend.py: the clause breaks of `_split_clauses` and the merge limit of
# `_split_and_normalize(max_words=12)`, which the export applies to its normalized words (see the docstring).
CLAUSE_BREAK = re.compile(r"[،؛]\s*|(?:ثم:\s*)")
MAX_WORDS = 12
# Words of the display text: marks removed, split on anything that is not a word character. Digits stay one word
# here, where the speech service's export spells them out.
_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_NON_WORD = re.compile(r"[^\w]+")


def split_clauses(text: str) -> list[str]:
    """The export script's `_split_clauses`, unchanged: split at «،» «؛» «ثم:», strip, drop empty clauses."""
    clauses = CLAUSE_BREAK.split(text)
    return [clause.strip().rstrip("،؛,.") for clause in clauses if clause.strip()]


def _clause_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, clause) for each clause `split_clauses` keeps, in order; `end` excludes its separator."""
    spans, start = [], 0
    for match in [*CLAUSE_BREAK.finditer(text), None]:
        end = match.start() if match else len(text)
        raw = text[start:end]
        if raw.strip():
            spans.append((start, end, raw.strip().rstrip("،؛,.")))
        if match:
            start = match.end()
    return spans


def word_count(text: str) -> int:
    folded = _MARKS.sub("", unicodedata.normalize("NFKC", text))
    return len(_NON_WORD.sub(" ", folded).replace("_", " ").split())


def segments(text: str, max_words: int = MAX_WORDS) -> list[tuple[str, int]]:
    """(display text, word count) per segment: clauses merged in order while they fit in `max_words`."""
    groups: list[list[tuple[int, int, str]]] = []
    current: list[tuple[int, int, str]] = []
    for span in _clause_spans(text):
        words = word_count(span[2])
        if not words:
            continue  # the export drops a clause that normalizes to nothing
        if current and sum(word_count(clause) for _s, _e, clause in current) + words > max_words:
            groups.append(current)
            current = [span]
        else:
            current.append(span)
    if current:
        groups.append(current)
    return [(text[group[0][0]:group[-1][1]].strip().rstrip("،؛,."), sum(word_count(c) for _s, _e, c in group))
            for group in groups]


@dataclass(frozen=True)
class Dua:
    id: str
    group: str
    kind: str
    title: str
    child_note: str
    repeat: int
    occasions: tuple[str, ...]
    review_status: str
    text: str            # the display text, which is the invocation itself for a hadith_invocation item

    def verified_segments(self, counts: list[int] | None) -> list[str]:
        """The practice segments, when their word counts are the speech service's exactly; else none (fail safe)."""
        if self.kind != "hadith_invocation" or not counts:
            return []
        found = segments(self.text)
        return [text for text, _words in found] if [words for _text, words in found] == counts else []


class DuaCatalogue:
    def __init__(self, path: Path = CONTENT):
        self.path = path
        self._items: dict[str, Dua] | None = None
        self.status = "draft"

    def _load(self) -> dict[str, Dua]:
        if self._items is None:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            items = {}
            for group in GROUPS:
                for row in content.get(group, []):
                    items[row["id"]] = Dua(
                        id=row["id"], group=group, kind=row.get("kind", "hadith_invocation"), title=row["display"],
                        child_note=row.get("child_note", ""), repeat=int(row.get("repeat", 1)),
                        occasions=tuple(row.get("occasions") or [row["occasion"]]),
                        review_status=row.get("review_status", "draft"), text=row["display"])
            approved = content.get("status") == "approved" and all(
                dua.review_status == "approved" for dua in items.values())
            self.status = "approved" if approved else "draft"
            self._items = items
        return self._items

    def items(self) -> list[Dua]:
        return list(self._load().values())

    def get(self, dua_id: str) -> Dua | None:
        return self._load().get(dua_id)
