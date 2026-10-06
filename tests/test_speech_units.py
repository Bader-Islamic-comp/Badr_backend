"""The speech preview's deterministic parts (ADR 0006): the letter check, text preparation, copy, the
diacritization prompt, attempt mapping, the dua split and the client's error handling."""
import asyncio
import unicodedata

import httpx
import pytest

from companion_api.rag import checks, grounding, never
from companion_api.rag.generator import GenerationError
from companion_api.speech import adhkar, arabic, child_copy, diacritize, duas, recitation, textprep
from companion_api.speech.client import (SpeechBusy, SpeechClient, SpeechConflict, SpeechNotFound, SpeechRejected,
                                         SpeechTooLarge, SpeechUnavailable)
from http_probe import recording_server, route_through
from speech_fake import SPEECH_TOKEN, SPEECH_URL

FATHA, DAMMA, KASRA, SHADDA, SUKUN = "\u064e", "\u064f", "\u0650", "\u0651", "\u0652"
FATHATAN, DAGGER_ALEF, TATWEEL = "\u064b", "\u0670", "\u0640"
HAMZA_ABOVE, MADDAH, SMALL_HIGH_SEEN = "\u0654", "\u0653", "\u06dc"


# The letter check --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("original, diacritized", [
    ("كتب الولد", "كَتَبَ الْوَلَدُ"),
    ("محمد", "مُحَمَّدٌ"),                                              # shadda and tanween
    ("هذا", "هٰذَا"),                                                    # dagger alef
    ("سلام", "سَـلَامٌ"),                                                 # tatweel added
    ("مرحبا  بك", " مَرْحَبًا بِكَ "),                                    # white space collapsed
    ("الحمد لله", unicodedata.normalize("NFD", "الْحَمْدُ لِلَّهِ")),     # decomposed marks
    ("أنا", "ا" + HAMZA_ABOVE + FATHA + "نَا"),                          # combining hamza composes to the letter
    ("مَرحبا", "مَرْحَبًا"),                                             # marks already in the input
    ("أهلًا، كيف حالك؟", "أَهْلًا، كَيْفَ حَالُكَ؟"),                    # punctuation kept
])
def test_adding_marks_keeps_the_letters(original, diacritized):
    assert arabic.same_letters(original, diacritized)


@pytest.mark.parametrize("original, diacritized", [
    ("كتب", "كَتَبَتْ"),                       # a letter added
    ("كتبت", "كَتَبَ"),                        # a letter removed
    ("قلم", "قَلَمٌ جَمِيلٌ"),                  # a word added
    ("اكبر", "أَكْبَرُ"),                       # a hamza added is a changed letter
    ("أكبر", "اَكْبَرُ"),                       # and so is one removed
    ("انا", "ا" + HAMZA_ABOVE + "نَا"),         # even as a combining mark
    ("هذه", "هَذِهِ."),                          # punctuation added
    ("مرحبا بك", "مَرْحَبًابِكَ"),              # a space removed joins two words
    ("قال", "قَالَ" + SMALL_HIGH_SEEN),          # a Quranic annotation mark is not removable
    ("ءامن", "آمَنَ"),                           # maddah is a different letter
    ("رحمة", "رَحْمَه"),                         # ta marbuta is not ha
    ("", ""),
    ("Hello", "Hello"),                         # nothing Arabic to check
])
def test_any_letter_change_is_refused(original, diacritized):
    assert not arabic.same_letters(original, diacritized)


def test_the_removable_marks_are_exactly_the_harakat_dagger_alef_and_tatweel():
    removable = {chr(code) for code in range(0x0600, 0x0700) if arabic.MARKS.fullmatch(chr(code))}
    assert removable == {chr(code) for code in range(0x064B, 0x0653)} | {DAGGER_ALEF, TATWEEL}
    assert arabic.letters("ب" + FATHA + SHADDA + "ـ" + SUKUN + KASRA + DAMMA + FATHATAN) == "بـ".replace("ـ", "")


# Text preparation ---------------------------------------------------------------------------------------------

def test_the_quote_pattern_is_the_checks_pattern():
    assert textprep.QUOTES.pattern == checks._QUOTE.pattern == grounding._QUOTES.pattern


@pytest.mark.parametrize("quoted", ["«الحمد لله»", '"الحمد لله"', "“الحمد لله”", "‘الحمد لله’", "﴿الحمد لله﴾",
                                    "﴾الحمد لله﴿"])
def test_a_sentence_with_a_quotation_is_never_spoken(quoted):
    text = f"مرحبًا يا صديقي. قل {quoted} عندما تعطس. هذا جميل."
    assert textprep.speakable_parts(text) == ["مرحبًا يا صديقي. هذا جميل."]


