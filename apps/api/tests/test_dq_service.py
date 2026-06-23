"""Unit tests for DqService.run error mapping (no DB).

The happy path (upload → run → scored bundle) is covered by the integration test
tests/integration/test_dq_run.py. Here we pin the cross-container failure mode: when the
dataset bytes cannot be read back (e.g. a stale/ephemeral ref), the read raises
FileNotFoundError and the service must surface a clean 404 (NotFoundError), not a 500.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from augura_api.core.config import Settings
from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.dq import service as dq_service
from augura_api.modules.dq.service import DqService


class _FakeDatasetRepo:
    async def get_dataset(self, tenant_id: object, dataset_id: object) -> object:
        return SimpleNamespace(storage_path="org/x/f.csv", name="f.csv")

    async def list_files(self, dataset_id: object) -> list[object]:
        return [SimpleNamespace(filename="f.csv", storage_path="org/x/f.csv")]


def _tenant() -> CurrentTenant:
    return CurrentTenant(tenant_id=TenantId(uuid4()), user_id=UserId(uuid4()), role="owner")


async def test_run_maps_missing_bytes_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(settings: object, path: str) -> bytes:
        raise FileNotFoundError(path)

    monkeypatch.setattr(dq_service, "read_bytes", _boom)
    settings = Settings(env="dev")  # pyright: ignore[reportCallIssue]
    svc = DqService(SimpleNamespace(), _FakeDatasetRepo())  # pyright: ignore[reportArgumentType]

    with pytest.raises(NotFoundError):
        await svc.run(_tenant(), settings, uuid4())
