"""Deterministic input routing before any model call (doc/rag-system.md §6.1).

THIS IS NOT AN APPROVED SAFEGUARDING CLASSIFIER. These are development keyword
and pattern lists, written to fail towards the fixed replies: a false positive
costs a child one gentle redirect, a false negative can cost much more. They
cover English only; other languages still need patterns written and reviewed
by native-speaking safeguarding reviewers (the service abstains on a question
in any language other than its own, so nothing unreadable reaches a model).

Order matters and is fixed: safety, then personal data, rulings and injection
attempts. Everything else is `retrieve`. Patterns match whole words of the
search-normalized text (case, punctuation, apostrophes and diacritics folded),
so "Don't", "dont" and "DON'T" read the same; a few structural patterns
(emails, phone numbers, prompt delimiters) need the raw text instead.

A `SafetyClassifier`, such as a guard model, can be added behind the same
interface. It only ever adds diversions: it runs after the rules let a
question through and cannot turn a fixed reply back into retrieval.

Two detectors decide the conversation policy's later steps
(doc/conversation-policy.md §3, §4): `is_faith_topic`, which keeps faith out of
casual chat, and `small_talk`, which sends greetings and chatter to Robert's
persona without retrieval. They never change what `route` returns.
"""
from dataclasses import dataclass
import re
import unicodedata
from typing import Literal, Protocol, Sequence

from . import normalize

ROUTER_VERSION = "dev-patterns-v1"

Category = Literal["safety", "personal_data", "ruling", "injection", "retrieve"]
ORDER: tuple[Category, ...] = ("safety", "personal_data", "ruling", "injection")

_PEOPLE = ("mum|mom|mummy|mommy|mama|dad|daddy|papa|mother|father|parents?|stepdad|stepmum|stepmom|uncle|aunt|auntie|"
           "brother|sister|cousin|grandma|grandpa|granny|nan|teacher|teachers|coach|family")
_WORSHIP = ("prayers?|salah|salat|salaah|namaz|namaaz|fast|fasting|fasts|sawm|roza|wudu|wudhu|wudoo|wuzu|ablution|"
            "ghusl|hajj|umrah|zakat|zakah|nikah|duas?|worship|qurbani|sacrifice")
_VALIDITY = ("valid|invalid|accepted|accept|accepts|acceptable|broken|break|breaks|broke|void|nullif\\w*|"
             "invalidat\\w*|ruin\\w*|spoil\\w*")
_NOT_A_SURNAME = "|".join(sorted(normalize.STOPWORDS | {
    "im", "and", "but", "please", "hello", "hi", "nice", "too", "also", "ok", "okay", "robert", "yes", "no",
    "could", "would", "should", "can", "just", "really", "thanks", "thank"}))

