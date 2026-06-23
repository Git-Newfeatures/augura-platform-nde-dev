"""Integration: upload (A2) → run DQ → bundle persisted (+ RLS).

Skipped if AUGURA_DATABASE_URL is not set. CI: after seed, under the augura_app role.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.config import get_settings
from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.datasets.service import DatasetService
from augura_api.modules.dq.repo import DqRepo
from augura_api.modules.dq.service import DqService

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


async def _scope(session: AsyncSession, tenant: TenantId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(USER))
    await session.execute(set_tenant_stmt(tenant))


def _tenant(t: TenantId) -> CurrentTenant:
    return CurrentTenant(tenant_id=t, user_id=USER, role="owner")


async def test_upload_then_run_dq_persists_scored_bundle(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())
    monkeypatch.setenv("AUGURA_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("AUGURA_ENV", os.environ.get("AUGURA_ENV", "dev"))
    get_settings.cache_clear()
    settings = get_settings()

    csv = b"id,val\n1,10\n2,11\n3,\n4,9\n5,1000\n6,10\n7,11\n8,9\n9,10\n10,12\n"

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await session.execute(
            text(
                "insert into orgs (id, name, slug) values (cast(:i as uuid), 'IT', :s)"
            ).bindparams(i=str(tenant), s="it-" + uuid4().hex[:8])
        )
        up = await DatasetService(DatasetRepo(session)).upload_dataset(
            _tenant(tenant), settings, files=[("c.csv", csv)], name=None, study_id=None
        )
        res = await DqService(DqRepo(session), DatasetRepo(session)).run(
            _tenant(tenant), settings, up.dataset.id
        )

    assert res.overall_score is not None
    assert 0.0 <= res.overall_score <= 1.0

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        latest = await DqService(DqRepo(session), DatasetRepo(session)).latest(
            _tenant(tenant), up.dataset.id
        )

    assert latest.bundle["provenance"]
    cats = {f["category"] for f in latest.bundle["provenance"]}
    assert "missing" in cats  # 'val' has a missing value
    assert "range" in cats  # 1000 is an IQR outlier
