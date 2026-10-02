"""test/corpus-tasks-serving: the post-generation checks (checks-v1), the scene check and English answers over
translations of the meanings.

Placeholder text only: invented Arabic and English sentences in passages typed as Quran, translation or
hadith, under an invented surah number (99), so that no Quran or hadith text is written here. Real episode
data (data/episodes.json) is used only where a test says so.
"""
from array import array
import json
import logging
from pathlib import Path

import pytest

from companion_api.rag import arabizi, checks, responses, router
from companion_api.rag.ayahs import AyahIndex
from companion_api.rag.checks import Answer, Verifier, addressee_mismatches, asks_for, gives
from companion_api.rag.embeddings import HashingEmbedder
from companion_api.rag.grounding import Segment, verify
from companion_api.rag.prompts import FAITH_SYSTEM, FAITH_SYSTEM_EN, build_messages
from companion_api.rag.release import LoadedRelease
from companion_api.rag.retriever import HybridRetriever
from companion_api.rag.scene import Episode, Episodes, check_scene, load_episodes
from companion_api.rag.service import AnswerService
from companion_api.rag.types import Chunk, ReleaseManifest

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "corpus" / "eval"
OK_VERDICT = '{"answers_question": true, "supported": true, "speaker_ok": true}'

# An invented story of "yusuf" in surah 99: ayahs 1-5 are the well, 6-10 the journey to the city.
WELL = ("ذهب الإخوة إلى البئر في الصباح",
        "وترك الإخوة يوسف الصغير عند البئر",
        "وجاء الإخوة إلى أبيهم في المساء يبكون",
        "قالوا يا أبانا ذهبنا نلعب وتركناه عند المتاع",
        "قال أبوهم صبر جميل والله المستعان")
CITY = ("وسافر الإخوة إلى المدينة الكبيرة",
        "وطلبوا القمح من العزيز في السوق",
        "وقال العزيز ائتوني بأخيكم الصغير",
        "فلما رجعوا إلى أبيهم قالوا منع منا القمح",
        "فأرسل معنا أخانا لنحمل القمح الكثير")


def _chunk(chunk_id, text, *, content_type="quran", language="ar", refs=(), prophet=None, title=None,
           source_label="Placeholder text"):
    return Chunk(id=chunk_id, document_id=chunk_id.split("#")[0], kind="passage",
                 title=title or "سورة التجربة 99:1–5", language=language, age_bands=("7-9", "10-11"),
                 content_type=content_type, madhhab=(), review_status="draft", synthetic=False, text=text,
                 search_text=__import__("companion_api.rag.normalize", fromlist=["x"]).search_text(
                     text, quranic=content_type == "quran"),
                 references=tuple(refs) or ("placeholder:1",), source_label=source_label, unit_ids=("u1",),
                 source_ids=("fixture-source",), source_refs=tuple(refs), prophet_id=prophet)


WELL_CHUNK = _chunk("quran-099-001-005#1", "\n\n".join(WELL), refs=[f"quran:99:{n}" for n in range(1, 6)],
                    prophet="yusuf")
CITY_CHUNK = _chunk("quran-099-006-010#1", "\n\n".join(CITY), refs=[f"quran:99:{n}" for n in range(6, 11)],
                    prophet="yusuf", title="سورة التجربة 99:6–10")
HADITH = _chunk("hadith-fixture-1#1", "قال النبي صلى الله عليه وسلم الكلمة الطيبة صدقة", content_type="hadith",
                title="حديث تجريبي")
EPISODES = Episodes([Episode("yusuf", 99, 1, 5, "الإخوة والبئر", "the brothers and the well"),
                     Episode("yusuf", 99, 6, 10, "قدوم الإخوة", "the brothers come to the city"),
                     Episode("ibrahim", 98, 1, 5, "الحوار مع أبيه", "talking with his father"),
                     Episode("ibrahim", 98, 6, 10, "الدعاء للمدينة", "the prayer for the city")])
FATHER = _chunk("quran-098-001-005#1", "\n\n".join((
    "وقال الفتى لأبيه يا أبت لماذا تحب الحجارة", "قال أبوه سأفكر في كلامك", "وذهب الفتى إلى السوق",
    "ورأى الناس هناك", "ثم رجع إلى البيت")), refs=[f"quran:98:{n}" for n in range(1, 6)], prophet="ibrahim")
