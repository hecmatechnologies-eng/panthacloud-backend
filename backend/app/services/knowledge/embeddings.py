import abc
import hashlib
import math
import re


class EmbeddingProvider(abc.ABC):
    """Abstract base class for text embedding providers."""

    model_id: str
    dimension: int

    @abc.abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Generate a normalized embedding vector for the provided text."""
        ...

    @abc.abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized embedding vectors for a list of texts."""
        ...


class DeterministicHashEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic local embedding provider using multi-resolution feature hashing.
    Zero external APIs, zero token cost, zero LLM dependencies.
    Produces 384-dimensional unit-normalized vectors.
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

    def embed_text(self, text: str) -> list[float]:
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

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute exact cosine similarity between two vectors.
    Since vectors produced by DeterministicHashEmbeddingProvider are normalized,
    cosine similarity is the dot product.
    """
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    # Bound to [-1.0, 1.0] to guard against floating-point drift
    return max(-1.0, min(1.0, float(dot)))
