"""Intégration du module semantic — taxonomie globale + RLS lecture seule.

Sauté si AUGURA_DATABASE_URL absent. CI : après seed, sous le rôle augura_app.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.semantic.repo import SemanticRepo

pytestmark = pytest.mark.integration

USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL absent — test d'intégration sauté")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(session: AsyncSession, tenant: TenantId, user: UserId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(user))
    await session.execute(set_tenant_stmt(tenant))


async def test_taxonomy_readable_and_seeded(sm: async_sessionmaker[AsyncSession]) -> None:
    tenant = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        repo = SemanticRepo(session)
        concepts = await repo.list_concepts()
        archetypes = await repo.list_archetypes()
        constraints = await repo.list_constraints()
    assert len(concepts) > 100  # ~171 seeded
    assert all(c.active for c in concepts)
    assert [c.local_concept_id for c in concepts] == sorted(c.local_concept_id for c in concepts)
    assert len(archetypes) >= 1
    assert len(constraints) >= 1


async def test_taxonomy_is_read_only_for_tenant(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    tenant = TenantId(uuid4())
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with sm() as session, session.begin():
            await _scope(session, tenant, USER)
            await session.execute(
                text(
                    "insert into taxonomy_concepts "
                    "(local_concept_id, layer, concept_name, augura_domain, "
                    "review_status, version, active) "
                    "values (:i, 1, 'x', 'd', 'r', 'v', true)"
                ).bindparams(i="rogue-" + uuid4().hex[:6])
            )
