"""HTTP adapter for the dq module."""

from uuid import UUID

from fastapi import APIRouter, status

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep, WriteTenantDep
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.dq import schemas
from augura_api.modules.dq.repo import DqRepo
from augura_api.modules.dq.service import DqService

router = APIRouter(prefix="/datasets", tags=["dq"])


def _service(session: SessionDep) -> DqService:
    return DqService(DqRepo(session), DatasetRepo(session))


@router.post(
    "/{dataset_id}/dq", response_model=schemas.DqRunResult, status_code=status.HTTP_201_CREATED
)
async def run_dq(
    dataset_id: UUID, tenant: WriteTenantDep, session: SessionDep, settings: SettingsDep
) -> schemas.DqRunResult:
    return await _service(session).run(tenant, settings, dataset_id)


@router.get("/{dataset_id}/dq", response_model=schemas.DqBundleOut)
async def latest_dq(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.DqBundleOut:
    return await _service(session).latest(tenant, dataset_id)
