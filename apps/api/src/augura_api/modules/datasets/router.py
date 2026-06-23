"""HTTP adapter of the datasets module.

The `/datasets/cohorts...` routes are declared BEFORE `/datasets/{dataset_id}`
so they are not captured as an identifier.
"""

from uuid import UUID

from fastapi import APIRouter, Form, UploadFile, status

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.datasets.service import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _service(session: SessionDep) -> DatasetService:
    return DatasetService(DatasetRepo(session))


@router.get("", response_model=list[schemas.DatasetOut])
async def list_datasets(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.DatasetOut]:
    return await _service(session).list_datasets(tenant)


@router.post("", response_model=schemas.DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    data: schemas.DatasetCreate, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.DatasetOut:
    return await _service(session).create_dataset(tenant, data)


@router.get("/cohorts", response_model=list[schemas.CohortSummary])
async def list_cohorts(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CohortSummary]:
    return await _service(session).list_cohorts(tenant)


@router.post(
    "/cohorts/import",
    response_model=schemas.CohortImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_cohort(
    payload: schemas.CohortImportRequest, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.CohortImportResult:
    """Ingests a longitudinal cohort (members + biomarkers) — the write path
    for the cohort_* tables, read by OutcomeSelection/SimulationEngine."""
    return await _service(session).import_cohort(tenant, payload)


@router.get("/cohorts/{cohort_name}/members", response_model=list[schemas.CohortMemberOut])
async def cohort_members(
    cohort_name: str, tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CohortMemberOut]:
    return await _service(session).cohort_members(tenant, cohort_name)


@router.get("/cohorts/{cohort_name}/biomarkers", response_model=list[schemas.CohortBiomarkerOut])
async def cohort_biomarkers(
    cohort_name: str, tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CohortBiomarkerOut]:
    return await _service(session).cohort_biomarkers(tenant, cohort_name)


@router.post("/upload", response_model=schemas.UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    file: UploadFile,
    name: str | None = Form(default=None),  # noqa: B008
    study_id: UUID | None = Form(default=None),  # noqa: B008
) -> schemas.UploadResult:
    data = await file.read()
    return await _service(session).upload_dataset(
        tenant,
        settings,
        filename=file.filename or "upload.csv",
        data=data,
        name=name,
        study_id=study_id,
    )


@router.get("/{dataset_id}", response_model=schemas.DatasetOut)
async def get_dataset(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.DatasetOut:
    return await _service(session).get_dataset(tenant, dataset_id)


@router.get("/{dataset_id}/columns", response_model=list[schemas.ColumnOut])
async def list_columns(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.ColumnOut]:
    return await _service(session).list_columns(tenant, dataset_id)


@router.put("/{dataset_id}/columns", response_model=list[schemas.ColumnOut])
async def replace_columns(
    dataset_id: UUID,
    payload: schemas.ColumnsPut,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> list[schemas.ColumnOut]:
    return await _service(session).replace_columns(tenant, dataset_id, payload)
