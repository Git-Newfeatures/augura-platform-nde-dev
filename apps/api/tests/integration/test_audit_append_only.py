"""Integration: usage_events is append-only under the augura_app role.

Runs in the db-bundle CI job (pytest -m integration). Skipped locally without
AUGURA_DATABASE_URL. NEVER point this at the prod project (conftest guards it).
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
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


async def test_usage_events_insert_allowed(sm: async_sessionmaker[AsyncSession]) -> None:
    async with sm() as session, session.begin():
        await _scope(session, LUCIS, USER)
        await session.execute(
            text(
                "insert into usage_events (org_id, user_id, event_type) values (:o, :u, 'login')"
            ).bindparams(o=str(LUCIS), u=str(USER))
        )  # commits cleanly → INSERT is permitted


async def test_usage_events_update_denied(sm: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with sm() as session, session.begin():
            await _scope(session, LUCIS, USER)
            await session.execute(
                text(
                    "update usage_events set event_type = 'tampered' where org_id = :o"
                ).bindparams(o=str(LUCIS))
            )


async def test_usage_events_delete_denied(sm: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with sm() as session, session.begin():
            await _scope(session, LUCIS, USER)
            await session.execute(
                text("delete from usage_events where org_id = :o").bindparams(o=str(LUCIS))
            )