def test_a_quotation_spanning_sentences_is_dropped_whole():
    text = "قصة جميلة. قال: «جملة أولى. جملة ثانية. جملة ثالثة» ثم سكت. انتهت القصة."
    assert textprep.speakable_parts(text) == ["قصة جميلة. انتهت القصة."]


@pytest.mark.parametrize("text", ["قال «الحمد لله. انتهى.", "قال الحمد لله» ثم سكت.", 'جملة "مفتوحة. وأخرى.'])
def test_an_unmatched_quote_mark_means_nothing_is_spoken(text):
    assert textprep.speakable_parts(text) == []


def test_citations_references_and_source_lists_are_removed():
    text = ("الصبر جميل [1]. نتعلم الصبر من القصص [2, 3] (البقرة: 153) كل يوم (٢:١٥٣).\n"
            "المصادر: قصص الأنبياء، الصفحة الأولى.")
    assert textprep.speakable_parts(text) == ["الصبر جميل. نتعلم الصبر من القصص كل يوم."]
    assert textprep.speakable_parts("جملة.\nSources: something") == ["جملة."]


def test_latin_and_non_arabic_sentences_are_dropped():
    text = "Hello there. مرحبًا! I am Robert. أنا روبرت من team Badr. 123. 🙂 ؟ كيف حالك؟"
    assert textprep.speakable_parts(text) == ["مرحبًا! كيف حالك؟"]


def test_parts_are_merged_bounded_and_at_most_six():
    short = textprep.speakable_parts("جملة أولى. جملة ثانية. جملة ثالثة.")
    assert short == ["جملة أولى. جملة ثانية. جملة ثالثة."]
    long_sentence = "، ".join(["كلمات كثيرة في جملة طويلة جدًا"] * 12) + "."
    parts = textprep.speakable_parts(long_sentence)
    assert all(len(part) <= textprep.MAX_PART_CHARS for part in parts) and len(parts) >= 3
    assert " ".join(parts).replace("، ", "،").replace(" ", "") == long_sentence.replace("، ", "،").replace(" ", "")
    unbroken = "كلمة " * 80
    assert all(len(part) <= 140 for part in textprep.speakable_parts(unbroken))
    many = " ".join(f"هذه الجملة رقم {index} وهي طويلة بما يكفي لتملأ جزءًا كاملًا من الأجزاء المسموعة هنا "
                    "مع كلمات إضافية كثيرة." for index in "ابتثجحخد")
    assert len(textprep.speakable_parts(many)) == textprep.MAX_PARTS


# Copy -------------------------------------------------------------------------------------------------------

def test_new_child_facing_copy_has_no_banned_word_and_breaks_no_must_never_rule():
    lines = child_copy.child_facing()
    assert len(lines) == 3 + 12
    for line in lines:
        folded = line.casefold()
        assert not any(word.casefold() in folded for word in child_copy.BANNED), line
        assert child_copy.is_gentle(line), line
        assert never.violations(line) == (), line
    assert adhkar.REVIEW_STATUS == "draft"


@pytest.mark.parametrize("line", ["هذا غلط", "فيه خطأ بسيط", "فشلت المحاولة", "قراءتك ما قُبل", "ما قبل منك",
                                  "هذا باطل", "لا يصح هذا", "ما بتنحسب", "مرفوض", "That was WRONG", "You failed",
                                  "invalid", "Rejected.", "incorrect", "a small mistake", "صلاتك صحيحة",
                                  "your prayer doesn't count", ""])
def test_a_feedback_line_that_judges_is_refused(line):
    assert not child_copy.is_gentle(line)


@pytest.mark.parametrize("line", ["ما شاء الله، أحسنت!", "لا بأس، جرّب مرة ثانية ببطء.", "تقبل الله منك",
                                  "أنت بتتحسن! جرّب مرة كمان."])
def test_a_gentle_line_passes(line):
    assert child_copy.is_gentle(line)


def test_the_adhkar_are_the_speech_service_allowlist():
    assert adhkar.ADHKAR_IDS == ("takbeer", "tasbeeh", "tahmeed", "istighfar")
    assert [arabic.letters(item["text"]) for item in adhkar.ADHKAR] == [
        "الله أكبر", "سبحان الله", "الحمد لله", "أستغفر الله"]
    assert all(arabic.same_letters(arabic.letters(item["text"]), item["text"]) for item in adhkar.ADHKAR)
    assert adhkar.dua_id("takbeer") == "dhikr-takbeer"


# The diacritization prompt ---------------------------------------------------------------------------------------

