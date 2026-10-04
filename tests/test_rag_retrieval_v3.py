"""hybrid-rrf-v3 (doc/rag-system.md §17): passages ahead of commentary, commentary only after its own passage,
curated child content first when about as relevant, and header phrases.

Placeholder text only: invented Arabic and English sentences in chunks typed as Quran, tafsir, translation,
story, dua or lesson, under an invented surah number (99), so that no Quran, tafsir or hadith text is written
here. The `comp-*` documents stand in for the curated child documents, which arrive with the corpus.
"""
from array import array

import pytest

from companion_api.rag import lexical, normalize, retriever as retriever_module
from companion_api.rag.chunking import embedding_text
from companion_api.rag.embeddings import HashingEmbedder
from companion_api.rag.prompts import FAITH_SYSTEM, NOT_IN_SOURCES
from companion_api.rag.release import LoadedRelease
from companion_api.rag.retriever import COMMENTARY_CONTENT, CURATED_RATIO, HybridRetriever
from companion_api.rag.service import AnswerService
from companion_api.rag.types import Chunk, ReleaseManifest


def _chunk(chunk_id, text, *, content_type="quran", language="ar", parent=None, header="", source="fixture-quran",
           ages=("7-9", "10-11"), tier=0):
    return Chunk(id=chunk_id, document_id=chunk_id.split("#")[0], kind="passage", title=header or chunk_id,
                 language=language, age_bands=ages, content_type=content_type, madhhab=(), review_status="draft",
                 synthetic=False, text=text, search_text=normalize.search_text(text, quranic=content_type == "quran"),
                 references=("placeholder:1",), source_label="Placeholder text", unit_ids=("u1",),
                 parent_id=parent, context_header=header, tier=tier, source_ids=(source,))


def _retriever(chunks):
    embedder = HashingEmbedder()
    vectors = embedder.embed_documents([embedding_text(chunk) for chunk in chunks])
    manifest = ReleaseManifest(release_id="v3-fixture", created_at="", channel="development", corpus_ids=("x",),
                               document_count=len(chunks), chunk_count=len(chunks), embedder=embedder.identity)
    release = LoadedRelease(manifest, tuple(chunks), tuple(array("f", vector) for vector in vectors))
    return HybridRetriever(release, embedder, include_drafts=True)


WELL = _chunk("quran-099-001-005#1", "ذهب الإخوة إلى البئر في الصباح\n\nوترك الإخوة أخاهم الصغير عند البئر",
              header="قصة تجريبية — سورة التجربة — الآيات 1–5")
CITY = _chunk("quran-099-006-010#1", "وسافر الإخوة إلى المدينة الكبيرة\n\nوطلبوا الطعام من العزيز",
              header="قصة تجريبية — سورة التجربة — الآيات 6–10")
OTHER = _chunk("quran-099-011-015#1", "وكان في المدينة نهر كبير وأشجار كثيرة",
               header="قصة تجريبية — سورة التجربة — الآيات 11–15")
# One long commentary on the city passage, cut into many chunks that all repeat the question's words.
BOOK_A = [_chunk(f"tafsir-a-099-006-010#{n}", f"قال المفسر منع العزيز القمح عن الإخوة في السنة {word} حتى يأتوا "
                 "بأخيهم", content_type="tafsir", parent=CITY.id, source="fixture-tafsir-a", tier=1,
                 header="تفسير تجريبي أ — سورة التجربة — الآيات 6–10")
          for n, word in enumerate(("الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة"), start=1)]
BOOK_B = _chunk("tafsir-b-099-006-010#1", "منع العزيز القمح عن الإخوة امتحانا لهم", content_type="tafsir",
                parent=CITY.id, source="fixture-tafsir-b", tier=1, header="تفسير تجريبي ب — سورة التجربة")
# The only chunk that knows the rare word «الجب» is a commentary on the well passage.
PIT = _chunk("tafsir-b-099-001-005#1", "والجب هو البئر العميقة التي لا حجارة حولها", content_type="tafsir",
             parent=WELL.id, source="fixture-tafsir-b", tier=1, header="تفسير تجريبي ب — سورة التجربة")


def _ids(retrieval):
    return [candidate.chunk.id for candidate in retrieval.candidates]


