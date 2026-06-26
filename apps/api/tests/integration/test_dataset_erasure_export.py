"""Integration: GDPR Art 17 dataset erasure + Art 15/20 export bundle.

Tests:
- erase_dataset removes DB rows + backing storage objects (disk backend).
- erase_dataset on unknown dataset raises NotFoundError.
- export_dataset returns a bundle with correct shape + emits a usage_events row.
- export_dataset is tenant-isolated (foreign tenant cannot export).
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.config import Settings, get_settings
from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.analytics.models import UsageEvent
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


# ─── erase_dataset ────────────────────────────────────────────────────────────


async def test_erase_dataset_removes_db_rows_and_storage_objects(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After erasure the dataset is gone from the DB and from disk storage."""
    from augura_api.core import storage
    from augura_api.modules.datasets.models import Dataset

    tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    owner = CurrentTenant(tenant_id=tenant, user_id=USER, role="owner")

    dataset_id: UUID | None = None
    storage_path: str | None = None

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await _make_org(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        result = await svc.upload_dataset(
            owner,
            settings,
            files=[("cohort.csv", b"id,age\n1,40\n2,50\n")],
            name="to-erase",
            study_id=None,
        )
        dataset_id = result.dataset.id
        # Grab the real storage path from the DB (DatasetFile model).
        file_rows = await DatasetRepo(session).list_files(dataset_id)
        assert file_rows, "expected at least one file row"
        storage_path = file_rows[0].storage_path

    # Sanity: the object exists on disk.
    assert await storage.exists(settings, storage_path)

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        await svc.erase_dataset(owner, settings, dataset_id)

    # Storage object must be gone.
    assert not await storage.exists(settings, storage_path)

    # Dataset row must be gone (query without RLS as a sanity check via direct select).
    async with sm() as session:
        res = await session.execute(select(Dataset).where(Dataset.id == dataset_id))
        assert res.scalar_one_or_none() is None, "dataset row must be deleted after erasure"


async def test_erase_dataset_unknown_id_raises_not_found(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    owner = CurrentTenant(tenant_id=tenant, user_id=USER, role="owner")

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await _make_org(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        with pytest.raises(NotFoundError):
            await svc.erase_dataset(owner, settings, uuid4())


# ─── export_dataset ───────────────────────────────────────────────────────────


async def test_export_dataset_returns_bundle_and_emits_usage_event(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """export_dataset returns a DatasetExport with the expected fields and emits
    a usage_events row with event_type='dataset.exported'."""
    tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    owner = CurrentTenant(tenant_id=tenant, user_id=USER, role="owner")

    dataset_id: UUID | None = None

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await _make_org(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        result = await svc.upload_dataset(
            owner,
            settings,
            files=[("export.csv", b"id,score\n1,95\n2,87\n")],
            name="export-me",
            study_id=None,
        )
        dataset_id = result.dataset.id

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        bundle = await svc.export_dataset(owner, dataset_id)

        # Shape checks.
        assert bundle.dataset.id == dataset_id
        assert bundle.dataset.name == "export-me"
        assert len(bundle.files) == 1
        col_names = {c.name for c in bundle.columns}
        assert {"id", "score"} <= col_names

        # Usage event must be flushed into the session.
        res = await session.execute(
            select(UsageEvent)
            .where(
                UsageEvent.org_id == tenant,
                UsageEvent.event_type == "dataset.exported",
            )
            .order_by(desc(UsageEvent.created_at))
            .limit(1)
        )
        event = res.scalar_one_or_none()
        assert event is not None, "expected a dataset.exported usage_event"
        assert event.metadata_ is not None
        assert str(dataset_id) in str(event.metadata_.get("dataset_id", ""))


async def test_export_dataset_tenant_isolated(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tenant cannot export another tenant's dataset."""
    owner_tenant = TenantId(uuid4())
    intruder_tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    owner = CurrentTenant(tenant_id=owner_tenant, user_id=USER, role="owner")

    dataset_id: UUID | None = None

    async with sm() as session, session.begin():
        await _scope(session, owner_tenant)
        await _make_org(session, owner_tenant)
        result = await DatasetService(DatasetRepo(session)).upload_dataset(
            owner, settings, files=[("f.csv", b"id\n1\n")], name="private", study_id=None
        )
        dataset_id = result.dataset.id

    async with sm() as session, session.begin():
        await _scope(session, intruder_tenant)
        await _make_org(session, intruder_tenant)
        intruder = CurrentTenant(tenant_id=intruder_tenant, user_id=USER, role="owner")
        with pytest.raises(NotFoundError):
            await DatasetService(DatasetRepo(session)).export_dataset(intruder, dataset_id)