PRAYER = _chunk("quran-098-006-010#1", "\n\n".join((
    "وقال الفتى رب اجعل المدينة سعيدة", "رب اجعل أهلها كرماء", "ووقف الفتى عند البيت القديم",
    "ونظر إلى السماء طويلا", "ثم نام تحت الشجرة")), refs=[f"quran:98:{n}" for n in range(6, 11)], prophet="ibrahim")
AYAHS = AyahIndex([WELL_CHUNK, CITY_CHUNK, FATHER, PRAYER, HADITH])


def answer(question, text, cited, faith_topic=False):
    return Answer(question, text, (Segment(text, tuple(chunk.id for chunk in cited)),), tuple(cited), faith_topic)


# The pipeline ------------------------------------------------------------------------------------------------

class Judge:
    model = "qwen3.5:9b"

    def __init__(self, verdict=OK_VERDICT):
        self.verdict, self.calls = verdict, 0

    def complete(self, messages, *, max_tokens, json_mode=False, temperature=None):
        self.calls += 1
        return self.verdict


def test_every_deterministic_check_runs_in_order_and_the_judge_last():
    judge = Judge()
    results, failure = Verifier(EPISODES, AYAHS).run(
        answer("ماذا قال الإخوة لأبيهم عند البئر؟", "قال الإخوة يا أبانا ذهبنا نلعب.", [WELL_CHUNK]), judge)
    assert [result.name for result in results] == ["first_person", "faith_terms", "answered", "addressee", "scene",
                                                   "translation", "judge"]
    assert failure is None and judge.calls == 1 and all(result.status == "pass" for result in results)
    assert checks.summary(results)["faith_terms"] == "pass:not_applicable"


def test_a_failed_deterministic_check_decides_and_saves_the_model_call():
    judge = Judge()
    results, failure = Verifier(EPISODES, AYAHS).run(
        answer("كم أخًا ذهب إلى البئر؟", "ذهب الإخوة إلى البئر.", [WELL_CHUNK]), judge)
    assert failure == "answered:no_quantity" and judge.calls == 0
    assert [result.name for result in results][-1] == "translation"  # recorded, judge not run


def test_the_judge_still_decides_last_and_is_unavailable_without_a_model():
    item = answer("ماذا قال الإخوة لأبيهم؟", "قال الإخوة يا أبانا ذهبنا نلعب.", [WELL_CHUNK])
    _, failure = Verifier(EPISODES, AYAHS).run(item, Judge('{"answers_question": false, "supported": true, '
                                                           '"speaker_ok": true}'))
    assert failure == "judge:answers_question"
    results, failure = Verifier(EPISODES, AYAHS).run(item, None)
    assert failure is None and results[-1].code() == "unavailable:no_model"


# answered ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("question, wanted", [
    ("كم سنة بقي الفتى في المدينة؟", "quantity"), ("قديش ضل الفتى بالمدينة؟", "quantity"),
    ("2adeish dal el walad bel madine?", "quantity"), ("kam sana 2a3ad hunak?", "quantity"),
    ("How many years did he stay?", "quantity"), ("How long did he call them?", "quantity"),
    ("متى رجع الإخوة؟", "time"), ("emta reje3 el walad, bel leil walla bel nhar?", "time"),
    ("Robert, when did they come back?", "time"), ("When did they come back?", "time"),
    ("What did they say when they came back?", None), ("ماذا قالوا لما رجعوا؟", None),
])
def test_questions_for_a_quantity_or_a_time_are_recognised(question, wanted):
    assert asks_for(question) == wanted


def test_an_answer_must_give_a_number_a_duration_or_a_time():
    assert gives("بقي فيهم ألف سنة إلا خمسين عاما.", "quantity")
    assert gives("دعاهم ليلًا ونهارًا.", "time") and gives("He stayed there 950 years.", "quantity")
    assert gives("They came back after the sun had set.", "time") and gives("رجعوا بعد أن غابت الشمس.", "time")
    assert not gives("دعا ربه أن يغفر له.", "quantity") and not gives("He prayed to his Lord.", "quantity")
    assert not gives("رجعوا بعد أن غابت الشمس.", "quantity")


