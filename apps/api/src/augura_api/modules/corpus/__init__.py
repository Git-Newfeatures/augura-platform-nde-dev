"""Interface publique du module corpus.

Expose le router (composition) et `search_corpus` (retrieval réutilisé par
l'agent E1 — appel inter-module via l'interface publique, spec §8).
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
    """Recherche pgvector (match_chunks) via l'interface publique du module."""
    return await CorpusRepo(session).search(embedding, match_count, filter or {})


__all__ = ["router", "search_corpus"]
