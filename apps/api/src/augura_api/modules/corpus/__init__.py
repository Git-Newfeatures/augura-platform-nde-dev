"""Public interface of the corpus module.

Exposes the router (composition) and `search_corpus` (retrieval reused by
the E1 agent — cross-module call via the public interface, spec §8).
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.modules.corpus.repo import CorpusRepo
from augura_api.modules.corpus.router import router


async def search_corpus(
    session: AsyncSession,
    embedding: list[float],
    *,
    match_count: int = 20,
    filter: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """pgvector search (match_chunks) via the module's public interface."""
    return await CorpusRepo(session).search(embedding, match_count, filter or {})


__all__ = ["router", "search_corpus"]
