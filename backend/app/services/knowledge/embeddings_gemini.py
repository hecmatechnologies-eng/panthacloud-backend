"""Gemini embedding adapter (FR-072, FR-125).

The only embedding module that imports a vendor SDK. It normalises the returned vectors so the
shared cosine-similarity dot product stays correct — Gemini returns non-unit vectors.
"""

import math

from app.services.knowledge.embeddings import EmbeddingProvider, EmbeddingProviderError

# One request per this many texts, so a large document does not exceed the provider's per-request
# limit and fail the whole ingestion.
_BATCH_SIZE = 100


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str, dimension: int) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model_id = model
        self.dimension = dimension

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            vectors.extend(await self._embed_batch_once(texts[start : start + _BATCH_SIZE]))
        return vectors

    async def _embed_batch_once(self, texts: list[str]) -> list[list[float]]:
        from google.genai import types

        try:
            result = await self._client.aio.models.embed_content(
                model=self.model_id,
                contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=self.dimension),
            )
        except Exception as exc:
            raise EmbeddingProviderError(f"Gemini embedding failed: {exc}") from exc

        return [_normalize(list(embedding.values)) for embedding in result.embeddings]


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm < 1e-12:
        return vector
    return [x / norm for x in vector]
