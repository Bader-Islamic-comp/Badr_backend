"""The letter-preservation check for diacritized text (ADR 0006, Robert's voice).

A model adds tashkeel to Robert's own sentences before they are spoken. It may add marks, never change a
letter: the output is accepted only when removing harakat, tanween, shadda, sukun, the dagger alef and tatweel
gives back the input (after the same normalization). Hamza forms are letters and are kept as they are, so
a model that writes «أ» for «ا» changes the text and is refused. Text is compared in NFC, so a hamza written as
a combining mark (U+0654, U+0655) composes to its letter first, and runs of white space count as one space.
"""
import re
import unicodedata

# U+064B-U+0652 (fathatan .. sukun), U+0670 (dagger alef), U+0640 (tatweel). Nothing else is removable.
MARKS = re.compile("[\u064b-\u0652\u0670\u0640]")
ARABIC_LETTER = re.compile("[\u0621-\u063a\u0641-\u064a]")


def letters(text: str) -> str:
    """`text` without the removable marks: NFC, marks removed, NFC again, white space collapsed."""
    value = MARKS.sub("", unicodedata.normalize("NFC", text))
    return " ".join(unicodedata.normalize("NFC", value).split())


def same_letters(original: str, diacritized: str) -> bool:
    """Whether `diacritized` only adds removable marks to `original` (which must hold an Arabic letter)."""
    expected = letters(original)
    return bool(ARABIC_LETTER.search(expected)) and letters(diacritized) == expected