# addressee -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, found", [
    ("قال الفتى لأبيه: «رَبِّ اجْعَلِ الْمَدِينَةَ سَعِيدَةً».", [("father", "lord")]),
    ("قال الفتى لأبيه «يَـٰٓأَبَتِ لِمَاذَا تُحِبُّ الْحِجَارَةَ».", []),
    ("قال الفتى لأبيه «يا أبت لماذا تحب الحجارة».", []),
    ("قال الفتى لابنه «يا أبت لماذا تحب الحجارة».", [("children", "father")]),
    ("قال نوح لقومه «يَـٰقَوْمِ اسمعوا».", []),
    ("دعا الفتى ربه «رب اجعل المدينة سعيدة».", []),
    ("قال الفتى «رب اجعل المدينة سعيدة».", []),            # no addressee named: nothing to compare
    ("قال موسى لفرعون «يا موسى اذهب».", [("pharaoh", "prophet:musa")]),
    ("قال الفتى لأبيه «ربي يحب الكرماء».", []),             # "ربي" opening a quotation is a statement
    ('He said to his father: "O my Lord, make the city happy."', [("father", "lord")]),
    ('He said to his father: "O my father, why do you love stones?"', []),
    ('The boy said to his people: "O my people, listen."', []),
])
def test_a_quotation_framed_as_said_to_someone_must_address_them(text, found):
    assert addressee_mismatches(text) == found


# scene ---------------------------------------------------------------------------------------------------------

def _scene(question, text, cited, episodes=EPISODES, ayahs=AYAHS, language="ar"):
    return check_scene(question, question, [text], cited, language, episodes, ayahs)


def test_an_answer_from_another_episode_that_never_names_the_asked_person_fails():
    question = "كيف كلم الفتى أباه عن الحجارة؟"
    assert _scene(question, "قال الفتى رب اجعل المدينة سعيدة.", [PRAYER]).reason == "other_episode"
    assert _scene(question, "قال الفتى يا أبت لماذا تحب الحجارة.", [FATHER]).status == "pass"


def test_another_episode_passes_when_its_ayahs_name_the_person():
    # The city episode is not the well, but its ayahs name the father: the episode word alone decides nothing.
    finding = _scene("ماذا قال الإخوة لأبيهم عند البئر؟", "قالوا منع منا القمح.", [CITY_CHUNK])
    assert finding.status == "pass"


def test_a_scene_defined_by_an_absent_person_needs_ayahs_that_name_him():
    question = "ماذا قال الإخوة لأبيهم لما رجعوا بدون يوسف؟"
    wrong = _scene(question, "قالوا منع منا القمح فأرسل معنا أخانا.", [CITY_CHUNK])
    right = _scene(question, "قالوا يا أبانا ذهبنا نلعب وتركناه عند المتاع.", [WELL_CHUNK])
    assert (wrong.status, wrong.reason, right.status) == ("fail", "absent_person", "pass")
    arabizi_question = "shu 2alo el ekhwe la abuhom lama rij3o bdoon yusuf?"
    assert check_scene(arabizi_question, arabizi.expand(arabizi_question).query, ["قالوا منع منا القمح."],
                       [CITY_CHUNK], "ar", EPISODES, AYAHS).reason == "absent_person"


def test_the_scene_check_says_when_it_cannot_judge():
    assert _scene("ما الكلمة الطيبة؟", "الكلمة الطيبة صدقة.", [HADITH]).reason == "not_applicable"
    assert _scene("ماذا قال الإخوة؟", "قالوا يا أبانا.", [WELL_CHUNK], episodes=None).status == "unavailable"
    outside = _chunk("quran-097-001-002#1", "نص تجريبي أول\n\nنص تجريبي ثان", refs=["quran:97:1", "quran:97:2"])
    assert _scene("ماذا قال الإخوة؟", "نص تجريبي أول.", [outside]).reason == "outside_episodes"


