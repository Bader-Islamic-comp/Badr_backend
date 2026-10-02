"""The post-generation checks: independent, named checks on every faith answer (doc/rag-system.md §16, checks-v1).

grounding-v3 shows that an answer's words are in the passages it cites; the faith judge asks the same model
whether it answers. On 2026-10-01 both released a quote from the wrong scene (yusuf-04-gulf), a prayer to
Allah framed as words to a father (ibrahim-04-msa) and an answer with no number to "how long" (nuh-01-arabizi).
So a verified faith answer now passes a list of checks, each a small, separately testable function that reads
the question, the released text and the cited passages and returns `pass`, `fail` with a fixed reason code, or
`unavailable` when the data it needs is missing (recorded, never counted as a pass, and it does not withhold
the answer: a check that cannot run says so instead of guessing).

Order: the cheap deterministic checks first, the model judge last. Every deterministic check runs and is
recorded; the judge runs only when all of them passed, so a failure never costs a model call. The first
failure in this order is the faith abstention's reason (`faith_abstain:<reason>`); the codes of the checks that
existed before keep their old spelling (`grounding:first_person`, `declined`, `off_topic`, `judge:<field>`).

| Check | Applies to | Fails when |
| --- | --- | --- |
| `first_person` | answers citing religious text | Robert speaks as "I" outside a quotation |
| `faith_terms` | questions naming a faith term | the answer declines, or neither it nor its passages use the question's faith terms |
| `answered` | questions asking how many, how long or when | the answer holds no number, duration or time |
| `numbers` | answers citing religious text (checks-v2) | the answer states a count its passages do not state |
| `addressee` | a quotation framed as said to someone | its own vocative names someone else («رَبِّ» after "لأبيه") |
| `scene` | answers citing Quran passages of a mapped story | they come from another episode (scene.py) |
| `translation` | quotations of a translation of the meanings | the sentence does not present it as a named translation |
| `judge` | answers citing religious text | the model judge says no (judge.py) |

Results reach provenance (`AnswerResult.checks`) and the log line as names and codes, never text.
"""
from dataclasses import dataclass
import re
from typing import Callable, Sequence

from . import arabizi, judge as faith_judge, normalize, router
from .ayahs import AyahIndex
from .grounding import DECLINE, Segment, first_person, quotations
from .prompts import is_faith_passage, is_translation, translation_name
from .scene import Episodes, check_scene
from .types import Chunk, Generator

CHECKS_VERSION = "checks-v2"
PASS, FAIL, UNAVAILABLE = "pass", "fail", "unavailable"
NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str          # PASS, FAIL or UNAVAILABLE
    reason: str = ""     # a fixed code; for a failure, the faith abstention's reason

    def code(self) -> str:
        return f"{self.status}:{self.reason}" if self.reason else self.status


@dataclass(frozen=True)
class Answer:
    """What the checks read: the child's question, the released answer and the passages it cites."""
    question: str
    text: str                       # released text, citation markers removed
    segments: tuple[Segment, ...]
    cited: tuple[Chunk, ...]
    faith_topic: bool = False       # router.is_faith_topic(question)

    @property
    def religious(self) -> bool:
        return any(is_faith_passage(chunk) for chunk in self.cited)

    @property
    def passage_language(self) -> str:
        return self.cited[0].language if self.cited else "ar"

    @property
    def question_terms(self) -> str:
        """The question as the checks read its words: an Arabizi question through its Arabic search terms."""
        return arabizi.expand(self.question).query if arabizi.is_arabizi(self.question) else self.question


def _passed(name: str, reason: str = "") -> CheckResult:
    return CheckResult(name, PASS, reason)


def _failed(name: str, reason: str) -> CheckResult:
    return CheckResult(name, FAIL, reason)


# first_person and faith_terms: the checks the service ran before checks-v1, unchanged ----------------------

def check_first_person(answer: Answer) -> CheckResult:
    if not answer.religious:
        return _passed("first_person", NOT_APPLICABLE)
    return _failed("first_person", "grounding:first_person") if first_person(answer.text) else _passed("first_person")