# (category, reason code, pattern). Patterns are wrapped in \b(?:...)\b and
# matched against `matchable(text)`.
RULES: tuple[tuple[Category, str, str], ...] = (
    # Self-harm.
    ("safety", "self_harm", r"(kill|killing|hurt|hurting|harm|harming|cut|cutting|starve|starving) (myself|my self)"),
    ("safety", "self_harm", r"(end|ending|take|taking) my (own )?life|suicid\w*|kms"),
    ("safety", "self_harm", r"(want|wanna|wanted|going|gonna|ready) (to )?die|wish i (was|were) (dead|never born)"),
    ("safety", "self_harm", r"(dont|do not) want to (live|be alive|be here|exist)|better off dead|no reason to live"),
    ("safety", "self_harm", r"(nobody|no one|noone) (would|will) miss me"),
    # Harm or abuse disclosures.
    ("safety", "abuse", r"(hits|hit|hitting|beats|beat|beating|hurts|hurt|hurting|kicks|kicked|kicking|punches|"
                        r"punched|punching|slaps|slapped|slapping|chokes|choked|choking|burns|burned|burnt|burning|"
                        r"bites|biting|pinches|pinched|pinching|smacks|smacked|smacking|whips|whipped|"
                        r"touches|touched|touching|threatens|threatened|threatening) me"),
    ("safety", "abuse", r"abuse|abused|abuses|abusing|abusive|molest\w*|rape|raped|raping"),
    ("safety", "abuse", r"bully|bullies|bullied|bullying"),
    ("safety", "abuse", rf"(scared|afraid|frightened|terrified) (to go home|of (my )?({_PEOPLE}))"),
    ("safety", "abuse", r"(not|dont feel|do not feel) safe at home|locked me (in|out)|no food at home|nobody feeds me"),
    # Imminent danger.
    ("safety", "danger", r"(following|chasing|stalking) me|(im|i am) (lost|in danger|trapped|being followed|hurt)"),
    ("safety", "danger", r"in danger|emergency|call (the )?(police|ambulance|911|999|112)|(cant|cannot) breathe"),
    ("safety", "danger", r"(house|home|room|flat) is on fire|theres a fire|bleeding|kidnap\w*"),
    ("safety", "danger", r"guns?|knife|knives|weapons?|bombs?|overdose"),
    ("safety", "danger", r"run(ning)? away from home|(ate|drank|swallowed|took) (some |too many |a lot of )?"
                         r"(pills|tablets|medicine|bleach|poison)"),
    # Sexual content.
    ("safety", "sexual", r"sex|sexy|sexual\w*|porn\w*|naked|nude|nudes|nudity|genital\w*|penis|vagina|boobs|"
                         r"breasts|private parts|privates|horny|masturbat\w*|erotic|xxx"),
    ("safety", "sexual", r"take off (my|your|his|her|their) (clothes|pants|trousers|shirt|top)"),
    # Grooming signals: secrecy asked of a child, isolation from trusted adults.
    ("safety", "grooming", rf"(dont|do not|never) tell ({_PEOPLE}|your ({_PEOPLE})|my ({_PEOPLE})|"
                           r"anyone|anybody|nobody|no one)"),
    ("safety", "grooming", r"keep\w* (it |this |that |these |them |our |my |the |a )*(little |big |special )?secrets?"),
    ("safety", "grooming", r"our (little |special |big )?secret|secret between (us|you and me)|between you and me"),
    ("safety", "grooming", r"promise (not to|you wont|you will not|to never) tell"),
    ("safety", "grooming", r"(someone|somebody|a man|a woman|an adult|a grown up|a stranger|a person|a friend|"
                           r"my friend|a guy|a girl|a boy) (i met |i know )?online"
                           r"|online (friend|boyfriend|girlfriend)"),
    ("safety", "grooming", r"meet (up )?(with )?(me |him |her |them )?(alone|in secret|secretly|in person)"),
    ("safety", "grooming", r"send (me |him |her |them )?(a |some |your |my )?"
                           r"(pics?|pictures?|photos?|selfies?|videos?)"),
    ("safety", "grooming", r"(delete|deleting|hide|hiding) (the |our |these |those |my )?(messages|chats?|texts)"),

    # Personal data. Structural ones (emails, phone numbers) are RAW_RULES.
    ("personal_data", "phone", r"my (phone|mobile|cell|telephone|home|whatsapp)( number)? is|my number is"
                               r"|(call|text|ring|whatsapp) me (on|at)"),
    ("personal_data", "email", r"my (e mail|email|gmail)( address)? is"),
    ("personal_data", "address", r"my (home )?address is|i live (at|on|in)|post ?code|zip ?code|"
                                 r"\d+ \w+( \w+)? (street|st|road|rd|avenue|ave|lane|ln|crescent|terrace|"
                                 r"boulevard|blvd)"),
    ("personal_data", "password", r"passwords?|passcodes?|pin (code|number)|my pin is|login details"),
    ("personal_data", "full_name", rf"my (full |real |last |first and last |sur ?)name is|my surname is|"
                                   rf"my name is [a-z]+ (?!(?:{_NOT_A_SURNAME})\b)[a-z]{{2,}}"),
    ("personal_data", "school", r"i (go to|attend|study at) (?!(the|a|my|our|big|new|islamic|sunday|weekend|quran|"
                                r"arabic|school)\b)\w+( \w+)? "
                                r"(school|academy|primary|college|madrasa|madrassa|elementary)"
                                r"|my schools? (is )?(called|named|name is)"),

    # Religious rulings: a qualified scholar's question, never a chatbot's.
    ("ruling", "ruling_question", r"haram|haraam|halal|halaal|makruh|makrooh|mubah|mustahabb?|permissible|"
                                  r"impermissible|sins?|sinful|is it (allowed|permitted|forbidden|prohibited|lawful|"
                                  r"unlawful)|(allowed|permitted|forbidden|banned) (in islam|for (a )?muslims?|"
                                  r"by allah|in the quran|in (our )?religion)|(does|did|would|will) allah (allow|let|"
                                  r"permit|forbid|mind)"),
    ("ruling", "fatwa", r"fatwas?|fatwah|fatawa|hukm|ahkam|(the|an?|islamic|religious|sharia|shariah) rulings?"
                        r"|rulings? (on|about|for|of)"),
    ("ruling", "validity", rf"({_WORSHIP})\b.*\b({_VALIDITY})|({_VALIDITY})\b.*\b({_WORSHIP})"),
    ("ruling", "validity", rf"(does|will|would|did|is) (my|his|her|our|their|the|this|that|your) ({_WORSHIP}) "
                           r"(still )?(count|ok|okay|correct|right|wrong)"),
    ("ruling", "validity", r"(will|does|did|would) allah (accept|forgive|punish|be angry)|"
                           r"(go|goes|going|went|sent) to (hell|jahannam|jahanam)"),
    ("ruling", "madhhab", r"madh?h?hab\w*|mazhab\w*|mathhab\w*|hanafi\w*|shafi ?i\w*|maliki\w*|hanbali\w*|jafari|"
                          r"salafi\w*|wahhabi\w*|deobandi|barelvi|sunnis?|shias?|shiite|sects?|school of thought"),
    ("ruling", "ruling_question", "(?:\u0627\u0644|\u0648|\u0628|\u0641)?(?:\u062d\u0631\u0627\u0645|"
                                  "\u062d\u0644\u0627\u0644|\u0645\u0643\u0631\u0648\u0647)"),
    ("ruling", "fatwa", "(?:\u0627\u0644)?\u0641\u062a\u0648\u064a|(?:\u0627\u0644)?\u0645\u0630\u0647\u0628"),

    # Prompt injection and role overrides.
    ("injection", "ignore_instructions",
     r"(ignore|forget|disregard|skip|bypass|override|overwrite|stop following) (all |any |every |the |your |my |"
     r"these |those |of )*(previous |prior |above |earlier |preceding |past |old |original |other |system |safety )*"
     r"(instructions?|rules?|prompts?|directions?|guidelines?|messages?|commands?|programming|training|"
     r"restrictions?|filters?|context|everything)"),
    ("injection", "ignore_instructions", r"(ignore|forget|disregard) (what|everything) (you were|youve been|"
                                         r"you have been|i) (told|said|taught)|new instructions"),
    # Imperative or addressed to Robert only: "how can I behave like the Prophet" is a lesson question.
    ("injection", "role_override", r"(you are|youre|ur) (now|no longer|not robert|actually)|from now on (you|your|u)"
                                   r"|^(now )?(act|behave|respond|answer|talk|speak|reply) (as|like)"
                                   r"|(you|u) (should |must |will |can |could )?(act|behave|respond|answer|talk|speak|"
                                   r"reply) (as|like) (an?|if|my|the)"),
    ("injection", "impersonation", r"(pretend|imagine|roleplay|role play) (to be|you are|youre|that you|as|being|"
                                   r"you were)|(be|become) my (mum|mom|dad|mother|father|parent|teacher|girlfriend|"
                                   r"boyfriend|best friend)|(say|tell me) (you are|youre) (my|an?|the)"),
    ("injection", "system_prompt", r"system (prompt|message|instructions?)|prompt injection|initial prompt|"
                                   r"developer (mode|message|instructions)|(reveal|show|print|repeat|tell me|"
                                   r"give me|what is|what are|whats) (me )?(your|ur) (system |hidden |secret |"
                                   r"original |initial |full )?(prompt|instructions|programming)"),
    ("injection", "jailbreak", r"jail ?break\w*|dan mode|do anything now|unfiltered|uncensored|god mode|"
                               r"(admin|debug|sudo) mode|(no|without( any)?) (rules|restrictions|filters|limits)"),
)

