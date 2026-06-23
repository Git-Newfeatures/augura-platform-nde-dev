"""HTTP adapter for the studies module (single gate: everything goes through FastAPI)."""

from uuid import UUID

from fastapi import APIRouter, status

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.core.ids import StudyId
from augura_api.modules.studies import schemas
from augura_api.modules.studies.repo import StudyRepo
from augura_api.modules.studies.service import StudyService

router = APIRouter(prefix="/studies", tags=["studies"])


def _service(session: SessionDep) -> StudyService:
    return StudyService(StudyRepo(session))


@router.get("", response_model=list[schemas.StudyOut])
async def list_studies(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.StudyOut]:
    return await _service(session).list_studies(tenant)


@router.post("", response_model=schemas.StudyOut, status_code=status.HTTP_201_CREATED)
async def create_study(
    data: schemas.StudyCreate, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.StudyOut:
    return await _service(session).create_study(tenant, data)


@router.get("/{study_id}", response_model=schemas.StudyOut)
async def get_study(
    study_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.StudyOut:
    return await _service(session).get_study(tenant, StudyId(study_id))


@router.patch("/{study_id}", response_model=schemas.StudyOut)
async def update_study(
    study_id: UUID,
    data: schemas.StudyUpdate,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.StudyOut:
    return await _service(session).update_study(tenant, StudyId(study_id), data)


@router.get("/{study_id}/state", response_model=schemas.StudyStateOut)
async def get_state(
    study_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.StudyStateOut:
    return await _service(session).get_state(tenant, StudyId(study_id))


@router.put("/{study_id}/state", response_model=schemas.StudyStateOut)
async def put_state(
    study_id: UUID,
    payload: schemas.StudyStatePut,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.StudyStateOut:
    return await _service(session).save_state(tenant, StudyId(study_id), payload)