def check_faith_terms(answer: Answer) -> CheckResult:
    """conversation-policy §3.1: on a faith topic, a decline is no answer, and the answer and its passages must
    use the question's own faith terms (any faith term when the question has none of its own)."""
    if not answer.faith_topic:
        return _passed("faith_terms", NOT_APPLICABLE)
    if DECLINE.search(router.matchable(answer.text)):
        return _failed("faith_terms", "declined")
    wanted = router.faith_words(answer.question)
    if arabizi.is_arabizi(answer.question):
        # An Arabizi question's terms are Latin ("nabi") and its answer is Arabic: compare the Arabic search
        # terms instead. When they hold no faith term, only the decline rule can be read (found on the
        # 2026-10-01 replay: "el kilme el 7ilwe sada2a?" answered with the hadith itself).
        wanted = router.faith_words(answer.question_terms)
        if not wanted:
            return _passed("faith_terms", "declined_only")
    for text in (answer.text, " ".join(chunk.text for chunk in answer.cited)):
        found = router.faith_words(text)
        if not (found & wanted if wanted else found):
            return _failed("faith_terms", "off_topic")
    return _passed("faith_terms")


# answered: a question for a quantity, a duration or a time gets one --------------------------------------

_QUANTITY_AR = {"كم", "بكم", "قديش", "اديش", "قداش", "كام", "بكام", "شقد", "اشقد", "شكد", "عدد", "مده"}
_TIME_AR = {"متي", "امتي", "ايمتي", "ايمت", "امتا", "وقتاش", "ايمته", "امته"}
_QUANTITY_ARABIZI = {"kam", "kaam", "2adeish", "2adesh", "2addeish", "2addesh", "adeish", "adesh", "addeish",
                     "addesh", "2adde", "2adeh", "shgad", "chgad", "shkad", "3adad"}
_TIME_ARABIZI = {"emta", "imta", "aimta", "amta", "emtan", "eimta", "imtan", "waqtesh", "emteh"}
_QUANTITY_EN = re.compile(r"\bhow (?:many|much|long|old|often|far)\b|\bwhat (?:number|age)\b|\bnumber of\b")
_TIME_EN = re.compile(r"(?:^|[.!?,;:]\s*)(?:(?:hi|hello|robert|and|so|but)\W+){0,3}when\b|"
                      r"\b(?:what|which) (?:time|year|day|month|age)\b|\bat what age\b", re.IGNORECASE)
_NUMBER_WORDS_AR = frozenset("""
واحد واحده اثنان اثنين اثنتان اثنتين اثنا اثني ثلاث ثلاثه اربع اربعه خمس خمسه ست سته سبع سبعه ثمان ثماني ثمانيه
تسع تسعه عشر عشره عشرون عشرين ثلاثون ثلاثين اربعون اربعين خمسون خمسين ستون ستين سبعون سبعين ثمانون ثمانين تسعون
تسعين ميه مايه مئه مييه مئتين مايتين الف الفا الفين الاف الوف مليون نصف ثلث ربع مره مرتين مرات بضع بضعه
""".split())
# Durations answer "how many" and "how long"; times of day answer only "when".
_DURATIONS_AR = frozenset("""
سنه سنين سنوات سنتين عام عاما اعوام عامين شهر اشهر شهور شهرين اسبوع اسابيع يوم ايام يومين ليله ليال ليالي
ساعه ساعات دقيقه دقايق دهر عمر عمره
""".split())
_TIMES_AR = frozenset("ليل ليلا نهار نهارا صباح صباحا مساء مساءا عشاء فجر ظهر عصر مغرب ضحي سحر بكره اصيل".split())
_CLAUSE_AR = frozenset({"عندما", "لما", "حين", "حينما", "بعد", "بعدما", "قبل", "اثناء", "بينما", "اذ", "يوم", "ريثما"})
_NUMBER_EN = re.compile(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
                        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
                        r"seventy|eighty|ninety|hundred|hundreds|thousand|thousands|million|half|once|twice|"
                        r"dozen|several)\b")
_DURATIONS_EN = re.compile(r"(?:years?|days?|nights?|months?|weeks?|hours?|minutes?|times|ages?|old|"
                           r"centur(?:y|ies))")
