"""Adaptateur HTTP du module jobs — suivi par polling (spec §8)."""

from uuid import UUID

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.core.errors import NotFoundError
from augura_api.modules.jobs import schemas
from augura_api.modules.jobs.service import get_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=schemas.JobOut)
async def get_job_status(
    job_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.JobOut:
    job = await get_job(session, tenant.tenant_id, job_id)
    if job is None:
        raise NotFoundError("job introuvable", job_id=str(job_id))
    return schemas.JobOut.model_validate(job)
