"""Verification of a generated answer before release (doc/rag-system.md §6.4).

A model output is released only if every sentence is attributed to a passage
that was in the prompt, the attributed passages actually contain most of what
the sentence says, and the whole answer passes output checks. Anything else abstains: an answer
that cannot be traced to reviewed text is not given to a child.

The support check is lexical on purpose. It cannot judge paraphrase, so it errs
towards rejecting reworded answers, which only costs an abstention; it cannot
be talked into accepting a sentence whose words are not in the sources.

grounding-v3 (test/corpus-tasks) adds three checks found necessary on Arabic
Quran and hadith answers (doc/rag-system.md §6.4): a quotation must be copied
word for word from a cited passage (`misquoted`); a faith answer must not speak
in the first person outside quotation marks (`first_person`), because the
model turned "He" (Allah) into "I"; and support matching is Arabic-aware, so a
paraphrase with attached clitics ("للملائكة" for "الملائكة") is matched. The
looser matching is only acceptable with the two new checks and the faith judge
(`judge.py`) in place.

grounding-v4 (test/corpus-tasks-serving) reads a quotation in curly single
quotes (‘…’) too, so an English quotation of a translation of the meanings is
held word for word to its passage whatever quotation marks the model uses. The
checks after verification (first person, faith terms, answered, addressee,
scene, translation, judge) are `checks.py`.

Attribution follows ordinary citation practice: a marker covers its own
sentence and, when the model cites once at the end of a short run ("They are
Talk, Learn, Quests and Style. Tap one to open it.[1]"), up to `MAX_CARRIED`
uncited sentences directly before it. Qwen3.5-9B writes that shape in about two
answers out of five (measured 2026-09-25). Each carried sentence is still held
to the same support check against the passage it is attributed to, and a
sentence with no marker after it is still a failure.
"""
from dataclasses import dataclass
import re
from typing import NamedTuple, Sequence

from . import normalize
from .prompts import NOT_IN_SOURCES
from .router import matchable
from .types import Chunk

VERIFIER_VERSION = "grounding-v4"
MAX_CHARS = 1200
MIN_SUPPORT = 0.5
MAX_CARRIED = 2  # uncited sentences a following marker may cover

_MARKER = r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]"
_MARKERS = re.compile(rf"(?:\s*{_MARKER})+")
_NUMBERS = re.compile(rf"{_MARKER}")
_TERMINAL = "[.!?\u061f\u06d4]+[\"'\u2019\u201d)]*"
# A sentence ends at terminal punctuation (optionally followed by its
# markers), or at markers that close the text or precede a capitalized word.
_SENTENCE = re.compile(
    rf"\S.*?(?:{_TERMINAL}(?:\s*{_MARKER})*(?=\s|$)|(?:\s*{_MARKER})+(?:\s*{_TERMINAL})?(?=\s*$|\s+[A-Z]))",
    re.DOTALL)
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([.!?,;:\u061f\u060c])")
_ONLY_SENTINEL = re.compile(rf"[\s`'\"*]*{NOT_IN_SOURCES}[\s`'\".*]*")

# (reason code, pattern). Raw patterns see the text with markers removed;
# folded ones see `router.matchable` text.
RAW_CHECKS = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),  # before URLs: an email contains a domain
    ("url", re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\."
                       r"(?:com|org|net|edu|gov|io|co|uk|info|app|me|ly|tv|ai)\b")),
    ("phone", re.compile(r"(?<![\w.])\+?\d(?:[ \t().-]{0,2}\d){6,}(?!\w)")),
    ("markup", re.compile(r"<\s*/?\s*[A-Za-z|!]|[\u2039\u203a]")),
)
FOLDED_CHECKS = (
    ("authority_claim", re.compile(
        r"\b(?:i am|im) (?:an? |the |your |a real |a qualified )?(?:imam|scholar|mufti|sheikh|shaykh|shaikh|alim|"
        r"aalim|mullah|mawlana|maulana|qadi|prophet|messenger|angel|religious (?:authority|leader|teacher))\b"
        r"|\bas your (?:imam|scholar|mufti|sheikh|shaykh)\b|\bmy fatwa\b|\bi (?:rule|declare) that\b"
        r"|\bi (?:can |will )?(?:give|issue) (?:you )?(?:an? )?fatwa\b")),
    ("secrecy_promise", re.compile(
        r"\b(?:i|we) (?:wont|will not|would not|wouldnt|never|promise not to) (?:tell|share|say)\b"
        r"|\bkeep(?:ing)? (?:it|this|that|your|our|a|the)(?: \w+)? secret\b|\bour (?:little )?secret\b"
        r"|\bsecret between (?:us|you and me)\b|\bbetween you and me\b|\bno one (?:will|needs to|has to) know\b")),
)