def test_passages_lead_and_one_commentary_follows_its_own_passage():
    retriever = _retriever([*BOOK_A, BOOK_B, WELL, CITY, OTHER])
    found = retriever.retrieve("لماذا منع العزيز القمح عن الإخوة؟", language="ar").candidates
    kinds = [candidate.chunk.content_type for candidate in found]
    assert found[0].chunk.id == CITY.id
    assert sum(kind in COMMENTARY_CONTENT for kind in kinds) == 1
    for before, candidate in zip(found, found[1:]):
        if candidate.chunk.content_type in COMMENTARY_CONTENT:
            assert candidate.chunk.parent_id == before.chunk.id
    assert sum(kind not in COMMENTARY_CONTENT for kind in kinds) <= retriever_module.FINAL_K
    assert retriever_module.RETRIEVER_VERSION == "hybrid-rrf-v3"


def test_under_v2_the_same_question_filled_every_place_with_commentary():
    """The regression this fixes: ranked as chunks, the six chunks of one book took all four places."""
    retriever = _retriever([*BOOK_A, BOOK_B, WELL, CITY, OTHER])
    tokens = normalize.content_tokens("لماذا منع العزيز القمح عن الإخوة؟")
    top = [retriever.release.chunks[index].content_type for index, _ in retriever._index.top(tokens, 4)]
    assert top == ["tafsir"] * 4


def test_a_passage_found_only_through_its_commentary_is_served_with_it():
    retriever = _retriever([WELL, CITY, OTHER, PIT])
    ids = _ids(retriever.retrieve("ما هو الجب؟", language="ar"))
    assert ids[:2] == [WELL.id, PIT.id]


def test_commentary_whose_passage_the_query_cannot_serve_never_serves():
    older = _chunk(WELL.id, WELL.text, header=WELL.context_header, ages=("10-11",))
    retriever = _retriever([older, CITY, OTHER, PIT])
    assert PIT.id not in _ids(retriever.retrieve("ما هو الجب؟", language="ar", age_band="7-9"))
    assert _ids(retriever.retrieve("ما هو الجب؟", language="ar", age_band="10-11"))[:2] == [WELL.id, PIT.id]
    orphan = _chunk("tafsir-c-099-001-005#1", "والجب هو البئر العميقة", content_type="tafsir", source="c", tier=1)
    assert orphan.id not in _ids(_retriever([CITY, OTHER, orphan]).retrieve("ما هو الجب؟", language="ar"))


def test_an_english_service_serves_commentary_after_the_translation_of_its_passage():
    translation = _chunk("quran-en-demo-099-001-005#1", "The brothers went to the well in the morning.",
                         content_type="quran_translation", language="en", parent=WELL.id, tier=1,
                         header="Translation of the meanings (Demo) — ayat 1–5")
    note = _chunk("tafsir-en-demo-099-001-005#1", "The pit is a deep well without stones around it.",
                  content_type="tafsir_translation", language="en", parent=WELL.id, source="fixture-tafsir-en",
                  tier=1, header="Commentary (Demo) — ayat 1–5")
    retriever = _retriever([WELL, CITY, translation, note])
    assert _ids(retriever.retrieve("What is the pit?", language="en")) == [translation.id, note.id]


STORY = _chunk("comp-story-brothers#1", "ذهب الإخوة إلى البئر في الصباح وتركوا أخاهم الصغير عند البئر",
               content_type="story", header="قصة الإخوة والبئر للأطفال", source="comp", tier=2)


def test_curated_child_content_about_as_relevant_comes_first():
    retriever = _retriever([WELL, CITY, OTHER, STORY])
    question = "ماذا فعل الإخوة عند البئر في الصباح؟"
    found = retriever.retrieve(question, language="ar").candidates
    assert found[0].chunk.id == STORY.id and WELL.id in _ids(retriever.retrieve(question, language="ar"))
    passage = next(candidate for candidate in found if candidate.chunk.id == WELL.id)
    assert found[0].score >= CURATED_RATIO * passage.score


def test_without_the_preference_the_passage_would_lead(monkeypatch):
    monkeypatch.setattr(retriever_module, "CURATED_RATIO", 2.0)
    found = _retriever([WELL, CITY, OTHER, STORY]).retrieve("ماذا فعل الإخوة عند البئر في الصباح؟", language="ar")
    assert _ids(found)[:2] == [WELL.id, STORY.id]