_TIMES_EN = re.compile(r"(?:mornings?|evenings?|night|noon|dawn|sunset|sunrise|daytime|day)")
_CLAUSE_EN = re.compile(r"\b(?:when|after|before|while|during|until|since|as soon as|once)\b")
_DIGIT = re.compile("[0-9٠-٩۰-۹]")


def asks_for(question: str) -> str | None:
    """"quantity" for how many, how much and how long; "time" for when; None for any other question."""
    folded = router.matchable(question)
    tokens = set(folded.split())
    if tokens & _QUANTITY_AR or (arabizi.is_arabizi(question) and tokens & _QUANTITY_ARABIZI):
        return "quantity"
    if _QUANTITY_EN.search(folded) and not arabizi.is_arabizi(question) and normalize.detect_language(question) == "en":
        return "quantity"
    if tokens & _TIME_AR or (arabizi.is_arabizi(question) and tokens & _TIME_ARABIZI):
        return "time"
    if normalize.detect_language(question) == "en" and not arabizi.is_arabizi(question) and _TIME_EN.search(
            question.strip().lower()):
        return "time"
    return None


def gives(text: str, wanted: str) -> bool:
    """Whether an answer holds a number or a duration; for a time question also a time of day or a time clause."""
    if _DIGIT.search(text):
        return True
    folded = router.matchable(text)
    forms = {form for token in folded.split() for form in normalize.arabic_forms(token)}
    if forms & (_NUMBER_WORDS_AR | _DURATIONS_AR) or _NUMBER_EN.search(folded) or _DURATIONS_EN.search(folded):
        return True
    return wanted == "time" and bool(forms & (_TIMES_AR | _CLAUSE_AR) or _TIMES_EN.search(folded)
                                     or _CLAUSE_EN.search(folded))


def check_answered(answer: Answer) -> CheckResult:
    wanted = asks_for(answer.question)
    if wanted is None:
        return _passed("answered", NOT_APPLICABLE)
    return _passed("answered") if gives(answer.text, wanted) else _failed("answered", f"answered:no_{wanted}")


# numbers: a count in a faith answer is one its passages give (checks-v2) ------------------------------------
#
# The 2026-10-02 run released "Yusuf stayed nine years in prison" over 12:42, which says «بِضْعَ سِنِينَ» (a few
# years): `answered` saw a number and the judge passed it. A count the answer states must now be in the cited
# passages, as a word or in digits; a count the passages only imply (950 from «أَلْفَ سَنَةٍ إِلَّا خَمْسِينَ») is
# not stated by them, so it fails too, and the child gets the abstention rather than an untraceable number.
# "One", "once", "times" and "a few" state no count and are not read; nor are surah and ayah numbers.
_COUNT_AR = {
    "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اثنتين": 2, "اثنا": 2, "اثني": 2, "مرتين": 2, "ثلاث": 3, "ثلاثه": 3,
    "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثماني": 8,
    "ثمانيه": 8, "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10, "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30,
    "اربعون": 40, "اربعين": 40, "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90, "ميه": 100, "مايه": 100, "مئه": 100, "مييه": 100,
    "مئتين": 200, "مايتين": 200, "الف": 1000, "الفا": 1000, "الاف": 1000, "الوف": 1000, "الفين": 2000,
    "مليون": 10 ** 6, "نصف": 0.5, "ثلث": "1/3", "ربع": "1/4",
}
_COUNT_EN = {
    "two": 2, "twice": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "hundreds": 100, "thousand": 1000,
    "thousands": 1000, "million": 10 ** 6, "half": 0.5,
}
_EASTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_REFERENCE = re.compile(r"\d+\s*[:：]\s*\d+(?:\s*[-–]\s*\d+)?|"
                        r"(?:الآية|الآيه|آية|آيه|الايه|ايه|الآيات|الايات|سورة|سوره|البخاري|مسلم|حديث|الحديث|رقم|"
                        r"ayah|ayat|verse|verses|surah|bukhari|muslim|hadith|number|no\.)\s*(?:رقم\s*)?\d+",
                        re.IGNORECASE)
_COUNT_PREFIXES = ("وال", "بال", "فال", "و", "ف", "ب", "ل")