# Robert saying he cannot answer ("I can't tell you about that", "my sources don't
# say"). Lexical support cannot tell such a sentence from an answer, because its
# words come from passages about Robert. The service applies it to faith topics
# only (doc/conversation-policy.md §2 step 3): there a decline is not an answer
# from the corpus. App help is left alone, because describing what Robert does
# when he is unsure is a legitimate answer there.
DECLINE = re.compile(
    r"\bi (?:cannot|cant|can not|could not|couldnt|am not able to|m not able to|am unable to|dont|do not|did not|"
    r"didnt) (?:answer|tell|say|explain|help with|find|know|have (?:any |the |an? )?(?:information|info|details|"
    r"answers?|lessons?|sources?|stor(?:y|ies)))\b"
    r"|\b(?:my|the|these|those|your) (?:sources?|lessons?|passages?) (?:do not|dont|does not|doesnt|did not|didnt) "
    r"(?:say|talk|tell|mention|contain|cover|have|include|explain|answer)\b"
    r"|\bnot (?:in|from) (?:my|the) (?:sources?|lessons?)\b|\b(?:i am|im) not sure\b|\bno information\b")


# Quoted spans: guillemets, straight and curly double quotes, and the Quranic ornate parentheses.
_QUOTES = re.compile('«([^»]+)»|"([^"]+)"|“([^”]+)”|‘([^’]+)’|﴿([^﴾]+)﴾|﴾([^﴿]+)﴿')
# First-person words a faith answer must not use outside a quotation: Robert narrates, he never speaks as
# Allah, an angel or a prophet. Arabic verbs in the first person are left to the faith judge.
FIRST_PERSON = frozenset({"i", "me", "my", "mine", "myself", "im", "ive",
                          "انا", "اني", "انني", "معي", "لي", "عندي", "بي"})


def quotations(text: str) -> list[str]:
    """Every quoted span in `text`, in order."""
    return [next(group for group in match.groups() if group) for match in _QUOTES.finditer(text)]


def _passage_tokens(chunk: Chunk) -> list[str]:
    """A passage as matched: its search text (the simple spelling for Quran text, norm-v3)."""
    return (chunk.search_text or normalize.search_text(chunk.text, quranic=chunk.content_type == "quran")).split()


def _contains(tokens: list[str], run: list[str]) -> bool:
    width = len(run)
    return any(tokens[start:start + width] == run for start in range(len(tokens) - width + 1))


def misquoted(text: str, passages: Sequence[Chunk]) -> bool:
    """Whether a quotation of two or more words is not copied word for word from one of `passages`.

    Compared on search text, so diacritics, hamza seats and the Uthmani rasm do not count as changes;
    a dropped, added or changed word does.
    """
    for quote in quotations(text):
        run = normalize.search_text(quote, quranic=True).split()
        if len(run) >= 2 and not any(_contains(_passage_tokens(chunk), run) for chunk in passages):
            return True
    return False


def first_person(text: str) -> bool:
    """Whether `text` uses a first-person word outside its quotations."""
    outside = _QUOTES.sub(" ", text)
    return any(token in FIRST_PERSON for token in normalize.tokens(outside))


class Segment(NamedTuple):
    """One released sentence: display text without markers, and the chunk ids it cites."""
    text: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class Grounding:
    segments: tuple[Segment, ...] = ()
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


def split_sentences(text: str) -> list[str]:
    sentences, end = [], 0
    for match in _SENTENCE.finditer(text):
        sentences.append(match.group().strip())
        end = match.end()
    if text[end:].strip():
        sentences.append(text[end:].strip())
    return sentences


