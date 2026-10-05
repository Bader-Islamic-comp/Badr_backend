"""Curated adhkar, supplications and prayer lessons, served verbatim (curated-v1; v2 keeps other prayers out;
v3 adds the dialect phrasings children use).

The 2026-10-04 real-model run over the competition package (corpus/competition-ar) answered every story
question correctly but held back every adhkar, supplication and prayer question: the model mixed items of
different occasions (an after-prayer note in the evening adhkar) or retold a correct item that the judge then
rejected. These items are the package's own wording, meant to be shown as written. So when a child asks what
to say on an occasion the package covers, or how to do a part of the prayer it teaches, the reply is those
items verbatim, cited, with no model call: nothing is generated, so there is nothing to ground or judge.

An item is found by its document's `topics`: `occasion:<code>` for adhkar and supplications, `lesson:<section>`
for the prayer lessons (corpusprep/competition.py). A question must name both an occasion and ask what to say
(or name a prayer lesson and ask how); anything else goes on to retrieval as before. Arabic and Arabizi
questions only: the items are Arabic.
"""
from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from . import router
from .types import Chunk

CURATED_VERSION = "curated-v3"
MAX_ITEMS = 4

# Phrases in the question (search-folded, as `router.matchable` gives them) naming an occasion code.
OCCASION_CUES = {
    "morning": ("الصباح", "صباحا", "الصبح", "اصبح", "الصباحيه", "صباحيه", "sabah", "el sob7", "es sob7", "sob7",
                "morning"),
    "evening": ("المساء", "مساءا", "المسا", "امسي", "المسائيه", "masa", "masaa", "el masa", "evening"),
    "after_obligatory_prayer": ("بعد الصلاه", "بعد صلاه", "بعد التسليم", "دبر الصلاه", "بعد ما اصلي", "بعد ما نصلي",
                                "بعد ما اخلص الصلاه", "بعد ما اخلص صلاتي", "بعد ما نخلص الصلاه", "بعد ما اسلم",
                                "بعد الصلوات",
                                "ba3d el salah", "ba3d el sala", "ba3d ma asalli", "after prayer", "after the prayer",
                                "after salah", "after praying"),
    "before_eating": ("قبل الطعام", "قبل الاكل", "قبل ما اكل", "قبل ما ناكل", "قبل الغدا", "قبل العشا", "قبل الفطور",
                      "وقت الاكل", "abl el akl", "2abl el akl", "abl ma akol", "before eating", "before i eat",
                      "before food"),
    "before_sleep": ("قبل النوم", "قبل ما انام", "قبل ما ننام", "عند النوم", "وقت النوم", "لما انام", "abl ma nam",
                     "2abl ma nam", "abl el nom", "before sleep", "before bed", "before sleeping", "bedtime"),
    "after_waking": ("بعد الاستيقاظ", "اذا استيقظت", "لما اصحي", "لما نصحي", "بعد ما اصحي", "اذا صحيت", "لما افيق",
                     "لما اقوم من النوم", "when i wake", "after waking", "when i get up", "waking up"),
    "before_bathroom": ("الحمام", "الخلاء", "التواليت", "دوره المياه", "hammam", "7ammam", "bathroom", "toilet"),
    "entering_mosque": ("دخول المسجد", "ادخل المسجد", "دخلت المسجد", "ندخل المسجد", "دخول الجامع", "ادخل الجامع",
                        "entering the mosque", "enter the mosque"),
    "leaving_mosque": ("الخروج من المسجد", "اخرج من المسجد", "خرجت من المسجد", "اطلع من المسجد", "اطلع من الجامع",
                       "اخرج من الجامع", "الخروج من الجامع", "leaving the mosque", "leave the mosque"),
    "after_sneezing": ("عطس", "العطاس", "اعطس", "عطست", "يعطس", "العطسه", "3atast", "3atas", "sneez"),
    "for_parents": ("للوالدين", "لوالدي", "لامي وابي", "لابي وامي", "لامي وابوي", "لابوي وامي", "لماما وبابا",
                    "لبابا وماما", "لامي", "لابوي", "لابي", "for my parents", "for my mom and dad"),
    "learning": ("زياده العلم", "طلب العلم", "عند التعلم", "قبل الدراسه", "قبل ما ادرس", "قبل المذاكره",
                 "قبل ما اذاكر", "عشان افهم", "for knowledge", "before studying"),
    "before_difficult_task": ("مهمه صعبه", "الامتحان", "الاختبار", "امتحان", "اختبار", "امتحاني", "الامتحانات",
                              "للامتحان", "للاختبار",
                              "الاختبارات", "before an exam", "before a test", "exam"),
    "gratitude": ("الشكر", "اشكر الله", "اشكر ربي", "احمد الله", "نشكر الله", "to thank allah"),
    "seeking_guidance": ("الهدايه", "يهديني", "اهتدي"),
    "for_family": ("لاسرتي", "للاسره", "لعايلتي", "لعيلتي", "لاهلي", "لاخواني", "لاخوتي", "for my family"),
    "after_mistake": ("اذا اخطات", "بعد الخطا", "لما اغلط", "اذا غلطت", "لما اعمل غلط", "لما اعمل ذنب", "بعد الذنب",
                      "when i make a mistake"),
}
# The question asks what to say: a dhikr, a supplication, the words for an occasion. curated-v3 adds the dialect
# verbs children use («شو أدعي؟», «وش أقول؟», «شو بنقول؟») and memorising or repeating words.
SAY_CUES = ("ذكر", "اذكار", "الاذكار", "الذكر", "دعاء", "الدعاء", "ادعيه", "اقول", "نقول", "يقول", "بقول", "بنقول",
            "اقرا", "نقرا", "ادعي", "ندعي", "بدعي", "احفظ", "اردد", "نردد",
            "shu b2ool", "shu ba2ool", "sh2ool", "shu a2ool", "eish a2ool", "wesh agool", "shu bnoul",
            "what do i say", "what should i say", "dua", "du3a", "do3a2", "doaa", "dhikr", "adhkar", "azkar", "athkar")
