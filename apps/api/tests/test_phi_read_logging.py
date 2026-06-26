"""Unit tests for Task 4: PHI read-access logging.

Verifies that the PHI-bearing read endpoints emit usage_events rows via
analytics.log_usage with the correct event_type, tenant_id, and user_id.

Covered read paths:
  - cohort_members → event_type='cohort.read'
  - cohort_biomarkers → event_type='cohort.biomarkers.read'
  - get_dataset → event_type='dataset.read'
  - list_files → event_type='dataset.files.read'

The log_usage call is mocked (no DB required). The tests prove:
  1. The call is awaited exactly once per PHI read.
  2. The event_type, tenant_id, and user_id are correct.
  3. No PHI values (member IDs, biomarker values) appear in the logged metadata.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets.service import DatasetService

_NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
_TENANT_ID = TenantId(uuid4())
_USER_ID = UserId(uuid4())
_DATASET_ID = uuid4()

TENANT = CurrentTenant(tenant_id=_TENANT_ID, user_id=_USER_ID, role="member")


def _make_dataset() -> SimpleNamespace:
    return SimpleNamespace(
        id=_DATASET_ID,
        org_id=_TENANT_ID,
        name="ds",
        status="uploaded",
        study_id=None,
        storage_path=None,
        row_count=10,
        created_at=_NOW,
        retention_until=None,
    )


def _make_member() -> SimpleNamespace:
    return SimpleNamespace(
        member_id="M001",
        age=42.0,
        sex="M",
        bmi=None,
        engagement_group=None,
        country="US",
    )


def _make_biomarker() -> SimpleNamespace:
    return SimpleNamespace(
        member_id="M001",
        timepoint_months=6,
        hba1c_pct=6.2,
        ldl_mgdl=None,
        hs_crp_mgl=None,
        adherence_pct=None,
    )


def _make_file() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        dataset_id=_DATASET_ID,
        filename="data.csv",
        storage_path=f"org/{_TENANT_ID}/f.csv",
        row_count=10,
        headers=["id", "age"],
        position=0,
        created_at=_NOW,
    )


def _mock_repo(**overrides: object) -> MagicMock:
    repo = MagicMock()
    repo.session = AsyncMock()
    repo.get_dataset = AsyncMock(return_value=overrides.get("dataset", _make_dataset()))
    repo.cohort_members = AsyncMock(return_value=overrides.get("members", []))
    repo.cohort_biomarkers = AsyncMock(return_value=overrides.get("biomarkers", []))
    repo.list_files = AsyncMock(return_value=overrides.get("files", []))
    repo.count_columns = AsyncMock(return_value=0)
    repo.count_files = AsyncMock(return_value=0)
    return repo


# ── cohort_members ────────────────────────────────────────────────────────────


async def test_cohort_members_read_emits_cohort_read_event() -> None:
    """cohort_members must emit a 'cohort.read' usage event."""
    members = [_make_member()]
    repo = _mock_repo(members=members)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        await svc.cohort_members(TENANT, "trial-A")

    mock_analytics.log_usage.assert_awaited_once()
    kw = mock_analytics.log_usage.call_args.kwargs
    assert kw["event_type"] == "cohort.read"
    assert kw["tenant_id"] == _TENANT_ID
    assert kw["user_id"] == _USER_ID


async def test_cohort_members_log_metadata_contains_no_phi() -> None:
    """Metadata logged for cohort.read must not contain raw member identifiers."""
    members = [_make_member()]
    repo = _mock_repo(members=members)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        await svc.cohort_members(TENANT, "trial-A")

    kw = mock_analytics.log_usage.call_args.kwargs
    meta = kw.get("metadata", {})
    # member_id ("M001") must not appear in metadata values
    assert "M001" not in str(meta)
    # count is fine
    assert meta.get("member_count") == 1


# ── cohort_biomarkers ─────────────────────────────────────────────────────────


async def test_cohort_biomarkers_read_emits_event() -> None:
    """cohort_biomarkers must emit a 'cohort.biomarkers.read' usage event."""
    biomarkers = [_make_biomarker()]
    repo = _mock_repo(biomarkers=biomarkers)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        await svc.cohort_biomarkers(TENANT, "trial-A")

    mock_analytics.log_usage.assert_awaited_once()
    kw = mock_analytics.log_usage.call_args.kwargs
    assert kw["event_type"] == "cohort.biomarkers.read"
    assert kw["tenant_id"] == _TENANT_ID
    assert kw["user_id"] == _USER_ID


async def test_cohort_biomarkers_log_metadata_contains_no_phi() -> None:
    """Metadata logged for cohort.biomarkers.read must not include raw biomarker values."""
    biomarkers = [_make_biomarker()]
    repo = _mock_repo(biomarkers=biomarkers)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        await svc.cohort_biomarkers(TENANT, "trial-A")

    kw = mock_analytics.log_usage.call_args.kwargs
    meta = kw.get("metadata", {})
    assert "M001" not in str(meta)
    assert meta.get("record_count") == 1


# ── get_dataset ───────────────────────────────────────────────────────────────


async def test_get_dataset_read_emits_dataset_read_event() -> None:
    """get_dataset must emit a 'dataset.read' usage event."""
    repo = _mock_repo(dataset=_make_dataset())
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        await svc.get_dataset(TENANT, _DATASET_ID)

    mock_analytics.log_usage.assert_awaited_once()
    kw = mock_analytics.log_usage.call_args.kwargs
    assert kw["event_type"] == "dataset.read"
    assert kw["tenant_id"] == _TENANT_ID
    assert kw["user_id"] == _USER_ID
    assert kw["metadata"] == {"dataset_id": str(_DATASET_ID)}


# ── list_files ────────────────────────────────────────────────────────────────


async def test_list_files_read_emits_dataset_files_read_event() -> None:
    """list_files must emit a 'dataset.files.read' usage event."""
    files = [_make_file()]
    repo = _mock_repo(dataset=_make_dataset(), files=files)
    svc = DatasetService(repo)  # pyright: ignore[reportArgumentType]

    with patch("augura_api.modules.datasets.service.analytics") as mock_analytics:
        mock_analytics.log_usage = AsyncMock()
        await svc.list_files(TENANT, _DATASET_ID)

    mock_analytics.log_usage.assert_awaited_once()
    kw = mock_analytics.log_usage.call_args.kwargs
    assert kw["event_type"] == "dataset.files.read"
    assert kw["tenant_id"] == _TENANT_ID
    assert kw["user_id"] == _USER_ID
    meta = kw.get("metadata", {})
    assert meta.get("dataset_id") == str(_DATASET_ID)
    assert meta.get("file_count") == 1
