"""Unit tests for DatasetService.erase_dataset and DatasetService.export_dataset.

These tests use async mock repos (no DB) to exercise the service logic in isolation:
- erase_dataset gathers storage paths, deletes DB rows, then calls delete_bytes per file.
- erase_dataset raises NotFoundError when the dataset is not found.
- export_dataset returns a DatasetExport bundle with correct shape.
- export_dataset emits a log_usage call with event_type='dataset.exported'.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from augura_api.core.config import Settings
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


def _settings(tmp_path: object) -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue]
        env="dev", artifacts_dir=str(tmp_path)
    )


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


async def test_erase_dataset_calls_delete_bytes_per_file(tmp_path: object) -> None:
    """erase_dataset must call delete_bytes for each file's storage_path."""
    storage_path = f"org/{_TENANT_ID}/file-abc.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    repo = _mock_repo(dataset=dataset, files=[file_])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _settings(tmp_path)

    with patch(
        "augura_api.modules.datasets.service.delete_bytes", new_callable=AsyncMock
    ) as mock_delete:
        await svc.erase_dataset(TENANT, settings, _DATASET_ID)

    repo.delete_dataset.assert_awaited_once_with(_TENANT_ID, _DATASET_ID)
    mock_delete.assert_awaited_once_with(settings, storage_path, expected_org=str(_TENANT_ID))


async def test_erase_dataset_raises_not_found_for_unknown_dataset(tmp_path: object) -> None:
    repo = _mock_repo(dataset=None)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _settings(tmp_path)

    with pytest.raises(NotFoundError):
        await svc.erase_dataset(TENANT, settings, uuid4())


async def test_erase_dataset_deletes_multiple_files(tmp_path: object) -> None:
    """All storage paths from all files must be deleted."""
    paths = [f"org/{_TENANT_ID}/file-{i}.csv" for i in range(3)]
    dataset = _make_dataset()
    files = [_make_file(p) for p in paths]
    repo = _mock_repo(dataset=dataset, files=files)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _settings(tmp_path)

    with patch(
        "augura_api.modules.datasets.service.delete_bytes", new_callable=AsyncMock
    ) as mock_delete:
        await svc.erase_dataset(TENANT, settings, _DATASET_ID)

    assert mock_delete.await_count == 3
    called_paths = [c.args[1] for c in mock_delete.await_args_list]
    assert set(called_paths) == set(paths)


async def test_erase_dataset_db_deleted_before_storage(tmp_path: object) -> None:
    """DB delete must be called before delete_bytes — ensures we never lose the
    path reference if delete_bytes raises."""
    call_order: list[str] = []
    storage_path = f"org/{_TENANT_ID}/file.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    repo = _mock_repo(dataset=dataset, files=[file_])

    async def _track_db_delete(*_: object, **__: object) -> None:
        call_order.append("db_delete")

    repo.delete_dataset = AsyncMock(side_effect=_track_db_delete)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _settings(tmp_path)

    async def _track_storage_delete(*_: object, **__: object) -> None:
        call_order.append("storage_delete")

    with patch(
        "augura_api.modules.datasets.service.delete_bytes",
        new_callable=AsyncMock,
        side_effect=_track_storage_delete,
    ):
        await svc.erase_dataset(TENANT, settings, _DATASET_ID)

    assert call_order == ["db_delete", "storage_delete"]


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
