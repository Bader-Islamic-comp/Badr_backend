"""Curated adhkar, supplications and prayer lessons, served verbatim (curated-v1).

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

CURATED_VERSION = "curated-v1"
MAX_ITEMS = 4

# Phrases in the question (search-folded, as `router.matchable` gives them) naming an occasion code.
OCCASION_CUES = {
    "morning": ("الصباح", "صباحا", "الصبح", "اصبح", "sabah", "el sob7", "morning"),
    "evening": ("المساء", "مساءا", "المسا", "امسي", "masa", "evening"),
    "after_obligatory_prayer": ("بعد الصلاه", "بعد التسليم", "دبر الصلاه", "بعد ما اصلي", "بعد ما نصلي",
                                "ba3d el salah", "ba3d el sala", "after prayer", "after the prayer", "after salah"),
    "before_eating": ("قبل الطعام", "قبل الاكل", "قبل ما اكل", "قبل ما ناكل", "abl el akl", "before eating",
                      "before i eat", "before food"),
    "before_sleep": ("قبل النوم", "قبل ما انام", "عند النوم", "abl ma nam", "before sleep", "before bed"),
    "after_waking": ("بعد الاستيقاظ", "اذا استيقظت", "لما اصحي", "لما اقوم من النوم", "when i wake", "after waking"),
    "before_bathroom": ("الحمام", "الخلاء", "bathroom", "toilet"),
    "entering_mosque": ("دخول المسجد", "ادخل المسجد", "دخلت المسجد", "entering the mosque", "enter the mosque"),
    "leaving_mosque": ("الخروج من المسجد", "اخرج من المسجد", "خرجت من المسجد", "leaving the mosque"),
    "after_sneezing": ("عطس", "العطاس", "اعطس", "sneez"),
    "for_parents": ("للوالدين", "لوالدي", "لامي وابي", "لابي وامي", "for my parents"),
    "learning": ("زياده العلم", "طلب العلم", "عند التعلم"),
    "before_difficult_task": ("مهمه صعبه", "الامتحان", "الاختبار"),
    "gratitude": ("الشكر", "اشكر الله"),
    "seeking_guidance": ("الهدايه",),
    "for_family": ("لاسرتي", "للاسره", "لعايلتي"),
    "after_mistake": ("اذا اخطات", "بعد الخطا", "لما اغلط"),
}
# The question asks what to say: a dhikr, a supplication, the words for an occasion.
SAY_CUES = ("ذكر", "اذكار", "الاذكار", "الذكر", "دعاء", "الدعاء", "ادعيه", "اقول", "نقول", "يقول", "بقول", "اقرا",
            "shu b2ool", "shu ba2ool", "sh2ool", "what do i say", "what should i say", "dua", "dhikr", "adhkar")
# Prayer lessons: (section, phrases naming it). The question asks how, or for the steps or the count.
LESSON_CUES = (
    ("counts", ("عدد ركعات", "كم ركعه", "ركعات الصلوات", "ركعات الصلاه")),
    ("wudu", ("الوضوء", "اتوضا", "نتوضا", "wudu")),
    ("preparation", ("الاستعداد للصلاه", "شروط الصلاه")),
    ("steps", ("خطوات الصلاه", "كيف اصلي", "كيف نصلي", "صفه الصلاه", "اتعلم الصلاه", "how do i pray", "how to pray")),
)
HOW_CUES = ("كيف", "خطوات", "عدد", "كم", "how", "steps", "kif", "keef")


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
    if _has(folded, SAY_CUES):
        found = [code for code, cues in OCCASION_CUES.items() if _has(folded, cues)]
        if len(found) == 1:
            return "occasion:" + found[0]
    if _has(folded, HOW_CUES):
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