def _count_forms(token: str) -> set[str]:
    """The token and the token without one leading clitic ("والف" -> "الف"). Trailing pronouns are not
    stripped: "الفهم" (understanding) is not "الف" (a thousand)."""
    return {token} | {token[len(prefix):] for prefix in _COUNT_PREFIXES
                      if token.startswith(prefix) and len(token) - len(prefix) >= 2}


def counts(text: str) -> set:
    """The counts a text states: digits (surah, ayah and hadith numbers left out) and number words, as values."""
    plain = _REFERENCE.sub(" ", text.translate(_EASTERN_DIGITS))
    found: set = {int(digits) for digits in re.findall(r"\d+", plain)}
    for token in router.matchable(plain).split():
        for form in _count_forms(token):
            if form in _COUNT_AR:
                found.add(_COUNT_AR[form])
        if token in _COUNT_EN:
            found.add(_COUNT_EN[token])
    return found


def check_numbers(answer: Answer) -> CheckResult:
    if not answer.religious:
        return _passed("numbers", NOT_APPLICABLE)
    stated = counts(answer.text)
    if not stated:
        return _passed("numbers", NOT_APPLICABLE)
    given = counts(" ".join(chunk.text for chunk in answer.cited))
    return _passed("numbers") if stated <= given else _failed("numbers", "numbers:not_in_sources")


# addressee: a quotation said "to his father" must speak to a father ---------------------------------------

_SPEECH_AR = frozenset({"قال", "قالوا", "قالت", "قالا", "يقول", "يقولون", "تقول", "نادي", "نادوا", "ينادي", "دعا",
                        "دعوا", "يدعو", "خاطب", "يخاطب", "سال", "سالوا", "يسال", "ناجي", "اجاب", "رد", "صاح",
                        "قايلا", "قايلين", "حدث", "كلم", "اخبر"})
# Who a frame names as addressee ("قال إبراهيم لأبيه"): the light stems of the word after the verb.
_ADDRESSEE_AR = {
    "father": {"ابيه", "اباه", "ابوه", "ابيهم", "اباهم", "ابوهم", "والده", "والدهم"},
    "people": {"قومه", "قومهم"},
    "lord": {"ربه", "ربهم", "الله", "لله"},
    "children": {"ابنه", "ابنيه", "بنيه", "ابنايه", "اولاده", "ولده", "ابنايهم"},
    "brothers": {"اخوته", "اخوانه", "اخوتهم", "اخيه", "اخاه"},
    "king": {"ملك", "الملك"},
    "pharaoh": {"فرعون"},
    "mother": {"امه"},
}
# Who a quotation's own vocative addresses: its first noun after "يا", or a joined Uthmani vocative.
_VOCATIVE_AR = {
    "lord": {"رب", "ربي", "ربنا", "اللهم", "الله"},
    "father": {"ابت", "ابتي", "ابانا", "ابي"},
    "people": {"قوم", "قومي", "ايها الناس"},
    "children": {"بني", "ابني"},
    "council": {"ايها الملا"},
    "aziz": {"ايها العزيز"},
    "prisoners": {"صاحبي", "صحبي"},
    "pharaoh": {"فرعون"},
}
_JOINED = {"ابت", "ابتي", "ابانا", "قوم", "قومي", "بني", "صحبي", "صاحبي", "ايها", "رب", "ربنا"}
_LEAD_AR = frozenset({"و", "ف", "اذ", "واذ", "قال", "فقال", "وقال", "قالوا", "فقالوا", "وقالوا", "قالت", "ثم", "انه",
                      "انا"})
_SENTENCE_END = re.compile(r"[.!?؟۔\n]")
_FRAME_EN = re.compile(r"\b(?:said|says|say|told|tells|asked|asks|called|calls|cried|prayed|prays|spoke|speaks|"
                       r"answered|replied|shouted|begged)\b(?: out)?(?: \w+){0,2}? (?:to )?(?:his |her |their |the |our )?"
                       r"(father|people|lord|allah|god|son|sons|children|king|brothers|brother|mother|pharaoh)\b")
_ADDRESSEE_EN = {"father": "father", "people": "people", "lord": "lord", "allah": "lord", "god": "lord",
                 "son": "children", "sons": "children", "children": "children", "king": "king",
                 "brothers": "brothers", "brother": "brothers", "mother": "mother", "pharaoh": "pharaoh"}
