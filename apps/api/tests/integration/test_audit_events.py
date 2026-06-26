"""Integration: audit_events change-capture triggers on regulated tables.

Runs in the db-bundle CI job (pytest -m integration). Skipped locally without
AUGURA_DATABASE_URL. NEVER point this at the prod project (conftest guards it).

Mirrors the harness from tests/integration/test_audit_append_only.py:
  set local role augura_app + app.user_id + app.tenant_id GUCs.
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


async def test_insert_creates_audit_row(sm: async_sessionmaker[AsyncSession]) -> None:
    """INSERT on a regulated table produces an audit_events row with op='I'."""
    async with sm() as session, session.begin():
        await _scope(session, LUCIS, USER)

        # Insert a study row.
        result = await session.execute(
            text(
                "insert into studies (org_id, title, status) "
                "values (:org, 'Audit Test Study', 'draft') returning id"
            ).bindparams(org=str(LUCIS))
        )
        study_id = str(result.scalar_one())

        # Exactly one audit row for the insert.
        row = await session.execute(
            text(
                "select op, actor_user_id, org_id, new_row "
                "from audit_events "
                "where table_name = 'studies' and row_pk = :pk"
            ).bindparams(pk=study_id)
        )
        audit = row.mappings().one()
        assert audit["op"] == "I"
        assert str(audit["actor_user_id"]) == str(USER)
        assert str(audit["org_id"]) == str(LUCIS)
        assert audit["new_row"]["id"] == study_id

        # Teardown: remove fixture study (and its audit row via the trigger).
        await session.execute(text("delete from studies where id = :id").bindparams(id=study_id))


async def test_update_creates_audit_row_with_old_and_new(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    """UPDATE produces an op='U' audit row carrying both old_row and new_row."""
    async with sm() as session, session.begin():
        await _scope(session, LUCIS, USER)

        result = await session.execute(
            text(
                "insert into studies (org_id, title, status) "
                "values (:org, 'Update Test', 'draft') returning id"
            ).bindparams(org=str(LUCIS))
        )
        study_id = str(result.scalar_one())

        await session.execute(
            text("update studies set title = 'Updated Title' where id = :id").bindparams(
                id=study_id
            )
        )

        row = await session.execute(
            text(
                "select op, old_row, new_row "
                "from audit_events "
                "where table_name = 'studies' and row_pk = :pk and op = 'U'"
            ).bindparams(pk=study_id)
        )
        audit = row.mappings().one()
        assert audit["op"] == "U"
        assert audit["old_row"]["title"] == "Update Test"
        assert audit["new_row"]["title"] == "Updated Title"

        # Teardown.
        await session.execute(text("delete from studies where id = :id").bindparams(id=study_id))


async def test_audit_events_update_denied(sm: async_sessionmaker[AsyncSession]) -> None:
    """augura_app cannot UPDATE audit_events (append-only invariant)."""
    with pytest.raises(DBAPIError, match="permission denied"):
        async with sm() as session, session.begin():
            await _scope(session, LUCIS, USER)
            await session.execute(
                text("update audit_events set op = 'X' where org_id = :o").bindparams(o=str(LUCIS))
            )


async def test_audit_events_delete_denied(sm: async_sessionmaker[AsyncSession]) -> None:
    """augura_app cannot DELETE audit_events (append-only invariant)."""
    with pytest.raises(DBAPIError, match="permission denied"):
        async with sm() as session, session.begin():
            await _scope(session, LUCIS, USER)
            await session.execute(
                text("delete from audit_events where org_id = :o").bindparams(o=str(LUCIS))
            )
