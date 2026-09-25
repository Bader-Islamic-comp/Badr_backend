"""Verification of a generated answer before release (doc/rag-system.md §6.4).

A model output is released only if every sentence is attributed to a passage
that was in the prompt, the attributed passages actually contain most of what
the sentence says, and the whole answer passes output checks. Anything else abstains: an answer
that cannot be traced to reviewed text is not given to a child.

The support check is lexical on purpose. It cannot judge paraphrase, so it errs
towards rejecting reworded answers, which only costs an abstention; it cannot
be talked into accepting a sentence whose words are not in the sources.

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

VERIFIER_VERSION = "grounding-v2"
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

    Lenient on inflection (shared base form, or a shared 5-character prefix),
    strict on numbers. A sentence with no content words ("Yes!") has no support.
    """
    tokens = normalize.content_tokens(sentence)
    if not tokens:
        return 0.0
    vocabulary = {token for chunk in passages for token in normalize.content_tokens(f"{chunk.title} {chunk.text}")}
    bases = {form for token in vocabulary for form in _forms(token)}
    prefixes = {token[:5] for token in vocabulary if len(token) >= 5 and not any(c.isdigit() for c in token)}
    found = sum(1 for token in tokens if token in vocabulary or _forms(token) & bases
                or (len(token) >= 5 and not any(c.isdigit() for c in token) and token[:5] in prefixes))
    return found / len(tokens)


def verify(output: str, passages: Sequence[Chunk], *, min_support: float = MIN_SUPPORT,
           max_chars: int = MAX_CHARS, max_carried: int = MAX_CARRIED) -> Grounding:
    """Released segments, or the first failure's reason code."""
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
    if len(" ".join(segment.text for segment in segments)) > max_chars:
        return Grounding(failure="too_long")
    return Grounding(tuple(segments))
