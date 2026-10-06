"""What of Robert's answer is spoken (ADR 0006, owner decision D-C).

Only Robert's own Arabic sentences. Quran, hadith and duas are never generated as speech, so:
- A sentence holding a quoted span (the quote characters of `rag/checks.py`: «…», "…", “…”, ‘…’, ﴿…﴾) is
  dropped whole, and so is every sentence inside the span: without its quotation it would no longer say what
  Robert wrote. A quote mark left unmatched means nothing can be told apart safely, so nothing is spoken.
- Citation markers (`[1]`) and anything inside them are removed, and so is a parenthesis holding a reference
  ("(البقرة: 255)"); a trailing sources list (a line opening with «المصادر», «المراجع», "Sources", "References")
  is cut with everything after it.
- A sentence with a Latin letter is dropped (the voice is Arabic only), and so is one without an Arabic letter.
The rest is split into sentences, long ones at «،» «؛» or spaces, and merged in order into parts of at most
`MAX_PART_CHARS` characters; at most `MAX_PARTS` parts are spoken.
"""
import re

MAX_PART_CHARS = 140
MAX_PARTS = 6
# The same quotation pattern as rag/checks.py `_QUOTE` and rag/grounding.py `_QUOTES` (a test holds them equal).
QUOTES = re.compile('«([^»]+)»|"([^"]+)"|“([^”]+)”|‘([^’]+)’|﴿([^﴾]+)﴾|﴾([^﴿]+)﴿')
QUOTE_MARKS = re.compile('[«»"“”‘’﴾﴿]')
CITATION = re.compile(r"\[[^\[\]]*\]")
REFERENCE = re.compile(r"\([^()]*[0-9٠-٩:][^()]*\)")
SOURCES_LIST = re.compile(r"(?im)^\s*(?:المصادر|المراجع|المصدر|sources?|references?)\s*[:：]")
SENTENCE = re.compile(r"[^.!?؟…\n]+[.!?؟…]*")
LATIN = re.compile("[A-Za-z]")
ARABIC = re.compile("[\u0621-\u064a]")
_BREAKS = re.compile(r"(?<=[،؛,;])\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([.!?؟…،؛,;:])")


_QUOTED = "\x00"  # stands for a removed quotation, so the sentence that held it is dropped too


def _sentences(text: str) -> list[str]:
    match = SOURCES_LIST.search(text)
    if match:
        text = text[:match.start()]
    text = QUOTES.sub(_QUOTED, text.replace(_QUOTED, " "))
    if QUOTE_MARKS.search(text):
        return []
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", REFERENCE.sub(" ", CITATION.sub(" ", text)))
    kept = []
    for raw in SENTENCE.findall(text):
        sentence = " ".join(raw.split())
        if not sentence or _QUOTED in sentence:
            continue
        if LATIN.search(sentence) or not ARABIC.search(sentence):
            continue
        kept.append(sentence)
    return kept


def _pieces(sentence: str, limit: int) -> list[str]:
    """A sentence in pieces of at most `limit` characters, cut at «،» «؛» first, then at spaces."""
    if len(sentence) <= limit:
        return [sentence]
    pieces = []
    for clause in _BREAKS.split(sentence):
        while len(clause) > limit:
            cut = clause.rfind(" ", 0, limit + 1)
            cut = cut if cut > 0 else limit
            pieces.append(clause[:cut].strip())
            clause = clause[cut:].strip()
        if clause:
            pieces.append(clause)
    return _merge(pieces, limit)


def _merge(pieces: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    for piece in pieces:
        if merged and len(merged[-1]) + 1 + len(piece) <= limit:
            merged[-1] += " " + piece
        else:
            merged.append(piece)
    return merged


def speakable_parts(text: str, max_chars: int = MAX_PART_CHARS, max_parts: int = MAX_PARTS) -> list[str]:
    """Robert's own Arabic sentences from `text`, as at most `max_parts` parts of at most `max_chars`."""
    pieces = [piece for sentence in _sentences(text) for piece in _pieces(sentence, max_chars)]
    return _merge(pieces, max_chars)[:max_parts]