def test_curated_child_content_well_behind_stays_behind():
    far = _chunk("comp-lesson-river#1", "نتعلم اليوم عن النهر والأشجار في المدينة", content_type="lesson",
                 header="درس النهر", source="comp", tier=2)
    retriever = _retriever([WELL, CITY, OTHER, far])
    found = retriever.retrieve("ماذا فعل الإخوة عند البئر في الصباح؟", language="ar").candidates
    assert found[0].chunk.id == WELL.id
    behind = [candidate for candidate in found if candidate.chunk.id == far.id]
    assert not behind or behind[0].score < CURATED_RATIO * found[0].score


class _Recorder:
    model = "qwen3.5:9b"

    def __init__(self):
        self.messages = []

    def complete(self, messages, *, max_tokens, json_mode=False, temperature=None):
        self.messages.append(messages)
        return NOT_IN_SOURCES


def test_the_faith_prompt_answers_over_curated_child_content():
    generator = _Recorder()
    service = AnswerService(_retriever([WELL, CITY, OTHER, STORY]), generator, language="ar")
    plan = service.prepare("ماذا فعل الإخوة عند البئر في الصباح؟")
    assert plan.step == "generate" and plan.faith and plan.retrieval.candidates[0].chunk.id == STORY.id
    service.answer("ماذا فعل الإخوة عند البئر في الصباح؟")
    assert generator.messages[0][0]["content"] == FAITH_SYSTEM


# Header phrases -------------------------------------------------------------------------------------------

STEPS = _chunk("comp-lesson-prayer-steps#1", "نتوضأ ثم نقف في الصلاة ونقول الله أكبر\n\nوفي الصلاة نقرأ الفاتحة "
               "ثم نركع ونقول سبحان ربي العظيم", content_type="lesson", header="خطوات الصلاة للأطفال",
               source="comp", tier=2)
AFTER = _chunk("comp-dua-after-prayer#1", "أستغفر الله ثلاث مرات\n\nاللهم أنت السلام ومنك السلام",
               content_type="dua", header="أذكار بعد الصلاة", source="comp", tier=2)


def test_phrases_pair_one_function_word_with_one_content_word():
    assert "بعد الصلاه" in lexical.phrases("ماذا أقول بعد الصلاة؟")
    assert lexical.phrases("فصبر جميل") == []          # two content words: BM25 already reads both
    assert lexical.phrases("في من") == []                # two function words mean nothing
    assert lexical.header_phrases(AFTER) == ["اذكار بعد", "بعد الصلاه"]


# Passages that share the question's words ("أقول", "الصلاة") but say nothing after the prayer.
SAYINGS = [_chunk(f"quran-099-{n:03d}-{n:03d}#1", f"قال الرجل {word} أقول لكم الحق في الصلاة وفي السوق",
                  header=f"قصة تجريبية — سورة التجربة — الآية {n}")
           for n, word in enumerate(("اسمعوا", "انتبهوا", "تعالوا", "اجلسوا", "قوموا", "انظروا"), start=20)]


def test_a_header_phrase_brings_the_adhkar_after_the_prayer_into_the_prompt(monkeypatch):
    question = "ماذا أقول بعد الصلاة؟"
    chunks = [STEPS, AFTER, *SAYINGS]
    found = _retriever(chunks).retrieve(question, language="ar")
    assert AFTER.id in _ids(found) and found.candidates[0].bm25 > 0
    monkeypatch.setattr(retriever_module, "phrases", lambda text: [])
    assert AFTER.id not in _ids(_retriever(chunks).retrieve(question, language="ar"))


@pytest.mark.parametrize("question", ["ماذا أقول قبل الصلاة؟", "ماذا أقول في الصلاة؟"])
def test_a_header_phrase_the_question_does_not_hold_changes_nothing(question, monkeypatch):
    chunks = [STEPS, AFTER, *SAYINGS]
    with_phrases = _ids(_retriever(chunks).retrieve(question, language="ar"))
    monkeypatch.setattr(retriever_module, "phrases", lambda text: [])
    assert with_phrases == _ids(_retriever(chunks).retrieve(question, language="ar"))
