"""The scene check: a faith answer must come from the part of the story the child asked about (checks-v1).

Found on Qwen3.5-9B (2026-10-01): asked what Yusuf's brothers told their father when they came back without
him (the wolf, 12:16-18), the model quoted 12:63, the return from Egypt; asked how Ibrahim spoke to his father
about idols, it quoted his prayer for Makkah (14:35). Both passed the lexical support check and the faith judge.

Episodes come from the Wave 1 source maps (`data/episodes.json`, exported by scripts/export_episodes.py): for
each prophet, ayah ranges with an Arabic and an English label («الإخوة والبئر», "the brothers and the well").
A cited passage belongs to the episodes whose ranges hold its ayahs. Two deterministic rules decide:

1. **Another episode.** The question's words that name episodes of the cited prophet's story (key words of
   their labels: «البئر», «السحرة», «أبيه»; not one every episode of that prophet shares, not a generic label
   word such as «الدعوة» or «النجاة», not the prophet's own name) point to those episodes. A cited passage in
   one of them passes. A cited passage outside all of them fails when one of those words names a person in
   the story (a father, a brother, a son, the magicians, Pharaoh, the king, Iblis, another prophet...) and
   that person appears neither in the cited ayahs, nor within two ayahs of them, nor in their own episode's
   label (`scene:other_episode`). "كيف كلّم إبراهيم أباه عن عبادة الأصنام" names «الحوار مع أبيه» and the
   idols episodes; 14:35-41 (his prayer for Makkah) is in neither and never names a father, so it fails;
   6:71-76 is in neither too, but 6:74 names his father, so it passes. Objects and actions («السفينة»,
   «الأكل») only point to episodes, never fail an answer: the Quran tells one scene in other words in
   another surah («الفلك» for «السفينة»).
Neither rule decides which scene was asked; each refuses an answer only on positive evidence of another scene,
so a question that names no episode word and no absent person passes. The check is `unavailable` (recorded,
never counted as a pass) when the episode data is missing or a cited Quran passage lies outside every mapped
episode, and passes as `not_applicable` for answers that cite no Quran passage (hadith).

Quranpedia topics were considered and are not used here: they are thematic, not narrative (12:60-61 have
none), and one topic links 12:16 with 12:63, the very scenes rule 2 has to tell apart.
"""
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Iterable, Sequence

from . import arabizi, normalize
from .arabic_rules import PROPHET_NAMES_AR
from .ayahs import Ayah, AyahIndex
from .types import Chunk

EPISODES_FILE = Path(__file__).with_name("data") / "episodes.json"
WINDOW = 2  # ayahs on each side of the one an answer draws on, for rule 2

_RANGE = re.compile(r"^quran:(\d+):(\d+)(?:-(\d+))?$")
# Label words that name no scene of their own: verbal nouns a question uses in other senses, framing words.
GENERIC_AR = frozenset("""
سوره ذكر دعوه نجاه تكذيب حوار خروج قدوم اجتماع تحقق استجابه نداء توكل عهد نسيان توبه امتحان منه اولي
ذهاب حديث ميقات نعم اسوه حسنه مله محاجه احياء موتي نظر حجه خلق اباء مولد القاء تكليم رساله وصيه امامه
ليلا نهارا مده بعد هبوط استخلاف
""".split())
GENERIC_EN = frozenset("""
story being saved calling called given earlier mentioned surah about after good his her their them him how
long talking leaving going come comes together true one first allah god proof
""".split()) | normalize.STOPWORDS
# One key per family word: every form of "father" ("أبيه", "أباه", "أبوهم", "يا أبت") reads as one word.
_KIN = {"اب": "اب", "ابا": "اب", "ابو": "اب", "ابي": "اب", "ابت": "اب", "ابتي": "اب", "ابانا": "اب",
        "ابوي": "اب", "اخ": "اخ", "اخا": "اخ", "اخو": "اخ", "اخي": "اخ", "اخوه": "اخ", "اخوت": "اخ",
        "اخوان": "اخ", "اخوتي": "اخ", "ابن": "ابن", "ابنه": "ابن", "ابنها": "ابن", "ولد": "ابن", "ولده": "ابن",
        "ام": "ام", "امه": "ام", "امها": "ام", "زوج": "زوج", "زوجه": "زوج",
        "زوجته": "زوج", "امراه": "زوج", "امراته": "زوج"}
