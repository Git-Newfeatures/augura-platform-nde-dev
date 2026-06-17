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
async def tenant(tenant: CurrentTenantDep, session: SessionDep) -> schemas.TenantProfileOut:
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


@router.get("/outcomes", response_model=list[schemas.OutcomeOut])
async def outcomes(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.OutcomeOut]:
    return await _service(session).outcomes()


@router.get("/estimands", response_model=list[schemas.EstimandOut])
async def estimands(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.EstimandOut]:
    return await _service(session).estimands()


@router.get("/estimators", response_model=list[schemas.EstimatorOut])
async def estimators(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.EstimatorOut]:
    return await _service(session).estimators()


@router.get("/frameworks", response_model=list[schemas.FrameworkOut])
async def frameworks(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.FrameworkOut]:
    return await _service(session).frameworks()


@router.get("/evidence-types", response_model=list[schemas.CodeLabelOut])
async def evidence_types(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CodeLabelOut]:
    return await _service(session).evidence_types()


@router.get("/domains", response_model=list[schemas.CodeLabelOut])
async def domains(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.CodeLabelOut]:
    return await _service(session).domains()


@router.get("/jurisdictions", response_model=list[schemas.CodeLabelOut])
async def jurisdictions(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CodeLabelOut]:
    return await _service(session).jurisdictions()


@router.get("/literature-study-designs", response_model=list[schemas.CodeLabelOut])
async def literature_study_designs(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CodeLabelOut]:
    return await _service(session).literature_designs()


@router.get("/dq-rules", response_model=schemas.DqRulesOut)
async def dq_rules(tenant: CurrentTenantDep, session: SessionDep) -> schemas.DqRulesOut:
    return await _service(session).dq_rules()


@router.get("/variable-roles", response_model=schemas.VariableRolesOut)
async def variable_roles(tenant: CurrentTenantDep, session: SessionDep) -> schemas.VariableRolesOut:
    return await _service(session).variable_roles()
