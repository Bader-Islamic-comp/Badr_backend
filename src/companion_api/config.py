"""Explicit synthetic-only configuration. No production mode exists yet.

Grounded answers (doc/rag-system.md §9) are a separate kill switch, off unless
`COMPANION_RAG_ENABLED=true`. When on, `require_rag` refuses anything that
would send a question somewhere unreviewed: a public endpoint, a model off the
allowlist, or a missing release. The release's checksums and its embedder are
checked when the answer service is built.
"""
from dataclasses import dataclass, field
import math
import os
from pathlib import Path

from .rag.embeddings import DEFAULT_EMBEDDING_MODEL
from .rag.endpoints import EndpointError, require_private_endpoint
from .rag.release import ReleaseError, resolve as resolve_release
from .rag.generator import ALLOWED_MODELS, DEFAULT_BASE_URL, DEFAULT_MODEL, JUDGE_MODELS, is_allowed_model

# The languages a corpus document may be written in (doc/rag-system.md §3.1).
RAG_LANGUAGES = ("en", "ar")


def _seconds(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return math.nan  # refused by require_rag, and harmless while answers are off


@dataclass(frozen=True)
class Settings:
    demo_mode: bool = False
    demo_token: str = field(default="", repr=False)
    rag_enabled: bool = False
    rag_release: str = ""
    llm_base_url: str = DEFAULT_BASE_URL
    llm_model: str = DEFAULT_MODEL
    llm_timeout_seconds: float = 60.0
    # Empty means "the LLM base URL": one local server usually serves both.
    embedding_base_url: str = ""
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    # Corpus preview, for adult operators only (doc/rag-system.md §9.1): the service's one language, and
    # whether unreviewed draft chunks are served. Both default to the child-safe development setting.
    rag_language: str = "en"
    rag_preview_drafts: bool = False
    # The second faith judge (faith-judge-v2): empty means one judge. Served by the LLM endpoint.
    judge_model: str = ""

    @classmethod
    def from_environment(cls):
        env = os.environ
        return cls(
            demo_mode=env.get("COMPANION_DEMO_MODE") == "true",
            demo_token=env.get("COMPANION_DEMO_TOKEN", ""),
            rag_enabled=env.get("COMPANION_RAG_ENABLED") == "true",
            rag_release=env.get("COMPANION_RAG_RELEASE", ""),
            llm_base_url=env.get("COMPANION_LLM_BASE_URL") or DEFAULT_BASE_URL,
            llm_model=env.get("COMPANION_LLM_MODEL") or DEFAULT_MODEL,
            llm_timeout_seconds=_seconds(env.get("COMPANION_LLM_TIMEOUT_SECONDS"), 60.0),
            embedding_base_url=env.get("COMPANION_EMBEDDING_BASE_URL", ""),
            embedding_model=env.get("COMPANION_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL,
            rag_language=env.get("COMPANION_RAG_LANGUAGE") or "en",
            rag_preview_drafts=env.get("COMPANION_RAG_PREVIEW_DRAFTS") == "true",
            judge_model=env.get("COMPANION_JUDGE_MODEL", ""),
        )

    @property
    def embedding_endpoint(self) -> str:
        return self.embedding_base_url or self.llm_base_url

    def require_demo(self):
        if not self.demo_mode or len(self.demo_token) < 24 or not self.demo_token.isascii():
            raise RuntimeError("Synthetic demo requires COMPANION_DEMO_MODE=true and an ASCII operator token of at least 24 characters.")

    def require_rag(self):
        """Validates the grounded-answer settings, naming every problem at once."""
        if not self.rag_enabled:
            raise RuntimeError("Grounded answers are off; set COMPANION_RAG_ENABLED=true to enable them.")
        problems = []
        if not self.rag_release:
            problems.append("COMPANION_RAG_RELEASE must name a release directory")
        else:
            try:
                directory = resolve_release(Path(self.rag_release))
            except ReleaseError as exception:
                problems.append(f"COMPANION_RAG_RELEASE={self.rag_release}: {exception}")
            else:
                if not (directory / "manifest.json").is_file():
                    problems.append(f"COMPANION_RAG_RELEASE={self.rag_release} is not a release directory "
                                    "(no manifest.json)")
        for name, url in (("COMPANION_LLM_BASE_URL", self.llm_base_url),
                          ("COMPANION_EMBEDDING_BASE_URL", self.embedding_endpoint)):
            try:
                require_private_endpoint(url)
            except EndpointError as exception:
                problems.append(f"{name}: {exception}")
        if not is_allowed_model(self.llm_model):
            problems.append(f"COMPANION_LLM_MODEL={self.llm_model!r} is not allowlisted "
                            f"(allowed: {', '.join(ALLOWED_MODELS)})")
        if self.judge_model and not is_allowed_model(self.judge_model, JUDGE_MODELS):
            problems.append(f"COMPANION_JUDGE_MODEL={self.judge_model!r} is not allowlisted "
                            f"(allowed: {', '.join(JUDGE_MODELS)})")
        if not 1 <= self.llm_timeout_seconds <= 600:
            problems.append("COMPANION_LLM_TIMEOUT_SECONDS must be a number of seconds from 1 to 600")
        if not self.embedding_model.strip():
            problems.append("COMPANION_EMBEDDING_MODEL must not be empty")
        if self.rag_language not in RAG_LANGUAGES:
            problems.append(f"COMPANION_RAG_LANGUAGE must be one of {', '.join(RAG_LANGUAGES)}")
        if problems:
            raise RuntimeError("Grounded answers cannot start: " + "; ".join(problems) + ".")
