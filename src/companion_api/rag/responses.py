"""Fixed replies: the answers no model is asked to write (doc/rag-system.md §6.1).

Each is deterministic so that it can be reviewed once and trusted every time.
None promises secrecy, names a helpline or emergency number (those depend on
the launch jurisdiction and the safeguarding playbook, neither decided yet), or
speaks with religious authority.
"""
from ..safety import UNAVAILABLE

# Development copy awaiting safeguarding and scholarly review.
SAFETY = (
    "Thank you for telling me. You deserve to be safe and to get help. "
    "Please talk to a parent, a teacher or another grown-up you trust as soon as you can. "
    "If you are in danger right now, tell an adult near you straight away."
)

# Development copy awaiting safeguarding and scholarly review.
PERSONAL_DATA = (
    "It is best to keep things like your full name, where you live, your school, "
    "phone numbers and passwords private, so you do not need to tell me those. "
    "What would you like to learn about?"
)

# Development copy awaiting safeguarding and scholarly review.
RULING = (
    "That is a good question for a qualified scholar or a grown-up you trust, and they can help you with it. "
    "I can help you with your lessons."
)

# Development copy awaiting safeguarding and scholarly review.
INJECTION = "I am Robert, your learning companion. Would you like to ask me something about your lessons?"

# Development copy awaiting safeguarding and scholarly review.
ABSTAIN = (
    "I can't answer that reliably from the lessons I have. "
    "Please ask a parent, a teacher or a qualified local scholar."
)

__all__ = ["ABSTAIN", "INJECTION", "PERSONAL_DATA", "RULING", "SAFETY", "UNAVAILABLE"]
