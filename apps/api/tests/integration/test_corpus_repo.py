"""Tests d'intégration du module corpus — lecture du corpus global sous RLS.

Le seed insère 8 documents globaux (org_id NULL) : ils restent visibles quel que
soit le tenant. Sautés sans AUGURA_DATABASE_URL ; en CI sous le rôle augura_app.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.corpus.repo import CorpusFilters, CorpusRepo
from augura_api.modules.corpus.service import CorpusService

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL absent — test d'intégration sauté")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s, s.begin():
            await s.execute(text("set local role augura_app"))
            await s.execute(set_user_stmt(USER))
            await s.execute(set_tenant_stmt(LUCIS))
            yield s
    finally:
        await engine.dispose()


async def test_feed_returns_global_corpus(session: AsyncSession) -> None:
    docs, total = await CorpusRepo(session).feed(CorpusFilters(), limit=20, offset=0)
    assert total == 8
    assert len(docs) == 8


async def test_sources_counts(session: AsyncSession) -> None:
    out = await CorpusService(CorpusRepo(session)).sources()
    assert out.total == 8
    by_source = {s.source_id: s.count for s in out.sources}
    assert by_source["pubmed"] == 3


async def test_coverage_matrix_zero_filled(session: AsyncSession) -> None:
    out = await CorpusService(CorpusRepo(session)).coverage()
    assert out.meta.total_docs == 8
    assert len(out.matrix) == 24  # 4 juridictions × 6 types
    cell = {(c.jurisdiction, c.evidence_type): c.doc_count for c in out.matrix}
    assert cell[("fda", "rct")] == 1
    assert cell[("fda", "preprint")] == 0  # cellule vide → gap


async def test_search_runs_against_match_chunks(session: AsyncSession) -> None:
    # Pas de chunks seedés → résultat vide, mais la fonction pgvector s'exécute.
    rows = await CorpusRepo(session).search([0.0] * 1536, 5, {})
    assert rows == []
