"""Embedding providers (FR-072, FR-109).

One asynchronous seam, resolved from the ``KnowledgeBase``'s stored model and dimension — never
hardcoded at a call site. A query and the chunks it searches must be embedded by the *same* model,
or the cosine scores are meaningless, which is why the KB records both.
"""

import abc
import hashlib
import math
import re

from app.core.config import settings


class EmbeddingProviderError(Exception):
    """No embedding provider is configured, or the provider failed."""


class EmbeddingProvider(abc.ABC):
    """Abstract base class for text embedding providers.

    Vectors are expected to be unit-normalised, so cosine similarity is the dot product.
    """

    model_id: str
    dimension: int

    @abc.abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate a normalized embedding vector for the provided text."""
        ...

    @abc.abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized embedding vectors for a list of texts."""
        ...


class DeterministicHashEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic local embedding provider using multi-resolution feature hashing.
    Zero external APIs, zero token cost, zero LLM dependencies.

    Lexical, not semantic — a development and test double, not a production embedding. Kept so
    test runs and pre-B6 knowledge bases remain reproducible without a network call.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.model_id = f"deterministic-hash-{dimension}"

    def _hash_feature(self, prefix: str, feature: str) -> tuple[int, float]:
        key = f"{prefix}:{feature}".encode()
        digest = hashlib.sha256(key).digest()
        idx = int.from_bytes(digest[:4], "big") % self.dimension
        sign = 1.0 if (digest[4] % 2 == 0) else -1.0
        return idx, sign

    async def embed_text(self, text: str) -> list[float]:
        norm_text = text.lower().strip()
        if not norm_text:
            val = 1.0 / math.sqrt(self.dimension)
            return [round(val, 6)] * self.dimension

        vec = [0.0] * self.dimension

        # 1. Word tokens
        words = re.findall(r"\b\w+\b", norm_text)
        for w in words:
            idx, sign = self._hash_feature("w", w)
            vec[idx] += sign * 2.0

        # 2. Character trigrams
        compact = re.sub(r"\s+", " ", norm_text)
        if len(compact) >= 3:
            for i in range(len(compact) - 2):
                tri = compact[i : i + 3]
                idx, sign = self._hash_feature("3", tri)
                vec[idx] += sign * 1.0

        # 3. Character 4-grams
        if len(compact) >= 4:
            for i in range(len(compact) - 3):
                four = compact[i : i + 4]
                idx, sign = self._hash_feature("4", four)
                vec[idx] += sign * 1.0

        # Compute L2 norm
        sq_sum = sum(x * x for x in vec)
        norm = math.sqrt(sq_sum)
        if norm < 1e-12:
            val = 1.0 / math.sqrt(self.dimension)
            return [round(val, 6)] * self.dimension

        return [round(x / norm, 6) for x in vec]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(t) for t in texts]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute exact cosine similarity between two vectors.
    Providers produce unit-normalised vectors, so this is the dot product.
    """
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    # Bound to [-1.0, 1.0] to guard against floating-point drift
    return max(-1.0, min(1.0, float(dot)))


def build_default_embedding_provider() -> EmbeddingProvider:
    """The provider new knowledge bases are created with, from settings."""
    if settings.EMBEDDING_PROVIDER == "deterministic":
        return DeterministicHashEmbeddingProvider(settings.EMBEDDING_DIMENSION)
    if settings.EMBEDDING_PROVIDER == "gemini":
        if not settings.EMBEDDING_API_KEY:
            raise EmbeddingProviderError(
                "EMBEDDING_API_KEY is not configured; set it or use "
                "EMBEDDING_PROVIDER=deterministic."
            )
        from app.services.knowledge.embeddings_gemini import GeminiEmbeddingProvider

        return GeminiEmbeddingProvider(
            settings.EMBEDDING_API_KEY, settings.EMBEDDING_MODEL, settings.EMBEDDING_DIMENSION
        )
    raise EmbeddingProviderError(f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER!r}")


def get_embedding_provider(model_id: str, dimension: int) -> EmbeddingProvider:
    """Resolve the provider a knowledge base was embedded with.

    A stored model id, not a global setting, decides: re-embedding an old knowledge base with a
    new model would silently invalidate every existing chunk.
    """
    if model_id.startswith("deterministic-hash"):
        return DeterministicHashEmbeddingProvider(dimension)
    if model_id.startswith("gemini-embedding"):
        if not settings.EMBEDDING_API_KEY:
            raise EmbeddingProviderError(
                f"Knowledge base uses {model_id!r} but EMBEDDING_API_KEY is not configured."
            )
        from app.services.knowledge.embeddings_gemini import GeminiEmbeddingProvider

        return GeminiEmbeddingProvider(settings.EMBEDDING_API_KEY, model_id, dimension)
    raise EmbeddingProviderError(f"No embedding provider for stored model {model_id!r}.")


def validate_embedding_configuration() -> None:
    """Refuse an embedding configuration that would fail on the first upload or query.

    Mirrors ``validate_model_configuration``: the shape is checked at startup; a missing key is
    left to the runtime, which reports it as a 503 rather than fabricating an answer.
    """
    if settings.EMBEDDING_PROVIDER not in {"deterministic", "gemini"}:
        raise RuntimeError(f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER!r}")
    if settings.EMBEDDING_DIMENSION <= 0:
        raise RuntimeError("EMBEDDING_DIMENSION must be positive.")
    if settings.EMBEDDING_PROVIDER == "gemini" and not settings.EMBEDDING_MODEL.startswith(
        "gemini-embedding"
    ):
        raise RuntimeError(
            f"EMBEDDING_MODEL {settings.EMBEDDING_MODEL!r} is not a recognized Gemini embedding "
            "model id (expected a 'gemini-embedding…' id); ingestion and retrieval would fail."
        )
