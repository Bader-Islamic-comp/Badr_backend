"""The ayahs of a release one by one, and questions that quote an ayah with altered words (test/corpus-tasks-serving).

A Quran chunk holds several ayahs: the chunker joins its units with a blank line, and `source_refs` lists one
`quran:S:A` per unit. `AyahIndex` splits them back, so that

* the scene check (`scene.py`) can read the ayahs around the one an answer draws on, and
* a child who quotes an ayah with a changed, missing or added word gets the exact ayah, named by surah and
  ayah, instead of an answer built on the altered text (doc/conversation-policy.md §14; the organizers' test
  case 11).

The index holds the release's own text, built once per service; nothing is written anywhere.

Near-quote detection compares words, not letters. Both sides are read in search text (diacritics, hamza
seats and the Uthmani rasm folded, norm-v3) and then in a looser spelling form (`skeleton`) that also drops
alef and hamza and joins a vocative "يا" to its noun, so "يا أبت" matches the Uthmani "يابت" and a child's
spelling never counts as a change. A question is a near quote when a local alignment with one ayah matches
at least `MIN_MATCHED` words (`MIN_MATCHED_UNMARKED` when the question neither puts the words in quotation
marks nor says it quotes an ayah, so that retelling an ayah in a question is not taken for a quotation), at
least `MIN_CONTENT` of them content words, covering at least `MIN_COVER` of
the aligned part of the ayah and of the question, with at least one word changed, missing or added inside
the aligned part. An exact quote of any ayah, or of a part of one, is never corrected.
"""
from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from . import normalize
from .types import Chunk

AYAH_CONTENT_TYPES = frozenset({"quran", "quran_translation"})
MIN_MATCHED = 4      # aligned words that agree
MIN_CONTENT = 3      # of which content words (not particles, not قال or الله)
MIN_COVER = 0.6      # agreeing words over the aligned span, on each side
MAX_CANDIDATES = 60  # ayahs aligned per span, those sharing the most words first
MIN_MATCHED_UNMARKED = 7  # agreeing words when the question neither quotes nor says it cites an ayah
# Phrases with which a child says they are quoting: "قال تعالى", "قوله تعالى", "قال الله", "الآية", "the ayah".
_CUE = re.compile(r"\b(?:تعالي|قال الله|يقول الله|قول الله|الايه|ايات|الايات|سوره|القران|قران|ayah|ayat|verse|"
                  r"verses|surah|sura|quran|koran)\b")
_REF = re.compile(r"^quran:(\d+):(\d+)$")
_ARABIC = re.compile("[ء-ي]")
_QUOTED = re.compile('«([^»]+)»|"([^"]+)"|“([^”]+)”|‘([^’]+)’|﴿([^﴾]+)﴾|﴾([^﴿]+)﴿')
_SKELETON = str.maketrans("", "", "اء")  # alef and hamza
_WEAK = str.maketrans("", "", "يو")      # ya and waw, for the looser spelling match
_COMMON = normalize.STOPWORDS | {"قال", "قالوا", "الله"}
_YA = "يا"  # the vocative particle, written apart by a child and joined in the Uthmani text


@dataclass(frozen=True)
class Ayah:
    surah: int
    number: int
    chunk: Chunk                 # the release chunk that holds it, cited as its source
    text: str                    # canonical text, as displayed
    tokens: tuple[str, ...]      # search tokens (the simple spelling for Arabic Quran text)

    @property
    def key(self) -> tuple[str, str, str]:
        return _key(self.chunk)


@dataclass(frozen=True)
class NearQuote:
    """A question span that nearly matches an ayah: the ayah, and how many words agree and differ."""
    ayah: Ayah
    matched: int
    edits: int


def _key(chunk: Chunk) -> tuple[str, str, str]:
    """Ayahs are neighbours only within one text: one language, one content type, one work (translation)."""
    return chunk.language, chunk.content_type, chunk.source_label.split(" · ")[0]


def skeleton(token: str) -> str:
    return token.translate(_SKELETON) or token


def _same(left: str, right: str) -> bool:
    """Equal in the looser spelling: skeletons agree, or for longer words also without ya and waw."""
    if left == right:
        return True
    a, b = skeleton(left), skeleton(right)
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and a.translate(_WEAK) == b.translate(_WEAK)


def _join_vocative(tokens: Sequence[str]) -> list[str]:
    joined, skip = [], False
    for index, token in enumerate(tokens):
        if skip:
            skip = False
            continue
        if token == _YA and index + 1 < len(tokens):
            joined.append(_YA + tokens[index + 1])
            skip = True
        else:
            joined.append(token)
    return joined


def split_units(chunk: Chunk) -> list[tuple[int, int, str]] | None:
    """(surah, ayah, text) per unit of a Quran or translation chunk, or None when units and refs disagree."""
    refs = [ref for ref in chunk.source_refs if ref.startswith("quran:")] or list(chunk.references)
    parts = chunk.text.split("\n\n")
    if not refs or len(parts) != len(refs):
        return None
    units = []
    for ref, part in zip(refs, parts):
        match = _REF.match(ref)
        if not match:
            return None
        units.append((int(match.group(1)), int(match.group(2)), part.strip()))
    return units