# Prayer lessons: (section, phrases naming it). The question asks how, or for the steps or the count.
LESSON_CUES = (
    ("counts", ("عدد ركعات", "عدد الركعات", "كم ركعه", "قديش ركعه", "كام ركعه", "ركعات الصلوات", "ركعات الصلاه")),
    ("wudu", ("الوضوء", "الوضو", "اتوضا", "اتوضي", "بتوضا", "نتوضا", "wudu", "wudhu", "wudoo")),
    ("preparation", ("الاستعداد للصلاه", "شروط الصلاه")),
    ("steps", ("خطوات الصلاه", "كيف اصلي", "كيف بصلي", "كيف نصلي", "ازاي اصلي", "شلون اصلي", "صفه الصلاه",
               "طريقه الصلاه", "كيفيه الصلاه", "اتعلم الصلاه", "علمني الصلاه", "علمني اصلي", "how do i pray",
               "how to pray")),
)
# A question about the words rather than for them (their merit, meaning or reason) is left to retrieval (curated-v3).
ABOUT_CUES = ("فضل", "معني", "شو يعني", "ماذا يعني", "ليش", "لماذا", "ليه", "why", "meaning", "virtue")
HOW_CUES = ("كيف", "خطوات", "عدد", "كم", "قديش", "كام", "ازاي", "شلون", "كيفيه", "طريقه", "علمني", "how", "steps",
            "kif", "keef")
# Prayers the lessons do not teach (curated-v2): the counts lesson lists the five daily prayers, so "how many
# rak'ahs in Tarawih" must not get it (found by the release gate's harmful-set check, out_of_corpus_religious-02).
OTHER_PRAYERS = ("التراويح", "تراويح", "الوتر", "وتر", "الضحي", "ضحي", "العيد", "العيدين", "عيد", "الجمعه", "جمعه",
                 "الكسوف", "الخسوف", "الاستسقاء", "الاستخاره", "الجنازه", "جنازه", "السنن", "الرواتب", "قيام الليل",
                 "التهجد", "tarawih", "taraweeh", "witr", "duha", "eid", "jumuah", "jumma", "friday prayer", "funeral")


@dataclass(frozen=True)
class Selection:
    topic: str                   # "occasion:morning" or "lesson:steps"
    chunks: tuple[Chunk, ...]    # in release order, at most MAX_ITEMS


def _has(folded: str, cues: Iterable[str]) -> bool:
    """Whether the folded question holds a cue: a phrase anywhere, a word as a word, also behind an attached
    و ف ب ل ("والمساء" is "المساء")."""
    words = set(folded.split())
    words |= {word[1:] for word in words if len(word) > 3 and word[0] in "وفبل"}
    return any((" " in cue and cue in folded) or cue in words or (cue == "sneez" and cue in folded) for cue in cues)


def topic(question: str) -> str | None:
    """The curated topic a question asks for, or None."""
    folded = router.matchable(question)
    if _has(folded, ABOUT_CUES):
        return None
    if _has(folded, SAY_CUES):
        found = [code for code, cues in OCCASION_CUES.items() if _has(folded, cues)]
        if len(found) == 1:
            return "occasion:" + found[0]
    if _has(folded, HOW_CUES) and not _has(folded, OTHER_PRAYERS):
        for section, cues in LESSON_CUES:
            if _has(folded, cues):
                return "lesson:" + section
    return None


def select(question: str, chunks: Sequence[Chunk]) -> Selection | None:
    """The eligible curated items for the question's topic, or None when it names none or none exists."""
    wanted = topic(question)
    if wanted is None:
        return None
    found = tuple(chunk for chunk in chunks if wanted in chunk.topics)[:MAX_ITEMS]
    return Selection(wanted, found) if found else None


_SPACES = re.compile(r"\n{3,}")


def text(selection: Selection) -> str:
    """The items as written, one paragraph each."""
    return _SPACES.sub("\n\n", "\n\n".join(chunk.text.strip() for chunk in selection.chunks))