_VOCATIVE_EN = (
    ("lord", re.compile(r"^(?:o |oh )?(?:my |our )?(?:lord|allah|god)\b")),
    ("father", re.compile(r"^(?:o |oh )?(?:my |our )?father\b")),
    ("people", re.compile(r"^(?:o |oh )?(?:my )?(?:people|mankind)\b")),
    ("children", re.compile(r"^(?:o |oh )?(?:my )?(?:son|sons|children|dear son)\b")),
    ("council", re.compile(r"^(?:o |oh )?(?:eminent ones|chiefs|council|nobles)\b")),
    ("aziz", re.compile(r"^(?:o |oh )?(?:aziz|al aziz|minister)\b")),
    ("pharaoh", re.compile(r"^(?:o |oh )?pharaoh\b")),
)
_LEAD_EN = re.compile(r"^(?:(?:and|then|he|she|they|said|says|say|that|indeed|verily)\s+)*")
_PROPHETS = {entry["ar"]: entry["id"] for entry in arabizi._aliases()["prophets"]}
_PROPHETS_LATIN = {spelling: entry["id"] for entry in arabizi._aliases()["prophets"] for spelling in entry["latin"]}


def _frame_ar(before: str) -> str | None:
    """The addressee a speech frame names, from the words just before a quotation: "قال إبراهيم لأبيه" ->
    father. A prophet's name counts only after ل or إلى ("قال لموسى"); right after the verb it is the speaker."""
    tokens = normalize.search_text(before).split()[-6:]
    for index, token in enumerate(tokens):
        if not normalize.arabic_forms(token) & _SPEECH_AR:
            continue
        for position in range(index + 1, len(tokens)):
            word = tokens[position]
            forms = normalize.arabic_forms(word)
            for name, words in _ADDRESSEE_AR.items():
                if forms & words:
                    return name
            named = word[1:] if word.startswith("ل") else word if tokens[position - 1] == "الي" else ""
            if named in _PROPHETS:
                return "prophet:" + _PROPHETS[named]
    return None


def _vocative_ar(quote: str) -> str | None:
    """Whom a quotation's own vocative addresses: "يا أبت" or the Uthmani "يابت" -> father, "رب" -> lord."""
    tokens = normalize.search_text(quote, quranic=True).split()
    while tokens and tokens[0] in _LEAD_AR:
        tokens = tokens[1:]
    if not tokens:
        return None
    first, rest = tokens[0], tokens[1:]
    if first == "يا" and rest:
        noun, rest = rest[0], rest[1:]
    elif first.startswith("ي") and len(first) > 3 and (first[1:] in _JOINED or first[1:] in _PROPHETS):
        noun = first[1:]                       # Uthmani joins the vocative: "يابت", "يقوم", "يبني", "يموسي"
    else:
        # Only a call to the Lord needs no "يا": "رب", "ربنا", "اللهم" ("ربي" opening a quotation is a statement).
        return "lord" if first in {"رب", "ربنا", "اللهم"} else None
    if noun == "ايها" and rest:
        noun = "ايها " + rest[0]
    if noun in _PROPHETS:
        return "prophet:" + _PROPHETS[noun]
    return _class(noun, _VOCATIVE_AR)


def _class(word: str, classes: dict[str, set[str]]) -> str | None:
    return next((name for name, words in classes.items() if word in words), None)


def _frame_en(before: str) -> str | None:
    matches = list(_FRAME_EN.finditer(router.matchable(before)))
    if matches:
        return _ADDRESSEE_EN[matches[-1].group(1)]
    named = re.search(r"\b(?:said|told|asked|called|cried|prayed|spoke) (?:to )?(\w+)\W*$", router.matchable(before))
    if named and named.group(1) in _PROPHETS_LATIN:
        return "prophet:" + _PROPHETS_LATIN[named.group(1)]
    return None


def _vocative_en(quote: str) -> str | None:
    text = _LEAD_EN.sub("", router.matchable(quote))
    for name, pattern in _VOCATIVE_EN:
        if pattern.match(text):
            return name
    named = re.match(r"^(?:o|oh) (\w+)\b", text)
    if named and named.group(1) in _PROPHETS_LATIN:
        return "prophet:" + _PROPHETS_LATIN[named.group(1)]
    return None