def test_the_episode_map_is_up_to_date_and_holds_ranges_and_labels_only():
    import importlib.util
    script = ROOT / "scripts" / "export_episodes.py"
    spec = importlib.util.spec_from_file_location("export_episodes", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = ROOT / "src/companion_api/rag/data/episodes.json"
    assert path.read_text(encoding="utf-8") == module.render(module.build()), "run python scripts/export_episodes.py"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert {key for item in data["episodes"] for key in item} == {"prophet", "ref", "surah", "first", "last",
                                                                  "label_ar", "label_en", "verification"}
    assert len(load_episodes().episodes) == len(data["episodes"]) == 59


# The service -------------------------------------------------------------------------------------------------------

class Generator:
    """The grounded call returns `answer`; JSON-mode calls (the judge) return a passing verdict."""
    model = "qwen3.5:9b"

    def __init__(self, answer="NOT_IN_SOURCES"):
        self.answer, self.messages, self.modes = answer, [], []

    def complete(self, messages, *, max_tokens, json_mode=False, temperature=None):
        self.messages.append(messages)
        self.modes.append("json" if json_mode else "text")
        if json_mode:
            return OK_VERDICT
        return self.answer(messages) if callable(self.answer) else self.answer


def _release(chunks):
    embedder = HashingEmbedder()
    vectors = embedder.embed_documents([f"{chunk.title}\n{chunk.text}" for chunk in chunks])
    manifest = ReleaseManifest(release_id="checks-1", created_at="", channel="development", corpus_ids=("x",),
                               document_count=len(chunks), chunk_count=len(chunks), embedder=embedder.identity)
    return LoadedRelease(manifest, tuple(chunks), tuple(array("f", vector) for vector in vectors))


def _service(chunks, generator, language="ar"):
    service = AnswerService(HybridRetriever(_release(chunks), HashingEmbedder(), include_drafts=True), generator,
                            language=language)
    service.verifier = Verifier(EPISODES, service.ayahs)
    return service


def test_faith_answers_record_every_check_in_provenance_and_codes_only_on_the_log(caplog):
    def reply(messages):
        number = 1 + [block for block in messages[1]["content"].split("<source ")[1:]].index(
            next(block for block in messages[1]["content"].split("<source ")[1:] if "الصباح" in block))
        return f"ذهب الإخوة إلى البئر في الصباح [{number}]."

    with caplog.at_level(logging.INFO, logger="companion_api.rag"):
        result = _service([WELL_CHUNK, CITY_CHUNK], Generator(reply)).answer("كم أخًا ذهب إلى البئر في الصباح؟")
    assert (result.answer_type, result.reason) == ("abstained", "faith_abstain:answered:no_quantity")
    assert {check.name: check.status for check in result.checks}["answered"] == "fail"
    line = json.loads(caplog.records[-1].getMessage().split(" ", 1)[1])
    assert line["checks"]["answered"] == "fail:answered:no_quantity" and line["checks_version"] == "checks-v1"
    assert "الصباح" not in caplog.text and "البئر" not in caplog.text


# English answers over translations of the meanings -----------------------------------------------------------------

TRANSLATION = _chunk("quran-en-099-001-002#1",
                     "The brothers went to the well in the morning.\n\nThe brothers left the young boy by the well.",
                     content_type="quran_translation", language="en", refs=["quran:99:1", "quran:99:2"],
                     title="Surah 99 (placeholder) 99:1–2", source_label="Placeholder International · quran:99:1–2")


def _english(answer):
    return _service([TRANSLATION], Generator(answer), language="en")


def test_english_faith_questions_get_the_english_faith_prompt_with_the_translation_named():
    generator = Generator()
    _service([TRANSLATION], generator, language="en").answer("Where did the brothers go in the morning?")
    system, user = generator.messages[0][0]["content"], generator.messages[0][1]["content"]
    assert system == FAITH_SYSTEM_EN and 'translation="Placeholder International"' in user
    assert "translation of the meanings" in system and "third person" in system
    assert build_messages("ما هذا؟", [WELL_CHUNK], faith=True)[0]["content"] == FAITH_SYSTEM  # Arabic unchanged


def test_a_named_translation_quoted_word_for_word_is_released():
    result = _english('In the translation of the meanings (Placeholder International): "The brothers went to '
                      'the well in the morning." [1]').answer("Where did the brothers go in the morning?")
    assert result.answer_type == "grounded" and result.citations == ("quran-en-099-001-002#1",)
    assert {check.name: check.code() for check in result.checks}["translation"] == "pass"


@pytest.mark.parametrize("output, reason", [
    ('The Quran says: "The brothers went to the well in the morning." [1]', "faith_abstain:translation:unframed"),
    ('In the translation of the meanings: "The brothers went to the well in the morning." [1]',
     "faith_abstain:translation:unnamed"),
    ('In the translation of the meanings (Placeholder International): "The brothers ran to the well in the '
     'morning." [1]', "faith_abstain:grounding:misquoted"),
])
def test_a_translation_presented_as_the_quran_or_misquoted_is_withheld(output, reason):
    result = _english(output).answer("Where did the brothers go in the morning?")
    assert (result.answer_type, result.text, result.reason) == ("abstained", responses.ABSTAIN_FAITH, reason)