class RecordingGenerator:
    def __init__(self, reply="نَصٌّ", error=False):
        self.reply, self.error, self.calls = reply, error, []

    def complete(self, messages, *, max_tokens, json_mode=False, temperature=None):
        self.calls.append({"messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                           "json_mode": json_mode})
        if self.error:
            raise GenerationError("generation endpoint timed out (ReadTimeout)")
        return self.reply


def test_the_diacritizer_asks_for_marks_only_at_temperature_zero():
    generator = RecordingGenerator("  نَصٌّ  ")
    model = diacritize.LlmDiacritizer(generator)
    assert model.prompt_id == diacritize.PROMPT_ID == "diacritize-v1"
    assert model.diacritize("نص") == "نَصٌّ"
    call = generator.calls[0]
    assert call["temperature"] == 0.0 and call["json_mode"] is False
    assert call["messages"] == [{"role": "system", "content": diacritize.SYSTEM}, {"role": "user", "content": "نص"}]
    assert diacritize.LlmDiacritizer(RecordingGenerator(error=True)).diacritize("نص") is None


# Attempt mapping ------------------------------------------------------------------------------------------------

def _scored(*states):
    return {"status": "scored", "abstainReason": None, "feedbackCopyId": "x",
            "words": [{"index": index, "state": state, "confidence": "high"} for index, state in enumerate(states)]}


@pytest.mark.parametrize("data, outcome, counts", [
    (_scored("clear"), "clear", True),
    (_scored("clear", "try_again"), "try_again", True),
    (_scored("unsure"), "try_again", True),
    (_scored(), "unsure", True),                                     # scored with nothing: any doubt abstains
    ({"status": "abstained", "abstainReason": "low_confidence", "words": []}, "unsure", True),
    ({"status": "abstained", "abstainReason": "off_script", "words": []}, "unsure", False),
    ({"status": "abstained", "abstainReason": "audio_quality", "words": []}, "unsure", False),
    ({"status": "abstained", "abstainReason": "too_long", "words": []}, "unsure", False),
    ({"status": "abstained", "abstainReason": "service_unavailable", "words": []}, "unsure", False),
])
def test_attempt_outcomes_and_what_counts(data, outcome, counts):
    result = recitation.read_attempt(data)
    assert (result.outcome, result.counts) == (outcome, counts)


@pytest.mark.parametrize("data", [{}, {"status": "weird"}, _scored("perfect"), {"status": "scored", "words": [{}]}])
def test_an_unexpected_attempt_body_is_unavailable(data):
    with pytest.raises(SpeechUnavailable):
        recitation.read_attempt(data)


def test_words_are_shown_only_on_the_first_three_scored_attempts():
    result = recitation.read_attempt(_scored("clear", "try_again"))
    feedback = {"copyId": "x", "text": "t", "audio": False}
    assert recitation.response(result, 3, feedback)["showWords"] is True
    assert recitation.response(result, 4, feedback) == {"outcome": "try_again", "words": [], "showWords": False,
                                                        "feedback": feedback}


# The dua split ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, clauses", [
    ("اللهم بك أصبحنا، وبك أمسينا، وإليك النشور", ["اللهم بك أصبحنا", "وبك أمسينا", "وإليك النشور"]),
    ("أولى؛ ثانية،ثالثة", ["أولى", "ثانية", "ثالثة"]),
    ("سبحان الله 33 مرة، ثم: لا إله إلا الله", ["سبحان الله 33 مرة", "لا إله إلا الله"]),
    ("، ، أولى،، ثانية.، ", ["أولى", "ثانية"]),
    ("نص واحد", ["نص واحد"]),
])
def test_clauses_split_as_the_speech_service_export_does(text, clauses):
    assert duas.split_clauses(text) == clauses
    assert [clause for _start, _end, clause in duas._clause_spans(text)] == clauses


def test_clauses_merge_up_to_twelve_words_in_order():
    text = "واحد اثنان ثلاثة، أربعة خمسة ستة سبعة، ثمانية تسعة عشرة أحد عشر اثنا، عشر"
    assert duas.segments(text) == [("واحد اثنان ثلاثة، أربعة خمسة ستة سبعة", 7), ("ثمانية تسعة عشرة أحد عشر اثنا، عشر", 7)]
    assert duas.segments("أ ب ج، د ه و") == [("أ ب ج، د ه و", 6)]
    assert duas.word_count("الْحَمْدُ  لِلَّهِ!") == 2


def test_only_hadith_invocations_with_matching_counts_get_segments():
    catalogue = duas.DuaCatalogue()
    morning, parents = catalogue.get("morning-by-god"), catalogue.get("dua-parents")
    assert morning.verified_segments([11]) == ["اللهم بك أصبحنا، وبك أمسينا، وبك نحيا، وبك نموت، وإليك النشور"]
    assert morning.verified_segments([3, 8]) == [] and morning.verified_segments(None) == []
    assert parents.kind == "quran_recitation" and parents.verified_segments([9]) == []
    assert catalogue.status == "draft" and len(catalogue.items()) == 22