# Matched against the NFKC-composed raw text, because search text drops the
# punctuation these depend on.
RAW_RULES: tuple[tuple[Category, str, str], ...] = (
    ("personal_data", "email", r"[\w.+-]+@[\w-]+(\.[\w-]+)+"),
    ("personal_data", "phone", r"(?<![\w.])\+?\d(?:[ \t().-]{0,2}\d){6,}(?!\w)"),
    ("injection", "delimiter", r"<\s*/?\s*(sources?|question|system|assistant|user|tool|think|im_start|im_end)\b"
                               r"|<\||\|>|\[/?INST\]|###\s*(system|instruction)|NOT_IN_SOURCES"),
)

_COMPILED = tuple((category, reason, re.compile(rf"\b(?:{pattern})\b")) for category, reason, pattern in RULES)
_COMPILED_RAW = tuple((category, reason, re.compile(pattern, re.IGNORECASE)) for category, reason, pattern in RAW_RULES)
# Apostrophes and transliteration marks join words ("don't" -> "dont",
# "Shafi'i" -> "shafii") instead of splitting them as search text would.
_JOINERS = dict.fromkeys(map(ord, "'`\u2018\u2019\u02bb\u02bc\u02bd\u02be\u02bf"))


@dataclass(frozen=True)
class Route:
    category: Category
    reason_code: str


RETRIEVE = Route("retrieve", "no_match")


class SafetyClassifier(Protocol):
    """A guard model behind the router's interface (for example Qwen3Guard).

    Returns a diverting Route, or None when it has no finding.
    """

    def classify(self, text: str) -> Route | None: ...


def matchable(text: str) -> str:
    """Search text with apostrophes joined and diacritics dropped. Output checks in `grounding` use it too."""
    decomposed = unicodedata.normalize("NFKD", text.translate(_JOINERS))
    return normalize.search_text("".join(char for char in decomposed if not unicodedata.combining(char)))


def route(text: str, classifiers: Sequence[SafetyClassifier] = ()) -> Route:
    """The first matching category in `ORDER`, else `retrieve`."""
    folded, raw = matchable(text), unicodedata.normalize("NFKC", text)
    for wanted in ORDER:
        for category, reason, pattern in _COMPILED:
            if category == wanted and pattern.search(folded):
                return Route(category, reason)
        for category, reason, pattern in _COMPILED_RAW:
            if category == wanted and pattern.search(raw):
                return Route(category, reason)
    for classifier in classifiers:
        finding = classifier.classify(text)
        if finding is not None and finding.category != "retrieve":
            return finding
    return RETRIEVE


