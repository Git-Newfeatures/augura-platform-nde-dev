"""Adaptateur HTTP du module reference (porte unique FastAPI)."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.reference import schemas
from augura_api.modules.reference.repo import ReferenceRepo
from augura_api.modules.reference.service import ReferenceService

router = APIRouter(prefix="/reference", tags=["reference"])


def _service(session: SessionDep) -> ReferenceService:
    return ReferenceService(ReferenceRepo(session))


@router.get("/tenant", response_model=schemas.TenantProfileOut)
async def tenant(
    tenant: CurrentTenantDep, session: SessionDep
) -> schemas.TenantProfileOut:
    return await _service(session).tenant_profile(tenant)


@router.get("/cesl-sources", response_model=list[schemas.CeslSourceOut])
async def cesl_sources(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CeslSourceOut]:
    return await _service(session).cesl_sources()


@router.get("/study-designs", response_model=list[schemas.StudyDesignOut])
async def study_designs(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.StudyDesignOut]:
    return await _service(session).study_designs()
