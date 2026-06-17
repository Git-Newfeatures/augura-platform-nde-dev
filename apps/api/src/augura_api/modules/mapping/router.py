"""Adaptateur HTTP du module mapping."""

from uuid import UUID

from fastapi import APIRouter, status

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.mapping import schemas
from augura_api.modules.mapping.repo import MappingRepo
from augura_api.modules.mapping.service import MappingService
from augura_api.modules.semantic.repo import SemanticRepo

router = APIRouter(prefix="/datasets", tags=["mapping"])


@router.post(
    "/{dataset_id}/map",
    response_model=schemas.MapResult,
    status_code=status.HTTP_201_CREATED,
)
async def map_dataset(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.MapResult:
    service = MappingService(MappingRepo(session), DatasetRepo(session), SemanticRepo(session))
    return await service.map_dataset(tenant, dataset_id)
