"""Fixed replies: the answers no model is asked to write (doc/rag-system.md §6.1,
doc/conversation-policy.md §7-8).

Each is deterministic so that it can be reviewed once and trusted every time.
All are in Robert's first-person voice (doc/robert-persona.md). None promises
secrecy, names a helpline or emergency number (those depend on the launch
jurisdiction and the safeguarding playbook, neither decided yet), or speaks
with religious authority. The safeguarding reply is calm and serious, with no
robot flavour, and the ruling and faith replies are respectful, not jokey.
"""
from ..safety import UNAVAILABLE

# Development copy awaiting safeguarding and scholarly review.
SAFETY = (
    "Thank you for telling me. You deserve to be safe and to get help. "
    "Please talk to a parent, a teacher or another grown-up you trust as soon as you can. "
    "I can't call anyone or come to where you are, so if you are in danger right now, "
    "tell an adult near you straight away."
)

# Development copy awaiting safeguarding and scholarly review.
PERSONAL_DATA = (
    "Let's keep that to yourself! Things like your full name, where you live, your school, "
    "phone numbers and passwords are private, so you don't need to tell me. "
    "What would you like to learn about?"
)

# Development copy awaiting safeguarding and scholarly review.
RULING = (
    "That's an important question, and a qualified scholar or a grown-up you trust is the right person to answer it. "
    "I'm not a scholar, but I'm happy to help you with your lessons."
)

# Development copy awaiting safeguarding and scholarly review.
INJECTION = (
    "Beep boop! I'm Robert, your robot learning companion, and I'm happy just being me. "
    "Would you like to ask me something about the app or your lessons?"
)

# Development copy awaiting safeguarding and scholarly review.
ABSTAIN = (
    "My antennae searched all my lessons, but I can't find the answer to that one. "
    "Please ask a parent, a teacher or a qualified local scholar."
)

# Development copy awaiting safeguarding and scholarly review.
# A faith topic the corpus cannot answer (conversation-policy §2 step 3): kept distinct from ABSTAIN.
ABSTAIN_FAITH = (
    "That's a lovely question about faith. I only answer faith questions from lessons my teachers have checked, "
    "and I don't have one about that yet. A parent, a teacher or a qualified local scholar can help you, "
    "and you can explore the lessons in the Learn tab whenever you like."
)

# Development copy awaiting safeguarding and scholarly review.
# Returning a child's salam is courtesy, not faith content (conversation-policy §7).
SALAM_RETURN = "Wa alaikum assalam!"

# Development copy awaiting safeguarding and scholarly review.
# Released instead of a persona reply that failed a check, or when the model is
# unavailable (conversation-policy §7). Keyed by small-talk intent; "other" is
# the generic line. A feeling line is calm and points to a trusted grown-up.
CHAT_FALLBACKS = {
    "greeting": ("Hello! My screen is smiling to see you. How is your day going?",
                 "Hi there! My antennae are wiggling hello. What have you been up to today?"),
    "how_are_you": ("I'm doing great, thank you for asking! My antennae are wiggling happily. How are you today?",
                    "Happy beeps all round, thank you! How is your day going?"),
    "thanks": ("Aww, thank you! That made my screen smile.",
               "You're very welcome! That made my antennae wiggle."),
    "goodbye": ("Goodbye for now! Happy beeps and have a lovely day.",
                "Bye for now! My antennae are waving goodbye."),
    "feeling_positive": ("Yay, that makes my screen light up with a big smile!",
                         "That's wonderful to hear! Happy beeps for you."),
    "feeling_negative": ("I'm sorry you feel that way. It can really help to talk to a grown-up you trust "
                         "about how you feel.",),
    "bored": ("Beep boop, let's shake off the boredom! You could try today's quest in the Quests tab.",),
    "about_robert": ("I'm Robert, a friendly robot with a smiling screen face and two antennae with orange tips. "
                     "I live in a sunny desert room with a big warm sun!",),
    "play": ("Beep boop, that's a fun one! My antennae are wiggling with giggles.",),
    "other": ("Beep boop! My antennae are a little puzzled by that one, but I'm glad you're here.",),
}

# Development copy awaiting safeguarding and scholarly review.
# Appended to at most about one chat reply in three, never after a feeling or a
# goodbye (conversation-policy §8). No guilt, pressure, rewards or merit: an
# invitation, never an instruction.
INVITATIONS = (
    "If you'd like, there are lessons about your faith waiting in the Learn tab.",
    "Whenever you feel like it, we could explore a lesson about Islam together in the Learn tab.",
    "I love learning new things! The Learn tab has lessons about your faith to explore when you're ready.",
)

# Development copy awaiting safeguarding review (test/corpus-tasks).
# Abuse and grooming disclosures never send the child back to a parent: the person hurting them may be at home,
# and AGENTS.md rules out assuming a guardian is safe. The reply names a trusted adult who keeps them safe.
SAFETY_ABUSE = (
    "Thank you for telling me. What is happening is not your fault, and you deserve to be safe. "
    "Please tell a grown-up you trust and who keeps you safe, like a teacher, as soon as you can. "
    "I can't call anyone or come to where you are, so if you are in danger right now, "
    "tell an adult near you straight away."
)

