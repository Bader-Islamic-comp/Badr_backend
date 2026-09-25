"""Embedders behind the `Embedder` protocol.

`HashingEmbedder` needs no model and no network: it is deterministic across
processes, so tests and an offline development release can use it. It matches
shared words and word fragments, not meaning. `OpenAICompatibleEmbedder` calls a
self-hosted `/v1/embeddings` endpoint (Ollama, llama.cpp or vLLM) and is what a
real release should be built with.
"""
from hashlib import blake2b
import math
from typing import Sequence

import httpx

from . import normalize
from .endpoints import require_private_endpoint
from .types import EmbedderIdentity

# Qwen3-Embedding is instruction-tuned: queries carry a task line, documents
# do not. Changing this string changes the identity, so an old release refuses
# to be queried with it instead of silently scoring worse.
QWEN_QUERY_INSTRUCTION = "Given a child's question, retrieve reviewed passages that answer it"
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"  # Ollama's OpenAI-compatible API
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
DEFAULT_EMBEDDING_DIMENSIONS = 1024


class EmbeddingError(RuntimeError):
    pass


def l2_normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm or not math.isfinite(norm):
        return [0.0] * len(vector)
    return [value / norm for value in vector]


class HashingEmbedder:
    """Signed feature hashing of search tokens and their character trigrams."""

    def __init__(self, dimensions: int = 384):
        if dimensions < 16:
            raise ValueError("dimensions must be at least 16")
        self._identity = EmbedderIdentity("hashing", "hashing-v1", dimensions)

    @property
    def identity(self) -> EmbedderIdentity:
        return self._identity

    def _features(self, text: str):
        for token in normalize.content_tokens(text):
            yield token, 1.0
            padded = f"<{token}>"
            for start in range(len(padded) - 2):
                yield "#" + padded[start:start + 3], 0.5

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._identity.dimensions
        for feature, weight in self._features(text):
            digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little")
            vector[value % len(vector)] += weight if value >> 63 else -weight
        return l2_normalize(vector)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OpenAICompatibleEmbedder:
    """`POST {base_url}/embeddings` on a self-hosted server.

    Only private endpoints are accepted. Inputs are never logged; errors carry
    the status code and nothing from the request.
    """

    def __init__(self, base_url: str, model: str = DEFAULT_EMBEDDING_MODEL, *,
                 dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
                 query_instruction: str = QWEN_QUERY_INSTRUCTION,
                 timeout: float = 120.0, batch_size: int = 16, client: httpx.Client | None = None):
        # Generous on purpose: the first request after a server start loads the
        # model onto the GPU, which took over 30 s on an RTX 3060 (measured).
        self.base_url = require_private_endpoint(base_url)
        self.batch_size = batch_size
        self._identity = EmbedderIdentity("openai-compatible", model, dimensions, query_instruction)
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    @property
    def identity(self) -> EmbedderIdentity:
        return self._identity

    def _request(self, inputs: list[str]) -> list[list[float]]:
        try:
            response = self._client.post(self.base_url + "/embeddings",
                                         json={"model": self._identity.model, "input": inputs})
        except httpx.HTTPError as exception:
            raise EmbeddingError(f"embedding endpoint unreachable ({type(exception).__name__})") from None
        if response.status_code != 200:
            raise EmbeddingError(f"embedding endpoint returned HTTP {response.status_code}")
        try:
            rows = sorted(response.json()["data"], key=lambda row: row["index"])
            vectors = [[float(value) for value in row["embedding"]] for row in rows]
        except (KeyError, TypeError, ValueError):
            raise EmbeddingError("embedding endpoint returned an unexpected body") from None
        if len(vectors) != len(inputs) or any(len(vector) != self._identity.dimensions for vector in vectors):
            raise EmbeddingError(
                f"expected {len(inputs)} vectors of {self._identity.dimensions} dimensions; "
                "check COMPANION_EMBEDDING_MODEL and its dimensions")
        return [l2_normalize(vector) for vector in vectors]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._request(list(texts[start:start + self.batch_size])))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        instruction = self._identity.query_instruction
        prompt = f"Instruct: {instruction}\nQuery:{text}" if instruction else text
        return self._request([prompt])[0]

    def close(self):
        self._client.close()


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Dot product; both sides are already L2-normalized."""
    return sum(a * b for a, b in zip(left, right))


def embedder_for(model: str, base_url: str = DEFAULT_BASE_URL):
    """The one place a model name becomes an embedder.

    The pipeline and the server both call this with the same settings, so a
    release and the queries against it cannot disagree about how text is
    embedded. `hashing` needs no endpoint and ignores `base_url`.
    """
    if model == "hashing":
        return HashingEmbedder()
    return OpenAICompatibleEmbedder(base_url, model)