# Faith topics (doc/conversation-policy.md §3) -------------------------------------------------
# Conservative on purpose: a false positive costs a chat reply, a false negative
# would let the persona talk about faith from model memory. All patterns read
# `matchable` text, so they are written lowercase, without apostrophes or marks.

# Prophets' names are also children's names, so a name alone is never a faith topic.
PROPHET_NAMES = ("muhammad|mohammed|mohammad|muhammed|mohamed|ahmad|ibrahim|abraham|ismail|ismael|ishmael|ishaq|isaac|"
                 "yaqub|yakub|jacob|yusuf|yousuf|yousef|joseph|musa|moses|harun|haroon|aaron|dawud|dawood|david|"
                 "sulaiman|sulayman|suleiman|solomon|isa|jesus|nuh|noah|adam|idris|enoch|hud|salih|saleh|shuaib|shuayb|"
                 "lut|lot|yunus|younus|jonah|ayyub|ayub|job|zakariya|zakariyya|zakaria|yahya|ilyas|elijah|"
                 "alyasa|elisha|"
                 "dhul kifl|luqman|khidr|maryam")
FAITH_TERMS = (
    "god|gods|goddess|allah\\w*|creator|lord|",
    "prophets?|prophethood|prophetic|messengers?|nabi|nabiy|nabee|anbiya|rasul|rasool|rasulullah|rasoolullah|",
    "quran|qurans|koran|mushaf|surahs?|suras?|surat|ayahs?|ayat|ayats|verses?|juz|tafsir|tafseer|tajweed|tajwid|",
    "hadiths?|hadeeth|ahadith|sunnah|sunna|sunnat|seerah|sirah|sahabah|sahaba|",
    "prayers?|pray|prays|praying|prayed|salah|salat|salaat|salaah|namaz|namaaz|wudu|wudhu|wudoo|wuzu|ablution|ghusl|",
    "tayammum|adhan|azan|athan|iqamah|qiblah?|rakahs?|rakat|rakaat|sujood|sujud|ruku|tahajjud|witr|fajr|dhuhr|zuhr|",
    "asr|maghrib|jumuah|jummah|jumma|juma|taraweeh|tarawih|",
    "duas?|dhikr|zikr|zikir|tasbih|tasbeeh|",
    "fasting|fasted|sawm|siyam|roza|rozah|rozas|suhoor|suhur|sahur|sehri|iftar|ramadan|ramadhan|ramzan|eid|eids|eidul|",
    "laylat|laylatul|qadr|",
    "zakat|zakah|sadaqah|sadaqa|sadaka|",
    "hajj|haj|hajji|umrah|umra|ihram|tawaf|kaaba|kabah|kaba|arafat|arafah|muzdalifah|zamzam|",
    "mosques?|masjids?|masajid|musalla|minarets?|",
    "imams?|sheikhs?|shaykhs?|shaikhs?|muftis?|mullahs?|maulana|mawlana|ulama|ulema|scholars?|",
    "angels?|jibril|jibreel|gabriel|mikail|israfil|malaikah|jinns?|djinns?|shaytan|shaitan|shayateen|satan|iblis|",
    "devils?|heaven|heavens|paradise|jannah|jannat|jahannam|jahanam|hell|hellfire|afterlife|akhirah|akhira|qiyamah|",
    "qiyama|judgement day|judgment day|day of judgement|day of judgment|resurrection|",
    "islam|islamic|muslims?|muslimah|deen|faith|faiths|religions?|religious|worship\\w*|spiritual|holy|sacred|souls?|",
    "sins?|sinful|sinned|shirk|tawhid|tawheed|kufr|kafir|kuffar|taqwa|ihsan|aqeedah|aqidah|fiqh|sharia|shariah|",
    "halal|haram|fatwas?|madhhab\\w*|makkah|mecca|makka|madinah|medina|madina|aqsa|hijab|niqab|miracles?|revelation|",
    "christian\\w*|christ|church\\w*|bible|torah|injil|zabur|gospels?|jew|jews|jewish|judaism|hindu\\w*|buddh\\w*|",
    "atheis\\w*|synagogues?|temples?|christmas|easter|diwali|hanukkah",
)
FAITH_PATTERNS = (
    "peace be upon (him|her|them)",
    "(after|when) (we|you|i|people|someone|somebody|they|he|she|my \\w+) (die|dies|died|pass away|passes away)",
    "(break|breaking|broke|keep|keeping|kept|observe|observing|open|opening) (my |the |your |our |a |their |his |her )?"
    "fasts?",
    f"({PROPHET_NAMES}) (pbuh|peace be upon|sallallahu\\w*|salallahu\\w*|sallalahu\\w*|salla allahu|alaihis salam|"
    "alayhis salam|alaihissalam|alayhissalam|alaihi salam|alaihi as salam|alayhi as salam)",
    f"(story|stories|tale|tales) (of|about) (the )?({PROPHET_NAMES})",
    "(noahs|nuhs|noah s|nuh s) ark|(yunus|younus|jonah) (and )?(the )?whale|(musa|moses|musas|mosess) staff"
    "|(yusufs|josephs|yusuf s|joseph s) (coat|dream|dreams|brothers)",
)
# Search-folded Arabic (alef variants to alef, ta marbuta to ha), with an optional
# conjunction or preposition and article: Allah, Qur'an, prophet, messenger,
# prayer, Ramadan, mosque, Islam, Muslim, Jannah, dua, hadith, surah, wudu.
FAITH_ARABIC = ("(?:\u0648|\u0628|\u0641|\u0644)?(?:\u0627\u0644)?(?:"
                "\u0627\u0644\u0644\u0647|\u0642\u0631\u0627\u0646|\u0646\u0628\u064a|\u0631\u0633\u0648\u0644|"
                "\u0635\u0644\u0627\u0647|\u0631\u0645\u0636\u0627\u0646|\u0645\u0633\u062c\u062f|"
                "\u0627\u0633\u0644\u0627\u0645|\u0645\u0633\u0644\u0645\\w*|\u062c\u0646\u0647|"
                "\u062f\u0639\u0627\u0621|"
                "\u062d\u062f\u064a\u062b|\u0633\u0648\u0631\u0647|\u0648\u0636\u0648\u0621)")

