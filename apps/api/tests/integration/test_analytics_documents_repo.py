"""Integration tests analytics + documents — usage/admin-stats and generation.

Under the augura_app role (RLS active).
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.analytics import log_usage
from augura_api.modules.analytics.service import AnalyticsService
from augura_api.modules.documents import schemas as doc_schemas
from augura_api.modules.documents.repo import DocumentRepo
from augura_api.modules.documents.service import DocumentService

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))
TENANT = CurrentTenant(tenant_id=LUCIS, user_id=USER, role="owner")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s, s.begin():
            await s.execute(text("set local role augura_app"))
            await s.execute(set_user_stmt(USER))
            await s.execute(set_tenant_stmt(LUCIS))
            yield s
    finally:
        await engine.dispose()


async def test_usage_logging_feeds_admin_stats(session: AsyncSession) -> None:
    await log_usage(session, tenant_id=LUCIS, user_id=USER, event_type="query", route="dag")
    stats = await AnalyticsService(session).admin_stats(TENANT)
    assert stats.total_events >= 1
    assert stats.by_type.get("query", 0) >= 1
    assert stats.unique_users >= 1


async def test_document_generate_creates_job_and_row(session: AsyncSession) -> None:
    created = await DocumentService(session).generate(
        TENANT, doc_schemas.GenerateRequest(type="report")
    )
    assert created.status == "pending"
    fetched = await DocumentService(session).get(TENANT, created.document_id)
    assert fetched.type == "report"
    listed = await DocumentService(session).list_documents(TENANT)
    assert any(d.id == created.document_id for d in listed)


async def test_document_content_round_trips_through_db(session: AsyncSession) -> None:
    """The document bytes live IN THE DATABASE (generated_documents.content): what the
    worker writes, the ASGI process reads back — consistent cross-container, unlike disk."""
    created = await DocumentService(session).generate(
        TENANT, doc_schemas.GenerateRequest(type="report")
    )
    html = b"<html><body>test document</body></html>"
    await DocumentRepo(session).set_status(
        LUCIS, created.document_id, status="ready", storage_path="logical/ref", content=html
    )
    doc_type, data = await DocumentService(session).download(TENANT, created.document_id)
    assert doc_type == "report"
    assert data == html