_QUOTE = re.compile('«([^»]+)»|"([^"]+)"|“([^”]+)”|‘([^’]+)’|﴿([^﴾]+)﴾|﴾([^﴿]+)﴿')


def addressee_mismatches(text: str) -> list[tuple[str, str]]:
    """(frame, vocative) for each quotation whose speech frame and own vocative name different addressees."""
    found, start = [], 0
    for match in _QUOTE.finditer(text):
        before = text[start:match.start()]
        ends = list(_SENTENCE_END.finditer(before))
        before = before[ends[-1].end():] if ends else before
        quote = next(group for group in match.groups() if group)
        arabic = bool(re.search("[ء-ي]", before + quote))
        frame = _frame_ar(before) if arabic else _frame_en(before)
        vocative = _vocative_ar(quote) if arabic else _vocative_en(quote)
        if frame and vocative and frame != vocative:
            found.append((frame, vocative))
        start = match.end()
    return found


def check_addressee(answer: Answer) -> CheckResult:
    if not quotations(answer.text):
        return _passed("addressee", NOT_APPLICABLE)
    return _failed("addressee", "addressee:mismatch") if addressee_mismatches(answer.text) else _passed("addressee")


# translation: a translation of the meanings is presented as one --------------------------------------------

_TRANSLATION_WORD = re.compile(r"\btranslat\w*\b|\bmeanings?\b", re.IGNORECASE)


def check_translation(answer: Answer) -> CheckResult:
    """A sentence quoting a translation of the meanings must say it is a translation and name it."""
    translations = [chunk for chunk in answer.cited if is_translation(chunk)]
    if not translations:
        return _passed("translation", NOT_APPLICABLE)
    by_id = {chunk.id: chunk for chunk in translations}
    for segment in answer.segments:
        quoted = [normalize.search_text(quote).split() for quote in quotations(segment.text)]
        sources = [by_id[chunk_id] for chunk_id in segment.citations if chunk_id in by_id]
        if not quoted or not sources:
            continue
        if not _TRANSLATION_WORD.search(segment.text):
            return _failed("translation", "translation:unframed")
        names = [translation_name(chunk) for chunk in sources if translation_name(chunk)]
        if names and not any(router.matchable(name) in router.matchable(segment.text) for name in names):
            return _failed("translation", "translation:unnamed")
    return _passed("translation")


# The pipeline -----------------------------------------------------------------------------------------------

class Verifier:
    """Runs the checks in order. The episode and ayah data come from the release and data/episodes.json."""

    def __init__(self, episodes: Episodes | None = None, ayahs: AyahIndex | None = None):
        self.episodes, self.ayahs = episodes, ayahs

    def check_scene(self, answer: Answer) -> CheckResult:
        finding = check_scene(answer.question, answer.question_terms, [segment.text for segment in answer.segments],
                              answer.cited, answer.passage_language, self.episodes, self.ayahs)
        if finding.status == FAIL:
            return _failed("scene", "scene:" + finding.reason)
        return CheckResult("scene", finding.status, finding.reason)

    @property
    def deterministic(self) -> tuple[Callable[[Answer], CheckResult], ...]:
        return (check_first_person, check_faith_terms, check_answered, check_numbers, check_addressee,
                self.check_scene, check_translation)

    def run(self, answer: Answer, generator: Generator | None) -> tuple[tuple[CheckResult, ...], str | None]:
        """Every result in order, and the first failure's reason (None when the answer may be released)."""
        results = [check(answer) for check in self.deterministic]
        failure = next((result.reason for result in results if result.status == FAIL), None)
        if failure is None and answer.religious:
            if generator is None:
                results.append(CheckResult("judge", UNAVAILABLE, "no_model"))
            else:
                verdict = faith_judge.judge(generator, answer.question, answer.text, list(answer.cited))
                results.append(_failed("judge", verdict) if verdict else _passed("judge"))
                failure = verdict
        return tuple(results), failure


def summary(results: Sequence[CheckResult]) -> dict[str, str]:
    """Names and codes for the log line: {"answered": "pass", "scene": "fail:scene:other_episode", ...}."""
    return {result.name: result.code() for result in results}
