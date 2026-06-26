"""Unit tests for DatasetService.erase_dataset and DatasetService.export_dataset.

These tests use async mock repos (no DB) to exercise the service logic in isolation:
- erase_dataset deletes DB rows, returns the storage paths, and calls NO storage I/O.
- erase_dataset raises NotFoundError when the dataset is not found.
- export_dataset returns a DatasetExport bundle with correct shape.
- export_dataset emits a log_usage call with event_type='dataset.exported'.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.service import DatasetService

_NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
_TENANT_ID = TenantId(uuid4())
_USER_ID = UserId(uuid4())
_DATASET_ID = uuid4()
_FILE_ID = uuid4()

TENANT = CurrentTenant(tenant_id=_TENANT_ID, user_id=_USER_ID, role="owner")


def _make_dataset() -> SimpleNamespace:
    return SimpleNamespace(
        id=_DATASET_ID,
        org_id=_TENANT_ID,
        name="my-dataset",
        status="ready",
        study_id=None,
        storage_path=None,
        row_count=2,
        created_at=_NOW,
    )


def _make_file(storage_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=_FILE_ID,
        dataset_id=_DATASET_ID,
        filename="data.csv",
        storage_path=storage_path,
        row_count=2,
        headers=["id", "age"],
        position=0,
        created_at=_NOW,
    )


def _make_column(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        dataset_id=_DATASET_ID,
        sheet="default",
        name=name,
        value_kind="numeric",
        n_total=2,
        n_non_null=2,
        null_pct=0.0,
        n_distinct=2,
        value_min=None,
        value_max=None,
        top_values=None,
        proposed_role=None,
        proposed_group=None,
        proposed_canonical_id=None,
        confidence=None,
        rationale=None,
        user_decision="pending",
        final_role=None,
        final_canonical_id=None,
    )


def _mock_repo(
    *,
    dataset: SimpleNamespace | None = None,
    files: list[SimpleNamespace] | None = None,
    columns: list[SimpleNamespace] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.session = AsyncMock()
    repo.get_dataset = AsyncMock(return_value=dataset)
    repo.list_files = AsyncMock(return_value=files or [])
    repo.list_columns = AsyncMock(return_value=columns or [])
    repo.delete_dataset = AsyncMock()
    repo.count_columns = AsyncMock(return_value=len(columns or []))
    repo.count_files = AsyncMock(return_value=len(files or []))
    return repo


# ─── erase_dataset ────────────────────────────────────────────────────────────


async def test_erase_dataset_returns_storage_paths_and_deletes_db_rows() -> None:
    """erase_dataset must delete DB rows and return the storage paths; it must NOT
    call delete_bytes itself (storage deletion is deferred to the caller via BackgroundTask)."""
    storage_path = f"org/{_TENANT_ID}/file-abc.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    repo = _mock_repo(dataset=dataset, files=[file_])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch(
        "augura_api.modules.datasets.service.delete_bytes", new_callable=AsyncMock
    ) as mock_delete:
        paths = await svc.erase_dataset(TENANT, _DATASET_ID)

    repo.delete_dataset.assert_awaited_once_with(_TENANT_ID, _DATASET_ID)
    assert paths == [storage_path]
    mock_delete.assert_not_called()


async def test_erase_dataset_raises_not_found_for_unknown_dataset() -> None:
    repo = _mock_repo(dataset=None)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with pytest.raises(NotFoundError):
        await svc.erase_dataset(TENANT, uuid4())


async def test_erase_dataset_returns_all_paths_for_multiple_files() -> None:
    """All storage paths from all files must be returned; no storage I/O inside the service."""
    paths = [f"org/{_TENANT_ID}/file-{i}.csv" for i in range(3)]
    dataset = _make_dataset()
    files = [_make_file(p) for p in paths]
    repo = _mock_repo(dataset=dataset, files=files)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch(
        "augura_api.modules.datasets.service.delete_bytes", new_callable=AsyncMock
    ) as mock_delete:
        returned_paths = await svc.erase_dataset(TENANT, _DATASET_ID)

    assert set(returned_paths) == set(paths)
    mock_delete.assert_not_called()


async def test_erase_dataset_no_storage_io_inside_service() -> None:
    """Regression: the service must NOT touch storage (delete_bytes). This is the correctness
    invariant — if the DB commit later fails, no bytes have been irreversibly deleted."""
    storage_path = f"org/{_TENANT_ID}/file.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    repo = _mock_repo(dataset=dataset, files=[file_])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch(
        "augura_api.modules.datasets.service.delete_bytes", new_callable=AsyncMock
    ) as mock_delete:
        await svc.erase_dataset(TENANT, _DATASET_ID)

    mock_delete.assert_not_called()


# ─── export_dataset ───────────────────────────────────────────────────────────


async def test_export_dataset_returns_bundle_shape() -> None:
    """export_dataset must return a DatasetExport with the correct structure."""
    dataset = _make_dataset()
    files = [_make_file(f"org/{_TENANT_ID}/f.csv")]
    columns = [_make_column("id"), _make_column("age")]
    repo = _mock_repo(dataset=dataset, files=files, columns=columns)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        bundle = await svc.export_dataset(TENANT, _DATASET_ID)

    assert isinstance(bundle, schemas.DatasetExport)
    assert bundle.dataset.id == _DATASET_ID
    assert bundle.dataset.name == "my-dataset"
    assert len(bundle.files) == 1
    assert {c.name for c in bundle.columns} == {"id", "age"}


async def test_export_dataset_emits_log_usage_event() -> None:
    """export_dataset must emit a usage_events row with event_type='dataset.exported'."""
    dataset = _make_dataset()
    repo = _mock_repo(dataset=dataset)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        await svc.export_dataset(TENANT, _DATASET_ID)

    mock_analytics.log_usage.assert_awaited_once()
    kwargs = mock_analytics.log_usage.call_args.kwargs
    assert kwargs["event_type"] == "dataset.exported"
    assert kwargs["tenant_id"] == _TENANT_ID
    assert kwargs["user_id"] == _USER_ID


async def test_export_dataset_raises_not_found_for_unknown() -> None:
    repo = _mock_repo(dataset=None)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with pytest.raises(NotFoundError):
        await svc.export_dataset(TENANT, uuid4())


# ─── remove_file — no storage I/O inside service ──────────────────────────────


async def test_remove_file_returns_result_and_path_no_storage_io() -> None:
    """remove_file must return (UploadResult, storage_path) and NOT call delete_bytes;
    the router schedules object deletion post-commit via BackgroundTask."""
    storage_path = f"org/{_TENANT_ID}/f.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    column = _make_column("id")

    from augura_api.core.config import Settings

    settings = Settings(env="dev", artifacts_dir="/tmp")  # pyright: ignore[reportCallIssue]

    repo = _mock_repo(dataset=dataset, files=[], columns=[column])
    repo.get_file = AsyncMock(return_value=file_)
    repo.delete_file = AsyncMock()
    repo.replace_columns = AsyncMock(return_value=[column])
    repo.set_storage_and_rowcount = AsyncMock()
    repo.next_position = AsyncMock(return_value=0)
    repo.list_active_pii_patterns = AsyncMock(return_value=[])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch(
        "augura_api.modules.datasets.service.delete_bytes", new_callable=AsyncMock
    ) as mock_delete:
        result, returned_path = await svc.remove_file(TENANT, settings, _DATASET_ID, _FILE_ID)

    assert returned_path == storage_path
    assert isinstance(result, schemas.UploadResult)
    mock_delete.assert_not_called()


# ─── owner-gating HTTP test ────────────────────────────────────────────────────


async def test_erase_dataset_non_owner_gets_403() -> None:
    """DELETE /datasets/{id} must be 403 for member and viewer roles (OwnerTenantDep gate)."""
    from collections.abc import AsyncIterator
    from uuid import uuid4 as _uuid4

    import httpx

    from augura_api.core.deps import get_current_tenant, get_session
    from augura_api.core.ids import TenantId, UserId
    from augura_api.core.tenancy import CurrentTenant
    from augura_api.main import create_app

    for role in ("member", "viewer"):

        def _non_owner(r: str = role) -> CurrentTenant:
            return CurrentTenant(tenant_id=TenantId(_uuid4()), user_id=UserId(_uuid4()), role=r)

        async def _session() -> AsyncIterator[object]:
            yield object()

        app = create_app()
        app.dependency_overrides[get_current_tenant] = _non_owner
        app.dependency_overrides[get_session] = _session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/datasets/{_uuid4()}")

        assert resp.status_code == 403, f"expected 403 for role={role}, got {resp.status_code}"
