"""Tashkeel for Robert's own sentences, by the configured model (prompt `diacritize-v1`, ADR 0006).

The speech service's voice needs fully voweled text. The model is asked to add marks and nothing else, at
temperature 0, and its output is used only when `arabic.same_letters` holds: a changed, added or removed letter
drops that part. The text is Robert's own released sentence (quotations already removed), never the child's.
"""
from typing import Protocol

from ..rag.generator import GenerationError

PROMPT_ID = "diacritize-v1"
SYSTEM = (
    "You add Arabic diacritics (harakat, tanween, shadda and sukun) to Arabic text.\n"
    "Reply with exactly the text you are given, with diacritics added, and nothing else.\n"
    "- Keep every letter, word, space and punctuation mark as it is. Do not add, remove, correct or change any "
    "letter or word.\n"
    "- Do not translate, explain, or add quotation marks, labels or notes."
)


class Diacritizer(Protocol):
    def diacritize(self, text: str) -> str | None:
        """`text` with tashkeel added, or None when the model could not be reached."""


class LlmDiacritizer:
    """`diacritize-v1` on the answer model's OpenAI-compatible adapter (`rag/generator.py`)."""
    prompt_id = PROMPT_ID

    def __init__(self, generator, max_tokens: int = 600):
        self.generator, self.max_tokens = generator, max_tokens

    def diacritize(self, text: str) -> str | None:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]
        try:
            return self.generator.complete(messages, max_tokens=self.max_tokens, temperature=0.0).strip()
        except GenerationError:
            return None
