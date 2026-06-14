"""Tests d'intégration du module studies — repos + RLS sur un vrai Postgres.

Sautés si AUGURA_DATABASE_URL est absent (local sans base). En CI, tournent
sous le rôle `augura_app` (NON exempt de RLS) pour prouver l'isolation tenant.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import StudyId, TenantId, UserId
from augura_api.modules.studies.repo import StudyRepo

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
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


async def test_create_list_and_state_versioning(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    slug = "it-" + uuid4().hex[:10]
    async with sm() as session, session.begin():
        await _scope(session, LUCIS, USER)
        repo = StudyRepo(session)
        study = await repo.create(
            LUCIS,
            name="Integration",
            slug=slug,
            tagline=None,
            category=None,
            framework=None,
            n_subjects=None,
            created_by=USER,
        )
        sid = StudyId(study.id)
        await repo.add_state(LUCIS, sid, state={"step": "one"}, created_by=USER)
        s2 = await repo.add_state(LUCIS, sid, state={"step": "two"}, created_by=USER)
        assert s2.version == 2

    async with sm() as session, session.begin():
        await _scope(session, LUCIS, USER)
        repo = StudyRepo(session)
        rows = await repo.list_for_tenant(LUCIS)
        assert any(r.slug == slug for r in rows)
        latest = await repo.latest_state(LUCIS, sid)
        assert latest is not None
        assert latest.version == 2
        assert latest.state == {"step": "two"}


async def test_rls_blocks_other_tenant(sm: async_sessionmaker[AsyncSession]) -> None:
    other = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, other, USER)
        count = (await session.execute(text("select count(*) from studies"))).scalar_one()
        assert count == 0
        assert await StudyRepo(session).list_for_tenant(other) == []