# People of the stories, besides family words and prophets' names: only words naming a person can fail rule 1.
PEOPLE_AR = frozenset({"اب", "اخ", "ابن", "ام", "زوج", "سحره", "ساحر", "فرعون", "ابليس", "شيطان", "ملايكه",
                       "ملك", "عزيز", "ضيف", "قوم", "هامان", "قارون", "بنو", "اسرايل", "عبد"})
# A prophet's family as the ayahs of his story call them: Yusuf's brothers say "أبانا", never "يعقوب".
FAMILY_AR = {"يعقوب": "اب", "ازر": "اب", "هارون": "اخ", "اسماعيل": "ابن", "اسحاق": "ابن"}
FAMILY_EN = {"yaqub": "father", "jacob": "father", "harun": "brother", "aaron": "brother", "ismail": "son",
             "ishmael": "son", "ishaq": "son", "isaac": "son"}
PEOPLE_EN = frozenset({"father", "brother", "son", "sons", "mother", "wife", "magician", "pharaoh", "iblis",
                       "satan", "angel", "king", "aziz", "guest", "people", "children", "israel", "servant"})
_PROPHET_NAME = re.compile(rf"^(?:{PROPHET_NAMES_AR})$")
_ABSENT_AR = re.compile(r"\b(?:بدون|بلا|بغير|دون|غير)\s+(?:ال)?(\S+)")
_ABSENT_LATIN = re.compile(r"\b(?:without|bdoon|bdun|bidoon|bidun|b doon|bala|bla|min ghair|men gheir|mn gher|"
                           r"min gheir)\s+(?:the |prophet |his |their |her |el |al )?(\S+)")
_KIN_EN = {"father": "father", "dad": "father", "brother": "brother", "brothers": "brother", "son": "son",
           "sons": "son"}
_KIN_EN_WORDS = {"father": {"father", "fathers"}, "brother": {"brother", "brothers"}, "son": {"son", "sons"}}


@dataclass(frozen=True)
class Episode:
    prophet: str
    surah: int
    first: int
    last: int
    label_ar: str
    label_en: str

    def holds(self, surah: int, ayah: int) -> bool:
        return self.surah == surah and self.first <= ayah <= self.last


class Episodes:
    def __init__(self, episodes: Iterable[Episode]):
        self.episodes = tuple(episodes)

    @classmethod
    def from_json(cls, data: dict) -> "Episodes":
        return cls(Episode(item["prophet"], item["surah"], item["first"], item["last"], item["label_ar"],
                           item["label_en"]) for item in data["episodes"])

    def of_ayah(self, surah: int, ayah: int) -> tuple[Episode, ...]:
        return tuple(episode for episode in self.episodes if episode.holds(surah, ayah))

    def of_chunk(self, chunk: Chunk) -> tuple[Episode, ...]:
        found = []
        for surah, ayah in quran_ayahs(chunk):
            found.extend(episode for episode in self.of_ayah(surah, ayah) if episode not in found)
        return tuple(found)

    def of_prophet(self, prophet: str) -> tuple[Episode, ...]:
        return tuple(episode for episode in self.episodes if episode.prophet == prophet)


@lru_cache(maxsize=1)
def load_episodes(path: Path = EPISODES_FILE) -> Episodes | None:
    """The exported episode index, or None when the file is missing (the scene check is then unavailable)."""
    if not path.is_file():
        return None
    return Episodes.from_json(json.loads(path.read_text(encoding="utf-8")))


def quran_ayahs(chunk: Chunk) -> list[tuple[int, int]]:
    """(surah, ayah) for every Quran reference of a chunk ("quran:12:58" or a range "quran:12:58-63")."""
    found = []
    for ref in chunk.source_refs or chunk.references:
        match = _RANGE.match(ref)
        if match:
            surah, first = int(match.group(1)), int(match.group(2))
            found.extend((surah, ayah) for ayah in range(first, int(match.group(3) or first) + 1))
    return found