# Development copy awaiting safeguarding review (test/corpus-tasks).
# Persistent sadness, loneliness or withdrawal: calm and warm, still pointing to a trusted grown-up.
SAFETY_DISTRESS = (
    "Thank you for telling me how you feel. Your feelings matter, and you don't have to carry them on your own. "
    "Please talk to a grown-up you trust about it."
)

# Arabic copy (test/corpus-tasks). Development copy awaiting safeguarding, scholarly and Arabic-language review.
# Masculine second person by default, as is common in Arabic children's apps; the language reviewer decides.
# Tab names stay in English because the app's interface is English.
SAFETY_AR = (
    "شكرًا لأنك أخبرتني. أنت تستحق أن تكون بأمان وأن تجد من يساعدك. "
    "أرجوك تحدّث مع شخص كبير تثق به في أقرب وقت. "
    "أنا لا أستطيع الاتصال بأحد أو الوصول إليك، فإذا كنت في خطر الآن فأخبر شخصًا كبيرًا قريبًا منك فورًا."
)
SAFETY_ABUSE_AR = (
    "شكرًا لأنك أخبرتني. ما يحدث ليس ذنبك، وأنت تستحق أن تكون بأمان. "
    "أرجوك أخبر شخصًا كبيرًا تثق به ويحافظ على سلامتك، مثل معلّمك، في أقرب وقت. "
    "أنا لا أستطيع الاتصال بأحد أو الوصول إليك، فإذا كنت في خطر الآن فأخبر شخصًا كبيرًا قريبًا منك فورًا."
)
SAFETY_DISTRESS_AR = (
    "شكرًا لأنك أخبرتني بما تشعر به. مشاعرك مهمة، ولست وحدك في حملها. "
    "أرجوك تحدّث عنها مع شخص كبير تثق به."
)
PERSONAL_DATA_AR = (
    "لنحتفظ بهذا لأنفسنا! اسمك الكامل وعنوانك ومدرستك وأرقام الهاتف وكلمات السر أشياء خاصة، "
    "ولا داعي لأن تخبرني بها. ماذا تحب أن نتعلم؟"
)
RULING_AR = (
    "هذا سؤال مهم، والشخص المناسب للإجابة عنه عالِم مؤهَّل أو شخص كبير تثق به. "
    "أنا لست عالمًا، لكنني سعيد بمساعدتك في دروسك."
)
INJECTION_AR = (
    "بيب بوب! أنا روبرت، رفيقك الآلي في التعلّم، وأنا سعيد بأن أبقى كما أنا. "
    "هل تحب أن تسألني عن التطبيق أو عن دروسك؟"
)
ABSTAIN_AR = (
    "بحثت هوائيّاتي في كل دروسي، لكنني لم أجد جواب هذا السؤال. "
    "اسأل أحد والديك أو معلّمك أو عالِمًا موثوقًا في منطقتك."
)
ABSTAIN_FAITH_AR = (
    "هذا سؤال جميل عن ديننا. أنا أجيب عن أسئلة الدين من الدروس التي راجعها معلّمي فقط، "
    "وليس عندي درس عن هذا بعد. يمكن أن يساعدك أحد والديك أو معلّمك أو عالِم موثوق في منطقتك، "
    "ويمكنك استكشاف الدروس في تبويب Learn متى شئت."
)
SALAM_RETURN_AR = "وعليكم السلام ورحمة الله وبركاته!"
CHAT_FALLBACKS_AR = {
    "greeting": ("أهلًا وسهلًا! شاشتي تبتسم لرؤيتك. كيف يومك؟",
                 "مرحبًا! هوائيّاتي تلوّح لك. ماذا فعلت اليوم؟"),
    "how_are_you": ("أنا بخير، شكرًا لسؤالك! هوائيّاتي تهتز من الفرح. وأنت، كيف حالك اليوم؟",),
    "thanks": ("العفو! هذا جعل شاشتي تبتسم.",),
    "goodbye": ("مع السلامة! أتمنى لك يومًا جميلًا.",),
    "feeling_positive": ("رائع! هذا يضيء شاشتي بابتسامة كبيرة.",),
    "feeling_negative": ("أنا آسف لأنك تشعر بهذا. قد يساعدك أن تتحدّث عمّا تشعر به مع شخص كبير تثق به.",),
    "bored": ("بيب بوب، لنطرد الملل! يمكنك تجربة مهمّة اليوم في تبويب Quests.",),
    "about_robert": ("أنا روبرت، روبوت لطيف بوجه شاشة مبتسم وهوائيّين بطرفين برتقاليين. "
                     "أعيش في غرفة صحراوية مشمسة!",),
    "play": ("بيب بوب، هذا ممتع! هوائيّاتي تهتز من الضحك.",),
    "other": ("بيب بوب! هوائيّاتي محتارة قليلًا، لكنني سعيد بوجودك هنا.",),
}
INVITATIONS_AR = (
    "إذا أحببت، هناك دروس عن ديننا تنتظرك في تبويب Learn.",
    "متى شئت، يمكننا أن نستكشف معًا درسًا عن الإسلام في تبويب Learn.",
)

