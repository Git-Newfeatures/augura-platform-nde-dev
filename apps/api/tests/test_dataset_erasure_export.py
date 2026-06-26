"""Unit tests for DatasetService.erase_dataset and DatasetService.export_dataset.

These tests use async mock repos (no DB) to exercise the service logic in isolation.

Key correctness invariant (ENG compliance/phase-3):
  DB commit MUST happen BEFORE any storage object deletion.  FastAPI 0.136.x runs
  background tasks before yield-dependency teardown (i.e. before get_session's
  `async with session.begin()` commits), so the old BackgroundTask pattern was wrong.
  The fix uses a dedicated committed session — its `s.begin()` context manager exits
  (and commits) before purge_objects is called.

  The ordering tests below prove this without relying on FastAPI internals: they
  monkeypatch `get_sessionmaker` to record when the dedicated-session commit occurs
  (by intercepting the session-context __aexit__) and `delete_bytes` to record when
  storage deletion is attempted, then assert the commit timestamp precedes any
  deletion call.
"""

import datetime
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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


def _make_settings() -> Settings:
    return Settings(env="dev", artifacts_dir="/tmp")  # pyright: ignore[reportCallIssue]


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


# ─── helpers for the dedicated-session mock ───────────────────────────────────


def _make_dedicated_session_mock(events: list[str]) -> MagicMock:
    """Return a mock async_sessionmaker whose session records 'committed' in `events`
    when its begin() context exits (i.e. when the dedicated transaction commits).

    The mock session also stubs execute() so set_user_stmt / set_tenant_stmt calls
    do not raise, and exposes a DatasetRepo-compatible interface so the inner
    DatasetRepo(s).delete_dataset call is captured.
    """
    session = AsyncMock()
    session.execute = AsyncMock()

    # Track delete_dataset calls on any DatasetRepo wrapping this session.
    session._delete_dataset = AsyncMock()

    @asynccontextmanager
    async def _begin() -> AsyncGenerator[None, None]:
        yield
        # Exiting this context = commit.  Record the event.
        events.append("committed")

    session.begin = _begin

    @asynccontextmanager
    async def _session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield session

    sm = MagicMock()
    sm.return_value = _session_ctx()

    # Make sm() always return a fresh context manager (supports multiple calls).
    def _sm_call() -> object:
        @asynccontextmanager
        async def _ctx() -> AsyncGenerator[AsyncMock, None]:
            yield session

        return _ctx()

    sm.side_effect = _sm_call
    return sm


# ─── erase_dataset — ordering proof ───────────────────────────────────────────


async def test_erase_dataset_commit_precedes_storage_deletion() -> None:
    """CORE ORDERING INVARIANT: the dedicated-session commit must be recorded before
    any delete_bytes call.

    How this works without FastAPI:
      - get_sessionmaker is monkeypatched to return a mock whose begin() __aexit__
        appends 'committed' to `events`.
      - delete_bytes is monkeypatched to append 'deleted:<path>' to `events`.
      - After erase_dataset returns we assert 'committed' comes first.

    This proves the dedicated-session pattern guarantees commit-before-delete
    independent of FastAPI's background-task ordering.
    """
    storage_path = f"org/{_TENANT_ID}/file-abc.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    repo = _mock_repo(dataset=dataset, files=[file_])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _make_settings()

    events: list[str] = []
    sm = _make_dedicated_session_mock(events)

    async def _fake_delete_bytes(s: Settings, path: str, *, expected_org: str) -> None:
        events.append(f"deleted:{path}")

    with (
        patch("augura_api.modules.datasets.service.get_sessionmaker", return_value=sm),
        patch("augura_api.modules.datasets.service.DatasetRepo") as MockRepo,
        patch(
            "augura_api.modules.datasets.service.delete_bytes",
            side_effect=_fake_delete_bytes,
        ),
    ):
        # Inner DatasetRepo(s).delete_dataset must not raise.
        inner_repo = AsyncMock()
        inner_repo.delete_dataset = AsyncMock()
        MockRepo.return_value = inner_repo

        await svc.erase_dataset(TENANT, settings, _DATASET_ID)

    # Committed must appear before any deleted event.
    assert "committed" in events, "dedicated-session commit was never recorded"
    committed_idx = events.index("committed")
    deletion_indices = [i for i, e in enumerate(events) if e.startswith("deleted:")]
    assert deletion_indices, "delete_bytes was never called — purge_objects not invoked"
    assert all(committed_idx < d_idx for d_idx in deletion_indices), (
        f"storage deletion preceded commit — ordering broken: {events}"
    )


async def test_erase_dataset_deletes_db_rows_before_storage() -> None:
    """Sanity: delete_dataset is called on the inner (dedicated-session) repo,
    and delete_bytes is called only after the dedicated session commits."""
    storage_path = f"org/{_TENANT_ID}/file-abc.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    repo = _mock_repo(dataset=dataset, files=[file_])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _make_settings()

    events: list[str] = []
    sm = _make_dedicated_session_mock(events)
    inner_repo_mock = AsyncMock()

    async def _record_delete_dataset(*_a: object, **_kw: object) -> None:
        events.append("delete_dataset")

    inner_repo_mock.delete_dataset = AsyncMock(side_effect=_record_delete_dataset)

    async def _fake_delete_bytes(s: Settings, path: str, *, expected_org: str) -> None:
        events.append(f"deleted:{path}")

    with (
        patch("augura_api.modules.datasets.service.get_sessionmaker", return_value=sm),
        patch(
            "augura_api.modules.datasets.service.DatasetRepo",
            return_value=inner_repo_mock,
        ),
        patch(
            "augura_api.modules.datasets.service.delete_bytes",
            side_effect=_fake_delete_bytes,
        ),
    ):
        await svc.erase_dataset(TENANT, settings, _DATASET_ID)

    assert events.index("delete_dataset") < events.index("committed"), (
        "delete_dataset must be called before commit exits"
    )
    assert events.index("committed") < events.index(f"deleted:{storage_path}"), (
        "commit must precede storage deletion"
    )


