"""OpenAI-compatible chat adapter for Qwen3.5-9B (doc/rag-system.md §6.3).

The server is self-hosted (Ollama by default; llama.cpp and vLLM speak the same
API) and must be on this machine or a private network. Only the reviewed model
may be called: switching models is a review decision, not a configuration
change, so anything off the allowlist is refused.

Qwen3.5 thinks before answering unless told not to. Thinking is disabled two
ways because servers read different fields (`reasoning_effort` for Ollama,
`chat_template_kwargs.enable_thinking` for llama.cpp and vLLM), and any
reasoning that still comes back is dropped: only the final answer is verified,
and reasoning is never shown to a child.
"""
import re
from typing import Sequence

import httpx

from .endpoints import require_private_endpoint

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "qwen3.5:9b"
# Exact names, plus Ollama tags of the same model ("qwen3.5:9b-q4_K_M").
ALLOWED_MODELS = ("qwen3.5:9b", "qwen3.5:9b-*", "Qwen/Qwen3.5-9B")
_TAG = re.compile(r"[A-Za-z0-9._-]+")
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class GenerationError(RuntimeError):
    """Carries a status or an error type only, never request or response content."""


def is_allowed_model(model: str) -> bool:
    for allowed in ALLOWED_MODELS:
        if allowed.endswith("*"):
            prefix = allowed[:-1]
            if model.startswith(prefix) and _TAG.fullmatch(model[len(prefix):]):
                return True
        elif model == allowed:
            return True
    return False


def strip_reasoning(text: str) -> str:
    """The answer without `<think>` blocks.

    An unclosed leading `<think>` means the output was cut off while reasoning,
    so there is no answer at all. A stray `</think>` means the template opened
    the block in the prompt, so everything before it is reasoning.
    """
    text = _THINK_BLOCK.sub("", text)
    lowered = text.lower()
    if "</think>" in lowered:
        text = text[lowered.rindex("</think>") + len("</think>"):]
    if text.lstrip().lower().startswith("<think>"):
        return ""
    return text.strip()


class OpenAICompatibleGenerator:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, timeout: float = 60.0,
                 client: httpx.Client | None = None, *, temperature: float = 0.3, top_p: float = 0.8):
        if not is_allowed_model(model):
            raise ValueError(f"model {model!r} is not allowlisted; expected one of {', '.join(ALLOWED_MODELS)}")
        self.base_url = require_private_endpoint(base_url)
        self.model = model
        self.temperature, self.top_p = temperature, top_p
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    def payload(self, messages: Sequence[dict], max_tokens: int) -> dict:
        return {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": max_tokens,
            "stream": False,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        }

    def complete(self, messages: Sequence[dict], *, max_tokens: int) -> str:
        try:
            response = self._client.post(self.base_url + "/chat/completions", json=self.payload(messages, max_tokens))
        except httpx.TimeoutException as exception:
            raise GenerationError(f"generation endpoint timed out ({type(exception).__name__})") from None
        except httpx.HTTPError as exception:
            raise GenerationError(f"generation endpoint unreachable ({type(exception).__name__})") from None
        if response.status_code != 200:
            raise GenerationError(f"generation endpoint returned HTTP {response.status_code}")
        try:
            # `reasoning` / `reasoning_content` are deliberately never read.
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError):
            raise GenerationError("generation endpoint returned an unexpected body") from None
        if content is None:
            return ""
        if not isinstance(content, str):
            raise GenerationError("generation endpoint returned an unexpected body")
        return strip_reasoning(content)

    def check(self) -> list[str]:
        """Model ids the endpoint serves; raises unless the configured model is one of them."""
        try:
            response = self._client.get(self.base_url + "/models")
        except httpx.HTTPError as exception:
            raise GenerationError(f"generation endpoint unreachable ({type(exception).__name__})") from None
        if response.status_code != 200:
            raise GenerationError(f"generation endpoint returned HTTP {response.status_code}")
        try:
            served = [str(row["id"]) for row in response.json()["data"]]
        except (KeyError, TypeError, ValueError):
            raise GenerationError("generation endpoint returned an unexpected model list") from None
        if self.model not in served:
            raise GenerationError(f"model {self.model!r} is not served by the endpoint; pull or load it first")
        return served

    def close(self):
        self._client.close()
