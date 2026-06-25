"""Integration: the ingestion PII gate rejects direct-identifier headers under a real DB
(the pii_pattern_catalog is loaded by the seed). Skipped without AUGURA_DATABASE_URL."""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.datasets.repo import DatasetRepo

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


async def test_pii_patterns_loaded_and_scan_flags_email(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    async with sm() as session, session.begin():
        await session.execute(text("set local role augura_app"))
        await session.execute(set_user_stmt(USER))
        await session.execute(set_tenant_stmt(LUCIS))
        rows = await DatasetRepo(session).list_active_pii_patterns()
    assert rows, "pii_pattern_catalog should be seeded with active patterns"
    from augura_api.modules.datasets.pii import PiiPattern, scan_headers_for_pii

    patterns = [PiiPattern(key=k, pattern=p) for k, p in rows]
    hits = scan_headers_for_pii(["patient_email", "hba1c_12m"], patterns)
    assert any(h.column == "patient_email" for h in hits)
    assert all(h.column != "hba1c_12m" for h in hits)
