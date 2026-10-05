"""curated-v1: adhkar, supplications and prayer lessons of the curated package are served verbatim.

Placeholder item text only; the questions are the package's own evaluation questions and similar ones.
"""
import pytest

from companion_api.rag import curated, normalize
from companion_api.rag.types import Chunk


def _chunk(chunk_id, text, topics, content_type="dua"):
    return Chunk(id=chunk_id, document_id=chunk_id.split("#")[0], kind="passage", title="عنوان تجريبي",
                 language="ar", age_bands=("7-9", "10-11"), content_type=content_type, madhhab=(),
                 review_status="draft", synthetic=False, text=text, search_text=normalize.search_text(text),
                 references=("placeholder:1",), source_label="Placeholder", unit_ids=("u1",), topics=topics)


MORNING = _chunk("comp-morning-a#1", "ذكر تجريبي للصباح", ("occasion:morning",))
BOTH = _chunk("comp-both#1", "ذكر تجريبي للصباح والمساء", ("occasion:morning", "occasion:evening"))
EVENING = _chunk("comp-evening-a#1", "ذكر تجريبي للمساء", ("occasion:evening",))
FOOD = _chunk("comp-food#1", "دعاء تجريبي قبل الطعام", ("occasion:before_eating",))
STEPS = _chunk("comp-prayer-steps#1", "خطوة تجريبية", ("lesson:steps",), content_type="lesson")
STORY = _chunk("comp-story#1", "مشهد تجريبي", (), content_type="story")
ALL = (MORNING, BOTH, EVENING, FOOD, STEPS, STORY)


@pytest.mark.parametrize("question, wanted", [
    ("ما أذكار الصباح المتاحة؟", "occasion:morning"),
    ("ما أذكار المساء المتاحة؟", "occasion:evening"),
    ("ماذا أقول بعد الصلاة؟", "occasion:after_obligatory_prayer"),
    ("ماذا أقول قبل الطعام؟", "occasion:before_eating"),
    ("وش أقول قبل النوم؟", "occasion:before_sleep"),
    ("كيف أتعلم خطوات الصلاة؟", "lesson:steps"),
    ("كم عدد ركعات الصلوات؟", "lesson:counts"),
    ("كيف أتوضأ؟", "lesson:wudu"),
])
def test_a_question_for_words_on_an_occasion_or_a_prayer_lesson_names_its_topic(question, wanted):
    assert curated.topic(question) == wanted


@pytest.mark.parametrize("question", [
    "احكِ لي قصة آدم والتوبة",                    # a story: generated and checked as before
    "هل صلاتي باطلة لأنني نسيت التشهد؟",           # a ruling: routed before this step
    "ما فضل الصباح؟",                               # names an occasion, asks for no words
    "ماذا أقول في الصباح والمساء؟",                 # two occasions: left to retrieval
    "اذكر دعاءً محددًا لم يرد في المصادر المتاحة",  # asks for words, names no occasion
    "كم عدد ركعات صلاة التراويح؟",                  # curated-v2: a prayer the counts lesson does not teach
    "كيف أصلي صلاة العيد؟",                         # nor the steps lesson
])
def test_other_questions_have_no_curated_topic(question):
    assert curated.topic(question) is None


def test_the_items_of_the_topic_are_served_as_written_in_release_order():
    selection = curated.select("ما أذكار الصباح المتاحة؟", ALL)
    assert [chunk.id for chunk in selection.chunks] == ["comp-morning-a#1", "comp-both#1"]
    assert curated.text(selection) == "ذكر تجريبي للصباح\n\nذكر تجريبي للصباح والمساء"


def test_a_topic_with_no_eligible_item_falls_through_to_retrieval():
    assert curated.select("ماذا أقول بعد الصلاة؟", ALL) is None
    assert curated.select("ماذا أقول قبل الطعام؟", (STORY,)) is None


@pytest.mark.parametrize("question, wanted", [
    # curated-v3: the dialect phrasings children use (Gulf, Levantine, Egyptian) and Arabizi.
    ("شو أقول لما أدعي لأمي وأبوي؟", "occasion:for_parents"),
    ("شو أدعي لأهلي؟", "occasion:for_family"),
    ("وش أقول الصبح؟", "occasion:morning"),
    ("شو بنقول بعد ما نخلص الصلاة؟", "occasion:after_obligatory_prayer"),
    ("شو أقول بعد ما أخلص صلاتي؟", "occasion:after_obligatory_prayer"),
    ("شو أدعي قبل الامتحان؟", "occasion:before_difficult_task"),
    ("دعاء للامتحان", "occasion:before_difficult_task"),
    ("شو أقول لما أطلع من الجامع؟", "occasion:leaving_mosque"),
    ("شو بقول لما أعطس؟", "occasion:after_sneezing"),
    ("وش أقول قبل الغدا؟", "occasion:before_eating"),
    ("shu a2ool abl ma nam?", "occasion:before_sleep"),
    ("ازاي أصلي؟", "lesson:steps"),
    ("علمني الصلاة", "lesson:steps"),
    ("قديش ركعة الظهر؟", "lesson:counts"),
    ("كيف بتوضا؟", "lesson:wudu"),
])
def test_dialect_phrasings_name_their_topic(question, wanted):
    assert curated.topic(question) == wanted


@pytest.mark.parametrize("question", [
    "ما فضل الدعاء للوالدين؟",          # its merit
    "شو يعني أذكار الصباح؟",            # its meaning
    "ليش نقول دعاء قبل النوم؟",          # its reason
    "what is the meaning of the dua before eating?",
])
def test_a_question_about_the_words_is_not_a_request_for_them(question):
    assert curated.topic(question) is None