def arabic_forms(token: str, *, vocative: bool = False) -> set[str]:
    """A token's light stems and the five nouns read as one word; with `vocative`, also the token without the
    vocative "يا" the Uthmani text joins to its noun ("يابت", "يقوم"). Passages only: in a question a leading
    ي is far more often a verb's."""
    forms = set(normalize.arabic_forms(token))
    if vocative and len(token) > 3 and token.startswith("ي"):
        forms |= normalize.arabic_forms(token[1:])
    forms |= {_KIN[form] for form in forms if form in _KIN}
    return forms


def english_forms(token: str) -> set[str]:
    forms = {token}
    for suffix in ("s", "es", "ed", "d", "ing"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            forms.add(token[:-len(suffix)])
    return forms


def _forms(token: str, language: str, vocative: bool = False) -> set[str]:
    return arabic_forms(token, vocative=vocative) if language == "ar" else english_forms(token)


def _vocabulary(texts: Iterable[str], language: str, *, passage: bool = False) -> set[str]:
    return {form for text in texts for token in normalize.content_tokens(text)
            for form in _forms(token, language, passage)}


def _names(prophet: str = "") -> tuple[set[str], set[str]]:
    """Prophets' names (Arabic, Latin), or one prophet's own."""
    arabic, latin = set(), set()
    for entry in arabizi._aliases()["prophets"]:
        if not prophet or entry["id"] == prophet:
            arabic.add(entry["ar"])
            latin |= set(entry["latin"])
    return arabic, latin


def _label_keys(episode: Episode, language: str) -> list[set[str]]:
    """The key words of an episode label, each as its set of forms: no generic word, not the prophet's name."""
    own_ar, own_latin = _names(episode.prophet)
    if language == "ar":
        tokens = [token for token in normalize.content_tokens(episode.label_ar)
                  if not GENERIC_AR & normalize.arabic_forms(token) and token not in own_ar]
    else:
        tokens = [token for token in normalize.content_tokens(episode.label_en)
                  if token not in own_latin and not english_forms(token) & GENERIC_EN]
    return [_forms(token, language) for token in tokens]


def _is_person(key: set[str], language: str) -> bool:
    names_ar, names_latin = _names()
    if language == "ar":
        return bool(key & (PEOPLE_AR | names_ar)) or any(_PROPHET_NAME.match(form) for form in key)
    return bool(key & (PEOPLE_EN | names_latin))


def episode_words(question_forms: set[str], prophet_episodes: Sequence[Episode],
                  language: str) -> list[tuple[set[str], tuple[Episode, ...]]]:
    """The question's words that name some, not all, of a prophet's episodes: each word's forms, with the
    episodes it names."""
    if len(prophet_episodes) < 2:
        return []
    keys = [_label_keys(episode, language) for episode in prophet_episodes]
    asked: list[tuple[set[str], tuple[Episode, ...]]] = []
    for episode_keys in keys:
        for key in episode_keys:
            if not key & question_forms or any(key & seen for seen, _ in asked):
                continue
            named = tuple(episode for episode, other in zip(prophet_episodes, keys) if any(key & word for word in other))
            # A key every episode of the prophet shares names no episode in particular.
            if len(named) < len(prophet_episodes):
                asked.append((key, named))
    return asked


def absent_people(question: str, language: str) -> list[set[str]]:
    """The people a question describes as absent ("بدون يوسف", "without his brother"), as sets of forms that
    name them in Arabic and in Latin letters."""
    folded = normalize.search_text(question)
    people = []
    aliases = arabizi._aliases()["prophets"]
    for match in _ABSENT_AR.finditer(folded):
        word = match.group(1)
        forms = arabic_forms(word)
        if _PROPHET_NAME.match(word) or forms & {"اب", "اخ"} or forms & {"ابن", "ابنه"}:
            names = {form for form in forms if form in {"اب", "اخ"}} or ({word} | forms)
            for prophet in aliases:
                if prophet["ar"] == word:
                    names |= set(prophet["latin"])
            people.append(names)
    for match in _ABSENT_LATIN.finditer(folded):
        word = match.group(1)
        if word in _KIN_EN:
            kin = _KIN_EN[word]
            people.append(_KIN_EN_WORDS[kin] | {{"father": "اب", "brother": "اخ", "son": "ابن"}[kin]})
            continue
        for prophet in aliases:
            if word in prophet["latin"]:
                people.append(set(prophet["latin"]) | {prophet["ar"]})
    return people


def answered_ayahs(sentences: Sequence[str], ayahs: Sequence[Ayah], language: str) -> list[Ayah]:
    """The ayahs an answer draws on: for each sentence, the ayah holding its quotation, else the ayahs sharing
    the most of its content words."""
    from .grounding import quotations  # here, because grounding imports router, which this module must not
    chosen: list[Ayah] = []
    for sentence in sentences:
        quoted = [normalize.search_text(quote, quranic=True).split() for quote in quotations(sentence)]
        hits = [ayah for ayah in ayahs for run in quoted if len(run) >= 2 and _contains(list(ayah.tokens), run)]
        if not hits:
            words = _vocabulary([sentence], language)
            scored = [(len(words & _vocabulary([" ".join(ayah.tokens)], language)), ayah) for ayah in ayahs]
            top = max((score for score, _ in scored), default=0)
            hits = [ayah for score, ayah in scored if top and score == top]
        chosen.extend(ayah for ayah in hits if ayah not in chosen)
    return chosen


def _contains(tokens: list[str], run: list[str]) -> bool:
    width = len(run)
    return any(tokens[start:start + width] == run for start in range(len(tokens) - width + 1))


@dataclass(frozen=True)
class SceneFinding:
    status: str      # "pass", "fail" or "unavailable"
    reason: str


def check_scene(question: str, question_terms: str, sentences: Sequence[str], cited: Sequence[Chunk],
                language: str, episodes: Episodes | None, ayahs: AyahIndex | None) -> SceneFinding:
    """Rules 1 and 2 above. `question_terms` is the text read for episode words: the question itself, or the
    Arabic search terms of an Arabizi question; `language` is the language of the cited passages."""
    quran = [chunk for chunk in cited if quran_ayahs(chunk)]
    if not quran:
        return SceneFinding("pass", "not_applicable")
    if episodes is None:
        return SceneFinding("unavailable", "no_episode_data")
    mapped = {chunk.id: episodes.of_chunk(chunk) for chunk in quran}
    prophets = sorted({episode.prophet for found in mapped.values() for episode in found})
    if not prophets:
        return SceneFinding("unavailable", "outside_episodes")
    question_forms = _vocabulary([question_terms], language)
    for prophet in prophets:
        own = [chunk for chunk in quran if any(episode.prophet == prophet for episode in mapped[chunk.id])]
        asked = episode_words(question_forms, episodes.of_prophet(prophet), language)
        named = {episode for _, episodes_named in asked for episode in episodes_named}
        if not asked or any(episode in named for chunk in own for episode in mapped[chunk.id]):
            continue
        people = [key for key, _ in asked if _is_person(key, language)]
        if not people:
            continue
        labels = [episode.label_ar if language == "ar" else episode.label_en
                  for chunk in own for episode in mapped[chunk.id]]
        texts = [chunk.search_text or chunk.text for chunk in own] + labels
        if ayahs is not None:
            texts += [" ".join(near.tokens) for chunk in own for ayah in ayahs.of_chunk(chunk)
                      for near in ayahs.window(ayah, WINDOW)]
        vocabulary = _vocabulary(texts, language, passage=True)
        family = FAMILY_AR if language == "ar" else FAMILY_EN
        if any(not key & vocabulary and not {family.get(form) for form in key} & vocabulary for key in people):
            return SceneFinding("fail", "other_episode")
    absent = absent_people(question, language)
    if absent:
        held = [ayah for chunk in quran for ayah in (ayahs.of_chunk(chunk) if ayahs is not None else [])]
        if held:
            drawn = answered_ayahs(sentences, held, language) or held
            window = {ayah for drawn_ayah in drawn for ayah in ayahs.window(drawn_ayah, WINDOW)}
            texts = [" ".join(ayah.tokens) for ayah in window]
        else:  # the release's text cannot be split into ayahs: the cited passages as a whole
            texts = [chunk.search_text or chunk.text for chunk in quran]
        words = _vocabulary(texts, language, passage=True) | {token for text in texts for token in text.split()}
        for person in absent:
            if not person & words:
                return SceneFinding("fail", "absent_person")
    return SceneFinding("pass", "")