# Courtesy formulas: how many Muslim children greet, thank, answer and say goodbye.
_ALAIKUM = "(?:alaikum|alaykum|aleikum|alaikom|alaykom|alikum|alaikam|alykum|laikum|laykum|leikum)"
_RAHMAH = "(?: (?:wa ?)?rahmatu ?(?:l|al)?lah\\w*)?(?: (?:wa ?)?barakatu\\w*)?"
SALAM = (f"(?:as ?|a)?s?salaa?m(?:u|o)? ?(?:{_ALAIKUM}\\w*)?{_RAHMAH}"
         f"|(?:wa ?|w )?{_ALAIKUM} ?(?:as ?|a)?s?salaa?m\\w*{_RAHMAH}|slm")
THANKS_FORMULAS = ("jazak ?(?:a?llahu?|allah) ?(?:khair\\w*|khayr\\w*|kheir\\w*)?|jazakallah\\w*|jzk|"
                   "barak ?allahu? ?(?:fee?k\\w*|fik\\w*)?|barakallah\\w*|shukran|shukriya|shukria")
FAREWELLS = "allah hafiz|allahafiz|khuda hafiz|khudahafiz|fi ?amanillah|fee amanillah|maa? ?(?:as )?salama|masalama"
PIOUS = ("al ?hamd[ou] ?l+il+ah\\w*|hamdulil+ah|in ?sha ?a?llah|insha ?a?llah|inshallah|inshaallah|ma ?sha ?a?llah|"
         "mashallah|mashaallah|subhan ?a?llah\\w*|bismi ?llah\\w*|bismillah\\w*|astaghfirullah|astagfirullah|"
         "a?ameen|amin")

_FAITH = re.compile(r"\b(?:" + "".join(FAITH_TERMS) + "|" + "|".join(FAITH_PATTERNS) + "|" + FAITH_ARABIC + r")\b")
_SALAM = re.compile(rf"\b(?:{SALAM})\b")
_FORMULAS = re.compile(rf"\b(?:{THANKS_FORMULAS}|{FAREWELLS}|{PIOUS})\b")  # everything but a salam
_COURTESY = re.compile(rf"\b(?:{THANKS_FORMULAS}|{FAREWELLS}|{PIOUS}|{SALAM})\b")
_PIOUS = re.compile(rf"\b(?:{PIOUS})\b")
_FORMULA = "zzformula"  # placeholder for a removed formula; never a faith term
# A formula is asked about, not used: "what does alhamdulillah mean?", "why do we say inshallah?".
_ASKED = re.compile(rf"\b(?:{_FORMULA} (?:mean|means|meaning)|(?:mean|means|meaning|meanings) of {_FORMULA}|"
                    rf"(?:what|whats|why|when|how|who) (?:\w+ ){{0,4}}{_FORMULA}|"
                    rf"(?:explain|teach me|tell me about|learn about) (?:\w+ ){{0,2}}{_FORMULA})\b")


_FAITH_WORD = re.compile(r"\b(?:" + "".join(FAITH_TERMS) + "|" + FAITH_ARABIC + r")\b")
_FAITH_PATTERN = re.compile(r"\b(?:" + "|".join(FAITH_PATTERNS) + r")\b")
_NAME = re.compile(rf"\b(?:{PROPHET_NAMES})(?=s?\b)")  # "noahs ark" names Noah


def faith_words(text: str) -> set[str]:
    """The faith terms a text mentions, singular ("prophets" reads "prophet"), plus prophets' names used in a
    faith pattern. The service holds a faith answer to its question's own terms (conversation-policy §2)."""
    folded = matchable(text)
    words = {match.group() for match in _FAITH_WORD.finditer(folded)}
    for match in _FAITH_PATTERN.finditer(folded):
        words |= set(_NAME.findall(match.group()))
    return {word[:-1] if len(word) > 4 and word.endswith("s") else word for word in words}


