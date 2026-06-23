"""Integration: dataset upload → parse → profile → persistence (+ RLS)."""

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


async def test_upload_persists_dataset_and_profiled_columns(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())

    # Settings is frozen=True (pydantic model_config) → cannot use object.__setattr__.
    # Override via env var before clearing the lru_cache so get_settings() returns a
    # fresh instance pointing storage at tmp_path.
    monkeypatch.setenv("AUGURA_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("AUGURA_ENV", os.environ.get("AUGURA_ENV", "dev"))
    get_settings.cache_clear()
    settings = get_settings()

    csv = b"member_id,age,sex\n1,40,M\n2,55,F\n3,,F\n4,61,M\n5,48,F\n6,52,M\n"

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        # datasets.org_id references orgs(id) — create the tenant's org first. The
        # orgs `tenant_self` policy (with check defaults to id = app.tenant_id)
        # permits inserting the row whose id is the scoped tenant.
        await session.execute(
            text(
                "insert into orgs (id, name, slug) values (cast(:i as uuid), 'IT', :s)"
            ).bindparams(i=str(tenant), s="it-" + uuid4().hex[:8])
        )
        svc = DatasetService(DatasetRepo(session))
        result = await svc.upload_dataset(
            CurrentTenant(tenant_id=tenant, user_id=USER, role="owner"),
            settings,
            filename="cohort.csv",
            data=csv,
            name=None,
            study_id=None,
        )

    assert result.dataset.row_count == 6
    assert result.dataset.storage_path
    by_name = {c.name: c for c in result.columns}
    assert by_name["age"].value_kind == "numeric"
    assert by_name["sex"].value_kind == "binary"
    assert by_name["sex"].n_distinct == 2
