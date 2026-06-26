"""Unit tests for Task 3: retention_until column + purge_expired primitive.

Covers:
  - purge_expired selects only expired datasets (retention_until < now())
    and calls erase_dataset for each of them.
  - Datasets without retention_until or with a future retention_until are left alone.
  - The returned PurgeExpiredResult carries the correct count and IDs.
  - Non-owner HTTP callers receive 403 on POST /datasets/purge-expired.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from augura_api.core.config import Settings
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.service import DatasetService

_NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
_TENANT_ID = TenantId(uuid4())
_USER_ID = UserId(uuid4())

TENANT = CurrentTenant(tenant_id=_TENANT_ID, user_id=_USER_ID, role="owner")


def _make_settings() -> Settings:
    return Settings(env="dev", artifacts_dir="/tmp")  # pyright: ignore[reportCallIssue]


def _make_dataset(dataset_id: object = None) -> SimpleNamespace:
    did = dataset_id or uuid4()
    return SimpleNamespace(
        id=did,
        org_id=_TENANT_ID,
        name="ds",
        status="uploaded",
        study_id=None,
        storage_path=None,
        row_count=0,
        created_at=_NOW,
        retention_until=None,
    )


def _mock_repo(
    *,
    expired: list[SimpleNamespace] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.session = AsyncMock()
    repo.list_expired_datasets = AsyncMock(return_value=expired or [])
    # get_dataset needed by erase_dataset's _require_dataset
    repo.get_dataset = AsyncMock(return_value=None)
    repo.list_files = AsyncMock(return_value=[])
    repo.delete_dataset = AsyncMock()
    return repo


# ── purge_expired — core selection logic ──────────────────────────────────────


async def test_purge_expired_calls_erase_for_each_expired_dataset() -> None:
    """purge_expired must call erase_dataset for each expired dataset returned
    by list_expired_datasets — 2 expired means 2 erase calls."""
    ds1_id = uuid4()
    ds2_id = uuid4()
    ds1 = _make_dataset(ds1_id)
    ds2 = _make_dataset(ds2_id)
    repo = _mock_repo(expired=[ds1, ds2])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _make_settings()

    erased: list[object] = []

    async def _fake_erase(tenant: CurrentTenant, s: Settings, dataset_id: object) -> None:
        erased.append(dataset_id)

    with patch.object(svc, "erase_dataset", side_effect=_fake_erase):
        result = await svc.purge_expired(TENANT, settings)

    assert result.erased_count == 2
    assert set(result.erased_ids) == {str(ds1_id), str(ds2_id)}
    assert set(erased) == {ds1_id, ds2_id}


async def test_purge_expired_skips_when_no_expired_datasets() -> None:
    """When no datasets have passed their retention_until, purge_expired returns 0."""
    repo = _mock_repo(expired=[])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    erased: list[object] = []

    async def _fake_erase(
        tenant: CurrentTenant, s: Settings, dataset_id: object
    ) -> None:  # pragma: no cover
        erased.append(dataset_id)

    with patch.object(svc, "erase_dataset", side_effect=_fake_erase):
        result = await svc.purge_expired(TENANT, _make_settings())

    assert result.erased_count == 0
    assert result.erased_ids == []
    assert erased == []


async def test_purge_expired_erases_exactly_expired_not_valid() -> None:
    """repo.list_expired_datasets filters by the DB; purge_expired erases exactly
    the rows returned — if the repo returns 1 expired and 0 valid, only 1 is erased."""
    expired_id = uuid4()
    expired_ds = _make_dataset(expired_id)
    repo = _mock_repo(expired=[expired_ds])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    erased: list[object] = []

    async def _fake_erase(tenant: CurrentTenant, s: Settings, dataset_id: object) -> None:
        erased.append(dataset_id)

    with patch.object(svc, "erase_dataset", side_effect=_fake_erase):
        result = await svc.purge_expired(TENANT, _make_settings())

    assert result.erased_count == 1
    assert result.erased_ids == [str(expired_id)]
    assert erased == [expired_id]


async def test_purge_expired_returns_purge_expired_result() -> None:
    """Result is a PurgeExpiredResult pydantic model."""
    repo = _mock_repo(expired=[])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch.object(svc, "erase_dataset", new=AsyncMock()):
        result = await svc.purge_expired(TENANT, _make_settings())

    assert isinstance(result, schemas.PurgeExpiredResult)


# ── HTTP owner-gating ──────────────────────────────────────────────────────────


async def test_purge_expired_non_owner_gets_403() -> None:
    """POST /datasets/purge-expired must be 403 for member and viewer roles."""
    from collections.abc import AsyncIterator
    from uuid import uuid4 as _uuid4

    import httpx

    from augura_api.core.deps import get_current_tenant, get_session
    from augura_api.core.ids import TenantId as _TenantId
    from augura_api.core.ids import UserId as _UserId
    from augura_api.core.tenancy import CurrentTenant as _CT
    from augura_api.main import create_app

    for role in ("member", "viewer"):

        def _non_owner(r: str = role) -> _CT:
            return _CT(tenant_id=_TenantId(_uuid4()), user_id=_UserId(_uuid4()), role=r)

        async def _session() -> AsyncIterator[object]:
            yield object()

        app = create_app()
        app.dependency_overrides[get_current_tenant] = _non_owner
        app.dependency_overrides[get_session] = _session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/datasets/purge-expired")

        assert resp.status_code == 403, f"expected 403 for role={role}, got {resp.status_code}"