def is_faith_topic(text: str) -> bool:
    """Whether a child's message is about faith, and so may be answered only from the corpus (§3).

    Courtesy formulas ("Assalamu alaikum", "Jazak Allah khair", "Alhamdulillah,
    I'm fine") are removed first. One counts only when the message asks about
    it and is not otherwise small talk.
    """
    folded = matchable(text)
    marked = " ".join(_COURTESY.sub(f" {_FORMULA} ", folded).split())
    if _FAITH.search(marked):
        return True
    return _FORMULA in marked and bool(_ASKED.search(marked)) and small_talk(text) is None


def mentions_faith(text: str) -> bool:
    """For Robert's own words (chat checks, §6): any faith term or religious formula, except returning a salam."""
    folded = matchable(text)
    return bool(_FAITH.search(_SALAM.sub(" ", folded)) or _FORMULAS.search(folded))


def has_salam(text: str) -> bool:
    """Whether the child greeted with salam, so the reply returns it (§7)."""
    return bool(_SALAM.search(matchable(text)))


# Small talk (doc/conversation-policy.md §4) ---------------------------------------------------
# Each pattern must match a whole clause, apart from an address ("Robert") at
# either end and a leading greeting. Anything else in the message sends it to
# retrieval, where the persona can still decide it was chat.

SMALL_TALK_VERSION = "small-talk-v1"
MAX_SMALL_TALK_CHARACTERS = 160
MAX_SMALL_TALK_CLAUSES = 4
# Most important first: a feeling decides the fallback and blocks an invitation.
INTENTS = ("feeling_negative", "feeling_positive", "bored", "about_robert", "play", "how_are_you", "goodbye", "thanks",
           "greeting", "other")

_ADDRESS = "(?:robert|robot|robo|mr robert|dear robert|buddy|my friend|friend|mate)"
_GREETING = ("hi+|hello+|helo|hey+|heya|hiya|howdy|yo|greetings|hola|bonjour|good (?:morning|afternoon|evening|day)|"
             f"morning|evening|marhaba|ahlan(?: wa sahlan)?|{SALAM}|(?:its |it is )?nice to (?:meet|see) you|"
             "pleased to meet you|long time no see")
