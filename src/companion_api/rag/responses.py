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

__all__ = ["ABSTAIN", "ABSTAIN_FAITH", "CHAT_FALLBACKS", "INJECTION", "INVITATIONS", "PERSONAL_DATA", "RULING",
           "SAFETY", "SALAM_RETURN", "UNAVAILABLE"]