def test_after_prayer_tasbih_gets_no_segments_and_that_is_the_safe_answer():
    # The speech service's registry spells "33" out («ثلاث وثلاثون») and keeps «مرة» in the words it scores, so its
    # segments (word counts 10, 5, 8, 9) are not the backend's (12, 8, 9). No segments is right: "33 مرة" says how
    # often to repeat the dhikr, it is not something a child recites, so no segment should score it.
    tasbih = duas.DuaCatalogue().get("after-prayer-tasbih")
    found = duas.segments(tasbih.text)
    assert [words for _text, words in found] == [12, 8, 9]
    assert "33 مرة" in found[0][0]
    assert tasbih.verified_segments([10, 5, 8, 9]) == []
    assert "exactly as" not in duas.__doc__ and "33 مرة" in duas.__doc__


# The client -------------------------------------------------------------------------------------------------------

def _client(handler, **options):
    return SpeechClient(SPEECH_URL, SPEECH_TOKEN, transport=httpx.MockTransport(handler), backoff=(0, 0), **options)


@pytest.mark.parametrize("status, body, error", [
    (503, {"detail": {"error": "speech_queue_full"}}, SpeechBusy),
    (503, {"detail": {"error": "model_loading"}}, SpeechUnavailable),
    (500, {"error": "internal_error"}, SpeechUnavailable),
    (401, {"detail": {"error": "unauthorized"}}, SpeechUnavailable),
    (404, {"detail": {"error": "dua_or_segment_not_found"}}, SpeechNotFound),
    (400, {"detail": {"error": "dua_registry_match", "detail": "text matches"}}, SpeechRejected),
    (409, {"detail": {"error": "dua_version_mismatch"}}, SpeechConflict),
    (413, {"detail": {"error": "audio_too_large"}}, SpeechTooLarge),
    (422, {"detail": [{"msg": "child text echoed"}]}, SpeechUnavailable),
])
def test_service_errors_become_fixed_codes(status, body, error):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)
    with pytest.raises(error) as raised:
        asyncio.run(_client(handler).attempt("dhikr-takbeer", "1", 0, 1, b"RIFF"))
    assert "child text" not in str(raised.value)
    assert len(calls) == (3 if error is SpeechBusy else 1)


def test_the_client_sends_the_token_and_raw_audio_and_caches_lists_for_a_minute():
    seen, now = [], [0.0]

    def handler(request):
        seen.append((request.method, request.url.path, request.headers.get("x-speech-token"),
                     request.headers.get("content-type")))
        return httpx.Response(200, json={"items": []})
    client = _client(handler, clock=lambda: now[0])

    async def run():
        await client.duas()
        await client.duas()
        now[0] = 61.0
        await client.duas()
        await client.transcribe(b"RIFF....WAVE", "ar")
        await client.aclose()
    asyncio.run(run())
    assert [entry[:2] for entry in seen] == [("GET", "/v1/duas"), ("GET", "/v1/duas"), ("POST", "/v1/transcribe")]
    assert all(entry[2] == SPEECH_TOKEN for entry in seen) and seen[-1][3] == "audio/wav"


def test_an_unreachable_or_odd_service_is_unavailable():
    def down(request):
        raise httpx.ConnectTimeout("timed out")
    with pytest.raises(SpeechUnavailable):
        asyncio.run(_client(down).capabilities())
    with pytest.raises(SpeechUnavailable):
        asyncio.run(_client(lambda request: httpx.Response(200, content=b"not json")).capabilities())
    with pytest.raises(SpeechUnavailable):
        asyncio.run(_client(lambda request: httpx.Response(200, json=[1, 2])).capabilities())
    huge = httpx.Response(200, content=b"x" * (9 * 1024 * 1024))
    with pytest.raises(SpeechUnavailable):
        asyncio.run(_client(lambda request: huge).render("نَصٌّ", "momen-dev"))


def test_the_client_refuses_a_public_address():
    with pytest.raises(ValueError):
        SpeechClient("http://8.8.8.8:8100", SPEECH_TOKEN)
    assert SPEECH_TOKEN not in repr(SpeechClient(SPEECH_URL, SPEECH_TOKEN))


def test_the_client_never_goes_through_a_proxy(monkeypatch):
    # HTTP_PROXY would hand the token and the child's recording to whatever the proxy is, defeating
    # require_private_endpoint: the speech service is always called directly.
    with recording_server({"sttEnabled": True}) as (service, reached), \
            recording_server({"sttEnabled": True}) as (proxy, proxied):
        route_through(monkeypatch, proxy)
        client = SpeechClient(service, SPEECH_TOKEN)

        async def run():
            await client.capabilities()
            await client.transcribe(b"RIFF....WAVE", "ar")
            await client.aclose()
        asyncio.run(run())
    assert proxied == []
    assert reached == [("GET", "/v1/capabilities"), ("POST", "/v1/transcribe?language=ar")]
