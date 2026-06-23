"""Integration tests simulation + jobs — seeded results + job idempotence.

Under the augura_app role (RLS active). The seed provides 12 simulation_results rows
for validation_v1 (3 scenarios × 4 estimators).
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.jobs import create_job
from augura_api.modules.simulation.repo import SimulationRepo

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


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


async def test_validated_results_seeded(session: AsyncSession) -> None:
    rows = await SimulationRepo(session).list_results(LUCIS, "validation_v1")
    assert len(rows) == 12  # 3 scenarios × 4 estimators
    assert {r.scenario for r in rows} == {"baseline", "conservative", "high_risk"}


async def test_create_job_is_idempotent(session: AsyncSession) -> None:
    key = "boot-" + uuid4().hex
    first = await create_job(
        session, LUCIS, type="bootstrap", payload={"effect": 0.3}, idempotency_key=key
    )
    second = await create_job(
        session, LUCIS, type="bootstrap", payload={"effect": 0.2}, idempotency_key=key
    )
    assert first.id == second.id  # same key → same job (no double bootstrap)
    assert first.status == "queued"


async def test_create_run_links_job(session: AsyncSession) -> None:
    job = await create_job(
        session, LUCIS, type="bootstrap", payload={}, idempotency_key=uuid4().hex
    )
    run = await SimulationRepo(session).create_run(
        LUCIS, study_id=None, params={"n": 824}, job_id=job.id
    )
    assert run.job_id == job.id
    assert run.status == "queued"
