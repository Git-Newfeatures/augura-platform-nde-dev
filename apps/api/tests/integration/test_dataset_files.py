"""Integration: multi-file datasets — upload N, add, remove, file_count, RLS."""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.config import Settings, get_settings
from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.errors import NotFoundError
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


def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("AUGURA_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("AUGURA_ENV", os.environ.get("AUGURA_ENV", "dev"))
    get_settings.cache_clear()
    return get_settings()


async def _make_org(session: AsyncSession, tenant: TenantId) -> None:
    await session.execute(
        text("insert into orgs (id, name, slug) values (cast(:i as uuid), 'IT', :s)").bindparams(
            i=str(tenant), s="it-" + uuid4().hex[:8]
        )
    )


async def test_upload_multi_unions_columns_and_sums_rows(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    tenant_ctx = CurrentTenant(tenant_id=tenant, user_id=USER, role="owner")

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await _make_org(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        result = await svc.upload_dataset(
            tenant_ctx,
            settings,
            files=[
                ("a.csv", b"id,age\n1,40\n2,50\n"),
                ("b.csv", b"id,age,crp\n3,60,5\n"),
            ],
            name="cohort",
            study_id=None,
        )

    assert result.dataset.row_count == 3
    assert result.dataset.file_count == 2
    assert {c.name for c in result.columns} == {"id", "age", "crp"}
    assert len(result.files) == 2


async def test_add_then_remove_file_reprofiles(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    tenant_ctx = CurrentTenant(tenant_id=tenant, user_id=USER, role="owner")

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await _make_org(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        created = await svc.upload_dataset(
            tenant_ctx, settings, files=[("a.csv", b"id,age\n1,40\n")], name="c", study_id=None
        )
        dsid = created.dataset.id

        added = await svc.add_files(
            tenant_ctx, settings, dsid, [("b.csv", b"id,age,crp\n2,50,9\n")]
        )
        assert added.dataset.file_count == 2
        assert added.dataset.row_count == 2
        assert any("crp" in w for w in added.warnings)

        files = await svc.list_files(tenant_ctx, dsid)
        to_remove = next(f for f in files if f.filename == "b.csv")
        removed = await svc.remove_file(tenant_ctx, settings, dsid, to_remove.id)
        assert removed.dataset.file_count == 1
        assert removed.dataset.row_count == 1
        assert "crp" not in {c.name for c in removed.columns}


async def test_files_are_tenant_isolated(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = TenantId(uuid4())
    intruder = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    owner_ctx = CurrentTenant(tenant_id=owner, user_id=USER, role="owner")

    async with sm() as session, session.begin():
        await _scope(session, owner)
        await _make_org(session, owner)
        created = await DatasetService(DatasetRepo(session)).upload_dataset(
            owner_ctx, settings, files=[("a.csv", b"id\n1\n")], name="c", study_id=None
        )
        dsid = created.dataset.id

    # A different tenant must not see the owner's dataset/files (RLS via dataset).
    async with sm() as session, session.begin():
        await _scope(session, intruder)
        await _make_org(session, intruder)
        intruder_ctx = CurrentTenant(tenant_id=intruder, user_id=USER, role="owner")
        with pytest.raises(NotFoundError):
            await DatasetService(DatasetRepo(session)).list_files(intruder_ctx, dsid)