def cited_numbers(sentence: str) -> list[int]:
    numbers: list[int] = []
    for marker in _NUMBERS.findall(sentence):
        for number in re.findall(r"\d+", marker):
            if int(number) not in numbers:
                numbers.append(int(number))
    return numbers


def strip_markers(text: str) -> str:
    return " ".join(_SPACE_BEFORE_PUNCTUATION.sub(r"\1", _MARKERS.sub(" ", text)).split())


def _forms(token: str) -> set[str]:
    """The token and its plausible bases: "gives" -> give, "earned" -> earn."""
    forms = {token}
    if not any(char.isdigit() for char in token):
        for suffix in ("s", "es", "ed", "d", "ing", "ly", "er", "est"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                forms.add(token[:-len(suffix)])
    return forms


def support(sentence: str, passages: Sequence[Chunk]) -> float:
    """Share of the sentence's content words found in the passages.

    Lenient on inflection (shared base form, a shared Arabic light stem, or a
    shared 5-character prefix), strict on numbers. A sentence with no content
    words ("Yes!") has no support. Passages are read in their search text, so a
    Quran passage is matched in the simple spelling a sentence is written in.
    """
    tokens = normalize.content_tokens(sentence)
    if not tokens:
        return 0.0
    vocabulary = {token for chunk in passages
                  for token in normalize.content_tokens(chunk.title) + [
                      token for token in _passage_tokens(chunk) if len(token) > 1 and token not in normalize.STOPWORDS]}
    bases = {form for token in vocabulary for form in _forms(token)}
    arabic = {form for token in vocabulary for form in normalize.arabic_forms(token)}
    prefixes = {token[:5] for token in vocabulary if len(token) >= 5 and not any(c.isdigit() for c in token)}
    found = sum(1 for token in tokens if token in vocabulary or _forms(token) & bases
                or normalize.arabic_forms(token) & arabic
                or (len(token) >= 5 and not any(c.isdigit() for c in token) and token[:5] in prefixes))
    return found / len(tokens)


def verify(output: str, passages: Sequence[Chunk], *, faith: bool = False, min_support: float = MIN_SUPPORT,
           max_chars: int = MAX_CHARS, max_carried: int = MAX_CARRIED) -> Grounding:
    """Released segments, or the first failure's reason code. `faith` adds the first-person check."""
    if not output.strip():
        return Grounding(failure="empty")
    if _ONLY_SENTINEL.fullmatch(output):
        return Grounding(failure="not_in_sources")
    if NOT_IN_SOURCES in output.upper().replace(" ", "_"):
        return Grounding(failure="mixed_not_in_sources")
    if len(output) > 4 * max_chars:
        return Grounding(failure="too_long")
    plain = strip_markers(output)
    for reason, pattern in RAW_CHECKS:
        if pattern.search(plain):
            return Grounding(failure=reason)
    folded = matchable(plain)
    for reason, pattern in FOLDED_CHECKS:
        if pattern.search(folded):
            return Grounding(failure=reason)
    if faith and first_person(plain):
        return Grounding(failure="first_person")

    segments, uncited = [], []
    for sentence in split_sentences(output):
        numbers = cited_numbers(sentence)
        if not numbers:
            uncited.append(sentence)
            if len(uncited) > max_carried:
                return Grounding(failure="missing_citation")
            continue
        if any(number < 1 or number > len(passages) for number in numbers):
            return Grounding(failure="invalid_citation")
        cited = [passages[number - 1] for number in numbers]
        # The marker covers the uncited run before it and its own sentence;
        # each is checked on its own, so a carried sentence gains nothing.
        for covered in (*uncited, sentence):
            text = strip_markers(covered)
            if support(text, cited) < min_support:
                return Grounding(failure="unsupported_sentence")
            segments.append(Segment(text, tuple(chunk.id for chunk in cited)))
        uncited = []
    if uncited:
        return Grounding(failure="missing_citation")
    if not segments:
        return Grounding(failure="empty")
    cited_ids = {chunk_id for segment in segments for chunk_id in segment.citations}
    if misquoted(plain, [chunk for chunk in passages if chunk.id in cited_ids]):
        return Grounding(failure="misquoted")
    if len(" ".join(segment.text for segment in segments)) > max_chars:
        return Grounding(failure="too_long")
    return Grounding(tuple(segments))