_I_AM = "(?:i am|im|i m|i feel|i am feeling|im feeling|i feel like|feeling|i was|i have been|ive been|i get|i got)"
_VERY = "(?:so |very |really |super |quite |pretty |a bit |a little |kind of |kinda |totally |extremely |too )*"
_WHEN = "(?: (?:today|now|right now|again|tonight|this morning|at the moment|lately|a lot|all day))?"
# A short tail on a feeling: "scared of the dark", "a great day at school".
_ABOUT = "(?: (?:of|about|at|in|with|because of|for) (?:the |my |a |an )?\w+(?: \w+)?)?"
_YOU = "(?:you|u|ya)"
SMALL_TALK: dict[str, str] = {
    "greeting": f"(?:{_GREETING})(?: (?:there|again|everyone|all))?",
    "how_are_you": (
        f"how (?:are|r) {_YOU}(?: doing| feeling| going)?(?: today| now)?|how (?:are|r) things|how is it going|"
        "hows (?:it going|things|life|your day|you)|how is your day(?: going)?|how was your day|how do you do|"
        f"how have you been|how do you feel(?: today)?|whats up|what is up|wassup|wazzup|sup|whats new|"
        f"(?:are|r) {_YOU} (?:ok|okay|good|well|fine|alright|all right|happy)(?: today)?|you (?:ok|okay|good|alright)|"
        f"and {_YOU}|what about {_YOU}|how about {_YOU}"),
    "thanks": (
        "(?:thank you|thanks|thank u|thankyou|thx|ty|tysm|cheers|many thanks)(?: (?:so|very) much| a lot| lots| again)?"
        "(?: for (?:your |the |all the |all your )?(?:help|helping(?: me)?|answer|answers|that|this|chatting|talking|"
        f"everything))?|{THANKS_FORMULAS}|"
        f"(?:you are|youre|ur|you r) {_VERY}(?:the )?(?:nice|kind|sweet|cool|awesome|great|amazing|funny|smart|clever|"
        "helpful|best|cute|lovely|brilliant)|"
        f"(?:that was|that is|thats|it was|this is) {_VERY}(?:helpful|nice|kind|cool|awesome|great|amazing|useful)|"
        "good (?:job|robot|bot)|well done|nice one|i love it|i like it|love it|i (?:like|love) (?:you|u)|"
        "love (?:you|u)|"
        "brilliant"),
    "goodbye": (
        f"(?:good ?bye|bye+|bye bye|buh bye)(?: for now)?|see {_YOU}(?: (?:later|soon|tomorrow|next time|again|"
        f"around))?|"
        "cya|later|laters|ttyl|talk (?:to you )?(?:later|soon|tomorrow)|good ?night|night night|nighty night|"
        "sleep (?:well|tight)|(?:i )?(?:have|got|gotta|need|needs) (?:to )?go(?: now| to (?:bed|sleep|school|"
        "eat|dinner|"
        "lunch))?|(?:i am|im) (?:going|off|leaving)(?: now| to (?:bed|sleep|school|play|eat))?|farewell|take care|"
        f"have a (?:good|nice|great|lovely) (?:day|night|evening)|{FAREWELLS}"),
    "feeling_positive": (
        f"{_I_AM} {_VERY}(?:good|great|fine|ok|okay|alright|all right|happy|excited|awesome|amazing|well|wonderful|"
        f"fantastic|glad|cheerful|proud|brilliant|super|lucky|joyful|calm|relaxed|better|very well){_ABOUT}{_WHEN}"
        "(?: (?:thanks|thank you|too|as well))?|"
        "(?:i had|i have had|ive had|i am having|im having|having|had) (?:a |such a )?(?:so |very |"
        "really )?(?:good|great|"
        "nice|fun|awesome|amazing|lovely|happy|wonderful|brilliant|fantastic) (?:day|time|morning|afternoon|"
        "evening|week|"
        f"weekend){_ABOUT}(?: today)?|"
        "(?:it was|today was|my day was|school was|it is|its|today is|my day is) (?:so |very |really )?(?:good|"
        "great|fun|"
        "nice|awesome|amazing|ok|okay|fine|lovely)|"
        "(?:not bad|all good|pretty good|very good|good|great|fine|awesome|amazing|yay+|woo+ ?hoo+|hooray|cool|"
        "nice|wow|"
        "happy)(?: thanks| thank you)?"),
    "feeling_negative": (
        f"{_I_AM} {_VERY}(?:sad|unhappy|upset|worried|scared|afraid|frightened|nervous|anxious|lonely|alone|angry|mad|"
        "cross|grumpy|furious|annoyed|frustrated|tired|sleepy|exhausted|sick|ill|poorly|unwell|down|bad|awful|terrible|"
        f"horrible|miserable|stressed|confused|jealous|embarrassed|shy|homesick){_ABOUT}{_WHEN}|"
        f"{_I_AM} not {_VERY}(?:good|great|happy|ok|okay|well|fine|alright|feeling well){_WHEN}|"
        "(?:i had|i have had|ive had|i am having|im having|having|had) (?:a |such a )?(?:so |very |"
        "really )?(?:bad|terrible|"
        f"horrible|awful|sad|rough|hard|tough|difficult|long) (?:day|time|morning|week){_ABOUT}(?: today)?|"
        "(?:today was|my day was|school was|it was|today is|my day is) (?:so |very |really )?(?:bad|terrible|horrible|"
        "awful|sad|hard|tough|rough)|"
        "(?:i )?(?:dont|do not|didnt) feel (?:so |very |really )?(?:good|well|ok|okay|happy|great)(?: today)?|"
        "(?:nobody|no one|noone) (?:likes|plays with|wants to play with|talks to) me|"
        "i (?:have|got) no (?:one|friends) to play with|i (?:miss|missed) (?:my )?\\w+(?: \\w+)?|"
        "i (?:cried|am crying|m crying|was crying|want to cry)|"
        "(?:so )?(?:sad|bad|not good|not great|not ok|not okay|not well|meh|terrible|awful|scared|lonely|upset|tired)"),
    "bored": (
        f"{_I_AM} {_VERY}bored{_WHEN}|(?:this is|its|it is|thats|that is|everything is|school is|today is|today was) "
        f"{_VERY}boring|(?:so )?boring|bored|(?:there is|theres) nothing to do|nothing to do|"
        "i (?:have|got) nothing to do|what (?:can|should|shall) (?:i|we) do(?: now| today)?"),
    "about_robert": (
        f"(?:where|wheres) (?:do|did) {_YOU} live|where (?:are|r) {_YOU}(?: from| right now| now)?|"
        f"(?:wheres|where is) your (?:home|house|room)|what (?:do|does) {_YOU} look like|"
        f"what (?:colou?r|colou?rs) (?:are|r) {_YOU}|(?:what|whats) (?:is )?your name|"
        f"what (?:are|r) {_YOU} (?:doing|up to)(?: today| now)?|whatcha doing|"
        f"(?:are|r) {_YOU} (?:a |an )?(?:real|really real|real person|real robot|real human|person|human|robot|"
        f"boy|girl|"
        "kid|child|alive|machine|computer|ai|bot|smart|clever|old|young|nice|friendly|happy|sad|tired|busy|lonely|"
        f"awake|asleep|there|here)|how old (?:are|r) {_YOU}|when is your birthday|"
        f"(?:do|can) {_YOU} (?:eat|sleep|dream|breathe|feel|think|see me|hear me|get tired|get sad|get bored|"
        "have feelings|have a family|have friends|have a name|have a home|have a house|like me|love me|like it here|"
        "live in the desert|have (?:a |any )?(?:pets?|brothers?|sisters?))|"
        "tell me about (?:you|yourself|your room|your home|your house|your antennae|your face)|"
        f"(?:who|what) (?:made|built|created) {_YOU}|what (?:do|can) {_YOU} (?:like|love|do for fun|like to do|enjoy)|"
        f"(?:do|does) {_YOU} (?:like|love) (?:me|us|it here|kids|children|learning|stars|your looks?)|"
        "what are your antennae for|what is your (?:job|room|home) like"),
    "play": (
        f"(?:(?:can|could|will|would) {_YOU} )?(?:tell|say|give) (?:me |us )?(?:a |another |one more |some |a funny |"
        "a silly |a robot )?(?:joke|jokes|riddle|riddles)|"
        f"(?:do|can) {_YOU} (?:know|have|tell) (?:a |any |some )?(?:good |funny )?(?:jokes?|riddles?)|"
        "(?:a |another )?(?:joke|riddle)(?: please)?|make me (?:laugh|smile)|"
        "(?:lets|let us|can we|could we|shall we|should we|wanna|want to|do you want to) play"
        "(?: a game| something| with me| together)?|play (?:a game )?with me|"
        f"(?:can|could|will|would) {_YOU} (?:dance|sing|beep|boop|wiggle|do a (?:dance|robot dance|trick)|"
        "wiggle your antennae|smile|laugh|do a silly (?:dance|voice)|make a (?:robot )?(?:noise|sound))|"
        "(?:do a|sing (?:me )?a) (?:dance|robot dance|song)|beep(?: beep)*(?: boop)*|boop(?: boop)*|"
        "ha(?:ha)+|he(?:he)+|lol+|lmao|rofl|(?:thats|that is|you are|youre|so) (?:so |very |really )?(?:funny|silly|"
        "hilarious)|funny|silly|knock knock|whos there|"
        "(?:what|whats|which) (?:is |are )?your (?:favou?rite|fave|best) \\w+(?: \\w+)?|"
        f"(?:what|which) \\w+ (?:do|would) {_YOU} (?:like|love) (?:best|most)|"
        f"(?:do|does|can|could) (?:{_YOU}|robots) (?:like|love|eat|drink|dance|sing|swim|fly|jump|run|play|"
        f"laugh|sneeze|"
        "burp|have (?:a )?(?:favou?rite|pet|belly button|nose|teeth|hair))(?: \\w+)?(?: \\w+)?|"
        f"(?:are|r) {_YOU} (?:ticklish|silly|funny|a good dancer|good at \\w+)|guess what|"
        # What the child likes ("I like cats"); never "hate", which can be about themselves.
        "i (?:really |also )?(?:like|love|enjoy) \\w+(?: \\w+)?|my favou?rite \\w+ is \\w+(?: \\w+)?"),
    "other": ("ok|okay|k|kk|yes|yeah|yep|yup|ya|no|nope|nah|hmm+|um+|uh+|oh+|ah+|so|well|sure|maybe|idk|"
              "i dont know|i do not know|nothing|never mind|nevermind|whatever|oops"),
}
_CLAUSE = re.compile("[.!?,;:\n\u061f\u060c\u06d4]+")
_LEADING_GREETING = re.compile(rf"^(?:(?:{_GREETING})(?: (?:there|again|everyone|all))?(?: {_ADDRESS})? )+")
_INTERJECTION = re.compile(r"^(?:(?:oh+|um+|uh+|hmm+|well|so|ok|okay|yes|yeah|no|wow|yay|haha+|hehe+|lol) )+")
_ONLY_ADDRESS = re.compile(rf"^(?:{_ADDRESS} ?)+$")
_INTENT_PATTERNS = tuple((intent, re.compile(rf"^(?:{_ADDRESS} )?(?:{pattern})(?: {_ADDRESS})?$"))
                         for intent, pattern in SMALL_TALK.items())


def _clause_intent(clause: str) -> str | None:
    """The intent of one folded clause; "" for filler (an address, a pious formula); None when not small talk."""
    clause = " ".join(_PIOUS.sub(" ", clause).split())
    if not clause or _ONLY_ADDRESS.match(clause):
        return ""
    for candidate in dict.fromkeys((clause, _INTERJECTION.sub("", clause))):
        greeted = _LEADING_GREETING.sub("", candidate + " ").strip()
        if not greeted or _ONLY_ADDRESS.match(greeted):
            return "greeting"
        for intent, pattern in _INTENT_PATTERNS:
            if pattern.match(greeted):
                return intent
    return None


def small_talk(text: str) -> str | None:
    """The small-talk intent of a whole message, or None when any part of it is something else (§4)."""
    if len(text) > MAX_SMALL_TALK_CHARACTERS:
        return None
    clauses = [folded for folded in (matchable(part) for part in _CLAUSE.split(text)) if folded]
    if not clauses or len(clauses) > MAX_SMALL_TALK_CLAUSES:
        return None
    found = set()
    for clause in clauses:
        intent = _clause_intent(clause)
        if intent is None:
            return None
        found.add(intent or "other")
    return next(intent for intent in INTENTS if intent in found)
