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
