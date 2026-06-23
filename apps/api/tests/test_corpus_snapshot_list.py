"""LiteratureSnapshotService.list_snapshots: maps rows to SnapshotSummary."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.corpus.live_repo import LiveRepo
from augura_api.modules.corpus.models import LiteratureSnapshot
from augura_api.modules.corpus.snapshot_service import LiteratureSnapshotService

TENANT = CurrentTenant(
    tenant_id=TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44")),
    user_id=UserId(UUID("11111111-1111-4111-8111-111111111111")),
    role="member",
)


def _row(query: str, n: int) -> LiteratureSnapshot:
    row = LiteratureSnapshot()
    row.id = uuid4()
    row.org_id = TENANT.tenant_id
    row.study_id = None
    row.created_by = TENANT.user_id
    row.created_at = datetime(2026, 6, 19, tzinfo=UTC)
    row.content_hash = "abc"
    row.payload = {
        "query": query,
        "sources": ["pubmed"],
        "results": [{"id": str(i)} for i in range(n)],
    }
    return row


class FakeLiveRepo:
    def __init__(self, rows: list[LiteratureSnapshot]) -> None:
        self.rows = rows
        self.calls: list[object] = []

    async def list_snapshots(self, tenant_id: TenantId, *, study_id: object = None):
        self.calls.append((tenant_id, study_id))
        return self.rows


async def test_list_snapshots_maps_to_summaries() -> None:
    repo = FakeLiveRepo([_row("glp-1 in heart failure", 3), _row("hba1c", 0)])
    service = LiteratureSnapshotService(cast(LiveRepo, repo))
    out = await service.list_snapshots(TENANT)

    assert [s.query for s in out] == ["glp-1 in heart failure", "hba1c"]
    assert out[0].result_count == 3
    assert out[1].result_count == 0
    assert out[0].sources == ["pubmed"]
    assert repo.calls == [(TENANT.tenant_id, None)]