def _align(question: Sequence[str], ayah: Sequence[str]) -> tuple[int, int, int, int, int, int]:
    """Smith-Waterman over words: (score, matched, edits, question span, ayah span, content matches)."""
    rows, cols = len(question) + 1, len(ayah) + 1
    # Each cell: (score, matched, edits, start_i, start_j, content)
    previous = [(0, 0, 0, 0, j, 0) for j in range(cols)]
    best = (0, 0, 0, 0, 0, 0)
    best_end = (0, 0)
    for i in range(1, rows):
        current = [(0, 0, 0, i, 0, 0)]
        for j in range(1, cols):
            same = _same(question[i - 1], ayah[j - 1])
            diagonal = previous[j - 1]
            if same:
                content = 1 if ayah[j - 1] not in _COMMON and len(ayah[j - 1]) > 1 else 0
                candidate = (diagonal[0] + 2, diagonal[1] + 1, diagonal[2], diagonal[3], diagonal[4],
                             diagonal[5] + content)
            else:
                candidate = (diagonal[0] - 1, diagonal[1], diagonal[2] + 1, diagonal[3], diagonal[4], diagonal[5])
            up, left = previous[j], current[j - 1]
            gap_up = (up[0] - 1, up[1], up[2] + 1, up[3], up[4], up[5])
            gap_left = (left[0] - 1, left[1], left[2] + 1, left[3], left[4], left[5])
            cell = max(candidate, gap_up, gap_left, key=lambda value: value[0])
            if cell[0] <= 0:
                cell = (0, 0, 0, i, j, 0)
            current.append(cell)
            if cell[0] > best[0]:
                best, best_end = cell, (i, j)
        previous = current
    score, matched, edits, start_i, start_j, content = best
    return score, matched, edits, best_end[0] - start_i, best_end[1] - start_j, content


class AyahIndex:
    """The ayahs of a release's Quran and translation chunks, by text and by (surah, ayah)."""

    def __init__(self, chunks: Iterable[Chunk]):
        self._ayahs: dict[tuple, Ayah] = {}
        self._by_chunk: dict[str, list[Ayah]] = {}
        self._postings: dict[str, set[tuple]] = {}
        for chunk in chunks:
            if chunk.content_type not in AYAH_CONTENT_TYPES or chunk.is_child or chunk.kind != "passage":
                continue
            units = split_units(chunk)
            if units is None:
                continue
            quranic = chunk.content_type == "quran"
            for surah, number, text in units:
                tokens = tuple(normalize.search_text(text, quranic=quranic).split())
                ayah = Ayah(surah, number, chunk, text, tokens)
                position = (*_key(chunk), surah, number)
                self._ayahs.setdefault(position, ayah)
                self._by_chunk.setdefault(chunk.id, []).append(ayah)
                if quranic:
                    for token in set(_join_vocative(tokens)):
                        if token not in _COMMON:
                            self._postings.setdefault(skeleton(token), set()).add(position)

    def __len__(self) -> int:
        return len(self._ayahs)

    def of_chunk(self, chunk: Chunk) -> list[Ayah]:
        return list(self._by_chunk.get(chunk.id, ()))

    def window(self, ayah: Ayah, width: int) -> list[Ayah]:
        """The ayah and up to `width` ayahs on each side in the same surah of the same text, where the release
        holds them."""
        found = []
        for number in range(ayah.number - width, ayah.number + width + 1):
            neighbour = self._ayahs.get((*ayah.key, ayah.surah, number))
            if neighbour is not None:
                found.append(neighbour)
        return found

    def near_quote(self, question: str) -> NearQuote | None:
        """The ayah a question quotes with altered words, or None (no quote, or an exact one)."""
        spans = [next(group for group in match.groups() if group) for match in _QUOTED.finditer(question)]
        spans = [span for span in spans if _ARABIC.search(span)]
        # Without quotation marks or a quoting phrase ("قال تعالى", "the ayah"), a question that retells an ayah
        # in its own words is no quotation: only a long run of the ayah's words counts then.
        least = MIN_MATCHED if spans or _CUE.search(normalize.search_text(question)) else MIN_MATCHED_UNMARKED
        best: NearQuote | None = None
        for span in spans or [question]:
            found = self._near_quote(_join_vocative(normalize.search_text(span).split()), least)
            if found is not None and (best is None or (found.matched, -found.edits) > (best.matched, -best.edits)):
                best = found
        return best

    def _near_quote(self, words: list[str], least: int = MIN_MATCHED) -> NearQuote | None:
        if len(words) < least or not self._postings:
            return None
        candidates: dict[tuple, int] = {}
        for word in set(words):
            for position in self._postings.get(skeleton(word), ()):
                candidates[position] = candidates.get(position, 0) + 1
        ranked = sorted((position for position, shared in candidates.items() if shared >= MIN_CONTENT),
                        key=lambda position: (-candidates[position], position))[:MAX_CANDIDATES]
        best, exact = None, 0
        for position in ranked:
            ayah = self._ayahs[position]
            _score, matched, edits, span_question, span_ayah, content = _align(words, _join_vocative(ayah.tokens))
            if matched < least or content < MIN_CONTENT:
                continue
            if matched < MIN_COVER * span_ayah or matched < MIN_COVER * span_question:
                continue
            if edits == 0:
                exact = max(exact, matched)
            elif best is None or (matched, -edits) > (best.matched, -best.edits):
                best = NearQuote(ayah, matched, edits)
        # The child quoted some ayah word for word at least as fully: nothing to correct.
        return None if best is None or exact >= best.matched else best


def surah_name(chunk: Chunk) -> str:
    """The surah's name as the release titles it ("سورة يوسف 12:14–20" -> "سورة يوسف"), else ""."""
    match = re.match(r"^(.*?\D)\s*\d+:\d+", chunk.title)
    return match.group(1).strip() if match else ""
