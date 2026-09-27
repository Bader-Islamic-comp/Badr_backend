"""Canonical text is kept verbatim; search text is a separate, lossy view of it.

The canonical form is what a child is shown and what a reviewer approved, so it
is only Unicode-composed and trimmed. Search text folds case, Arabic diacritics,
tatweel and letter variants so that "أ" and "ا", or "Stars" and "stars", match.
Search text is never displayed and never written back over canonical text.

norm-v2 adds one step for Arabic: Uthmani-rasm spellings are mapped to the
simple spelling ("الصلوه" -> "الصلاه") from a table derived from Tanzil data
(`data/rasm_map.tsv`, built by `corpusprep.rasm`). Latin text is unchanged.
"""
from pathlib import Path
import re
import unicodedata

VERSION = "norm-v2"
_RASM_FILE = Path(__file__).with_name("data") / "rasm_map.tsv"


def _load_rasm() -> dict[str, str]:
    if not _RASM_FILE.is_file():
        return {}
    table = {}
    for line in _RASM_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            word, target = line.split("\t")
            table[word] = target
    return table


RASM = _load_rasm()

# Harakat, tanwin, shadda, sukun, superscript alef and Qur'anic annotation marks.
_ARABIC_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_TATWEEL = "\u0640"
_ARABIC_FOLDS = str.maketrans({
    "\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627", "\u0671": "\u0627",  # alef variants
    "\u0649": "\u064a",  # alef maqsura -> ya
    "\u0629": "\u0647",  # ta marbuta -> ha
    "\u0624": "\u0648", "\u0626": "\u064a",  # hamza carriers
})
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_ARABIC_LETTER = re.compile("[\u0600-\u06ff]")
_LATIN_LETTER = re.compile("[A-Za-z]")

STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from how i if in is it its me my of on or so that the "
    "their them then there these they this to was what when where which who why will with you your "
    "\u0641\u064a \u0645\u0646 \u0639\u0644\u064a \u0627\u0644\u064a \u0639\u0646 \u0647\u0630\u0627 "
    "\u0647\u0630\u0647 \u0645\u0627 \u0645\u0627\u0630\u0627 \u0643\u064a\u0641 \u0647\u0644 \u0648".split()
)


def canonical(text: str) -> str:
    """The displayable form: NFC-composed and trimmed, otherwise untouched."""
    return unicodedata.normalize("NFC", text).strip()


def search_text_v1(text: str) -> str:
    """norm-v1: case, marks, tatweel and letter variants folded, punctuation removed."""
    value = unicodedata.normalize("NFKC", text).casefold()
    value = _ARABIC_MARKS.sub("", value).replace(_TATWEEL, "").translate(_ARABIC_FOLDS)
    return " ".join(_NON_WORD.sub(" ", value).replace("_", " ").split())


def tokens_v1(text: str) -> list[str]:
    return search_text_v1(text).split()


def search_text(text: str) -> str:
    """The matchable form (norm-v2). Deterministic, idempotent and never shown."""
    return " ".join(RASM.get(word, word) for word in search_text_v1(text).split())


def tokens(text: str) -> list[str]:
    """Every search token, stopwords included, in order."""
    return search_text(text).split()


def content_tokens(text: str) -> list[str]:
    """Search tokens that carry meaning: stopwords and single characters dropped."""
    return [token for token in tokens(text) if len(token) > 1 and token not in STOPWORDS]


def detect_language(text: str) -> str:
    """"ar" when Arabic letters outnumber Latin ones, otherwise "en"."""
    return "ar" if len(_ARABIC_LETTER.findall(text)) > len(_LATIN_LETTER.findall(text)) else "en"
