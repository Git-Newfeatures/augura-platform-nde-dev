"""Integration tests for the reference module — global catalogs + tenant org + RLS.

Skipped if AUGURA_DATABASE_URL is not set. In CI, run after the seed, under the
augura_app role (NOT RLS-exempt).
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
from augura_api.modules.reference.repo import ReferenceRepo

pytestmark = pytest.mark.integration

USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(session: AsyncSession, tenant: TenantId, user: UserId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(user))
    await session.execute(set_tenant_stmt(tenant))


async def test_reference_catalogs_are_readable_and_ordered(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    tenant = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        repo = ReferenceRepo(session)
        sources = await repo.list_cesl_sources()
        designs = await repo.list_study_designs()

    assert {s.code for s in sources} >= {"pubmed", "clinicaltrials", "maude", "guidance"}
    assert all(s.active for s in sources)
    assert [s.sort_order for s in sources] == sorted(s.sort_order for s in sources)
    assert {d.code for d in designs} >= {"retro_cohort", "mediation"}
    assert [d.sort_order for d in designs] == sorted(d.sort_order for d in designs)


async def test_tenant_reads_only_its_own_org(sm: async_sessionmaker[AsyncSession]) -> None:
    tenant = TenantId(uuid4())
    # INSERT of the org scoped to the current tenant: the orgs `tenant_self` policy
    # (using id = app.tenant_id, WITH CHECK defaults to USING) permits this row.
    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        await session.execute(
            text(
                "insert into orgs (id, name, slug, cesl_profile) "
                "values (cast(:id as uuid), :n, :s, cast(:p as jsonb))"
            ).bindparams(
                id=str(tenant),
                n="IT Org",
                s="it-" + uuid4().hex[:8],
                p='{"clinical_domain": ["x"]}',
            )
        )

    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        org = await ReferenceRepo(session).get_org(tenant)
        assert org is not None
        assert org.cesl_profile == {"clinical_domain": ["x"]}

    other = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, other, USER)
        assert await ReferenceRepo(session).get_org(tenant) is None  # RLS isolates


async def test_reference_tables_are_read_only_for_tenant(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    tenant = TenantId(uuid4())
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with sm() as session, session.begin():
            await _scope(session, tenant, USER)
            await session.execute(
                text("insert into cesl_sources (code, label) values (:c, :l)").bindparams(
                    c="rogue-" + uuid4().hex[:6], l="nope"
                )
            )
