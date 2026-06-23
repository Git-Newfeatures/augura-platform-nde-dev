"""OpenAI embeddings (text-embedding-3-small, 1536) — for the E1 retrieval.

Injectable via the `Embedder` Protocol: tests provide a fake embedder.
"""

from typing import Protocol

import openai

from augura_api.core.config import Settings
from augura_api.core.llm.runtime import AgentUpstreamError

EMBED_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    def __init__(self, client: openai.AsyncOpenAI, model: str = EMBED_MODEL) -> None:
        self._client = client
        self._model = model

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=self._model, input=text)
        return list(resp.data[0].embedding)


def get_embedder(settings: Settings) -> Embedder:
    if settings.openai_api_key is None:
        raise AgentUpstreamError("OPENAI_API_KEY missing")
    return OpenAIEmbedder(openai.AsyncOpenAI(api_key=settings.openai_api_key))