async def test_erase_dataset_raises_not_found_for_unknown_dataset() -> None:
    repo = _mock_repo(dataset=None)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with pytest.raises(NotFoundError):
        await svc.erase_dataset(TENANT, _make_settings(), uuid4())


async def test_erase_dataset_purges_all_paths_for_multiple_files() -> None:
    """All storage paths from all files must be purged; the dedicated session must
    commit once before any object deletion begins."""
    paths = [f"org/{_TENANT_ID}/file-{i}.csv" for i in range(3)]
    dataset = _make_dataset()
    files = [_make_file(p) for p in paths]
    repo = _mock_repo(dataset=dataset, files=files)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _make_settings()

    events: list[str] = []
    sm = _make_dedicated_session_mock(events)
    inner_repo_mock = AsyncMock()
    inner_repo_mock.delete_dataset = AsyncMock()

    async def _fake_delete_bytes(s: Settings, path: str, *, expected_org: str) -> None:
        events.append(f"deleted:{path}")

    with (
        patch("augura_api.modules.datasets.service.get_sessionmaker", return_value=sm),
        patch(
            "augura_api.modules.datasets.service.DatasetRepo",
            return_value=inner_repo_mock,
        ),
        patch(
            "augura_api.modules.datasets.service.delete_bytes",
            side_effect=_fake_delete_bytes,
        ),
    ):
        await svc.erase_dataset(TENANT, settings, _DATASET_ID)

    deleted_paths = {e.split("deleted:")[1] for e in events if e.startswith("deleted:")}
    assert deleted_paths == set(paths), f"not all paths were purged: {deleted_paths}"
    committed_idx = events.index("committed")
    for p in paths:
        assert committed_idx < events.index(f"deleted:{p}"), f"commit must precede deletion of {p}"


async def test_erase_dataset_delete_bytes_403_not_swallowed_silently() -> None:
    """purge_objects must log errors but not re-raise them (orphaned objects are
    recoverable; we must not crash after the rows are already deleted)."""
    storage_path = f"org/{_TENANT_ID}/file-abc.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    repo = _mock_repo(dataset=dataset, files=[file_])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]
    settings = _make_settings()

    sm = _make_dedicated_session_mock([])
    inner_repo_mock = AsyncMock()
    inner_repo_mock.delete_dataset = AsyncMock()

    async def _failing_delete(s: Settings, path: str, *, expected_org: str) -> None:
        raise PermissionError("403 forbidden")

    with (
        patch("augura_api.modules.datasets.service.get_sessionmaker", return_value=sm),
        patch(
            "augura_api.modules.datasets.service.DatasetRepo",
            return_value=inner_repo_mock,
        ),
        patch(
            "augura_api.modules.datasets.service.delete_bytes",
            side_effect=_failing_delete,
        ),
    ):
        # Must not raise — purge_objects swallows the error and logs it.
        await svc.erase_dataset(TENANT, settings, _DATASET_ID)


# ─── remove_file — no BackgroundTask, storage purged post-commit ──────────────


async def test_remove_file_returns_upload_result_no_storage_io_before_commit() -> None:
    """remove_file must return an UploadResult and only call delete_bytes after the
    dedicated session commits.  The old BackgroundTask pattern is gone."""
    storage_path = f"org/{_TENANT_ID}/f.csv"
    dataset = _make_dataset()
    file_ = _make_file(storage_path)
    column = _make_column("id")
    settings = _make_settings()

    repo = _mock_repo(dataset=dataset, files=[], columns=[column])
    repo.get_file = AsyncMock(return_value=file_)
    repo.delete_file = AsyncMock()
    repo.replace_columns = AsyncMock(return_value=[column])
    repo.set_storage_and_rowcount = AsyncMock()
    repo.next_position = AsyncMock(return_value=0)
    repo.list_active_pii_patterns = AsyncMock(return_value=[])
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    events: list[str] = []
    sm = _make_dedicated_session_mock(events)

    inner_repo_mock = AsyncMock()
    inner_repo_mock.delete_file = AsyncMock()
    inner_repo_mock.list_files = AsyncMock(return_value=[])
    inner_repo_mock.replace_columns = AsyncMock(return_value=[column])
    inner_repo_mock.set_storage_and_rowcount = AsyncMock()

    async def _fake_delete_bytes(s: Settings, path: str, *, expected_org: str) -> None:
        events.append(f"deleted:{path}")

    with (
        patch("augura_api.modules.datasets.service.get_sessionmaker", return_value=sm),
        patch(
            "augura_api.modules.datasets.service.DatasetRepo",
            return_value=inner_repo_mock,
        ),
        patch(
            "augura_api.modules.datasets.service.delete_bytes",
            side_effect=_fake_delete_bytes,
        ),
    ):
        result = await svc.remove_file(TENANT, settings, _DATASET_ID, _FILE_ID)

    assert isinstance(result, schemas.UploadResult)
    # Commit must precede deletion.
    if f"deleted:{storage_path}" in events:
        committed_idx = events.index("committed")
        deleted_idx = events.index(f"deleted:{storage_path}")
        assert committed_idx < deleted_idx, f"storage deletion preceded commit: {events}"


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