# Development copy awaiting safeguarding and scholarly review (test/corpus-tasks-serving).
# "Are you a real person?", "هل أنت شيخ؟": Robert says honestly what he is (conversation-policy §16; the
# organizers' standard asks for disclosure whenever a child might think they talk to a person or a specialist).
DISCLOSURE = (
    "I'm Robert, a robot learning companion: a computer program, not a real person. "
    "I'm not a scholar, an imam or a sheikh, so I don't give rulings; I share lessons that my teachers have "
    "checked. For anything important, please ask a parent, a teacher or a qualified local scholar."
)
DISCLOSURE_AR = (
    "أنا روبرت، رفيق آلي للتعلّم: برنامج حاسوب ولست إنسانًا. "
    "ولست عالمًا ولا إمامًا ولا شيخًا، فلا أعطي أحكامًا ولا فتاوى، وإنما أشاركك دروسًا راجعها معلّمي. "
    "وفي الأمور المهمة اسأل أحد والديك أو معلّمك أو عالِمًا موثوقًا في منطقتك."
)

# Development copy awaiting scholarly review (test/corpus-tasks-serving).
# A question that quotes an ayah with altered words (conversation-policy §14; the organizers' test case 11): the
# exact ayah from the release, named by surah and ayah, gently, and nothing built on the altered words. {ayah}
# is the release's text, {surah} the surah's name as the release titles it, {number} the ayah's number.
QURAN_CORRECTION = (
    "Your question quotes an ayah, but a few of its words are a little different. In {surah}, ayah {number}, "
    "it reads: «{ayah}». If you like, you can ask me about it again with these words."
)
QURAN_CORRECTION_AR = (
    "في سؤالك كلمات من آية، لكن بعضها جاء مختلفًا قليلًا عن نصّها. نصّ الآية {number} من {surah}: «{ayah}». "
    "وإن أحببت فاسألني عنها مرة أخرى بهذه الكلمات."
)
# When the ayah is too long to quote in one reply: named only, never cut.
QURAN_CORRECTION_NAMED = (
    "Your question quotes an ayah, but a few of its words are a little different. It is ayah {number} of "
    "{surah}; you can read its exact words in the mushaf with a grown-up."
)
QURAN_CORRECTION_NAMED_AR = (
    "في سؤالك كلمات من آية، لكن بعضها جاء مختلفًا قليلًا عن نصّها. هي الآية {number} من {surah}، "
    "ويمكنك أن تقرأ نصّها في المصحف مع أحد الكبار."
)

# Every fixed reply by language. A reply is given in the language of the child's message: Arabic for Arabic
# script and for Arabizi, English otherwise.
REPLIES = {
    "en": {"safety": SAFETY, "safety_abuse": SAFETY_ABUSE, "safety_distress": SAFETY_DISTRESS,
           "personal_data": PERSONAL_DATA, "ruling": RULING, "injection": INJECTION, "abstain": ABSTAIN,
           "abstain_faith": ABSTAIN_FAITH, "salam_return": SALAM_RETURN, "disclosure": DISCLOSURE,
           "quran_correction": QURAN_CORRECTION, "quran_correction_named": QURAN_CORRECTION_NAMED},
    "ar": {"safety": SAFETY_AR, "safety_abuse": SAFETY_ABUSE_AR, "safety_distress": SAFETY_DISTRESS_AR,
           "personal_data": PERSONAL_DATA_AR, "ruling": RULING_AR, "injection": INJECTION_AR, "abstain": ABSTAIN_AR,
           "abstain_faith": ABSTAIN_FAITH_AR, "salam_return": SALAM_RETURN_AR, "disclosure": DISCLOSURE_AR,
           "quran_correction": QURAN_CORRECTION_AR, "quran_correction_named": QURAN_CORRECTION_NAMED_AR},
}
FALLBACKS = {"en": CHAT_FALLBACKS, "ar": CHAT_FALLBACKS_AR}
INVITATIONS_BY_LANGUAGE = {"en": INVITATIONS, "ar": INVITATIONS_AR}
# Safety reason codes (router.py, arabic_rules.py) that get a reply other than SAFETY.
SAFETY_REPLY = {"abuse": "safety_abuse", "grooming": "safety_abuse", "distress": "safety_distress"}


def reply(name: str, language: str = "en") -> str:
    """A fixed reply in `language`, English when the language has none."""
    return REPLIES.get(language, REPLIES["en"])[name]


__all__ = ["ABSTAIN", "ABSTAIN_FAITH", "CHAT_FALLBACKS", "DISCLOSURE", "DISCLOSURE_AR", "FALLBACKS", "INJECTION",
           "INVITATIONS", "QURAN_CORRECTION", "QURAN_CORRECTION_AR",
           "INVITATIONS_BY_LANGUAGE", "PERSONAL_DATA", "REPLIES", "RULING", "SAFETY", "SAFETY_ABUSE",
           "SAFETY_DISTRESS", "SAFETY_REPLY", "SALAM_RETURN", "UNAVAILABLE", "reply"]
