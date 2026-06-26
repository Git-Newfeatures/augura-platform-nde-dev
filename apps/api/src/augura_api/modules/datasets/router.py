"""HTTP adapter of the datasets module.

The `/datasets/cohorts...` routes are declared BEFORE `/datasets/{dataset_id}`
so they are not captured as an identifier.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile, status

from augura_api.core.deps import (
    CurrentTenantDep,
    SessionDep,
    SettingsDep,
    WriteTenantDep,
    require_role,
)
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.datasets.service import DatasetService, purge_objects

# Owner-only dependency (GDPR Art 17 erasure must be owner-gated).
OwnerTenantDep = Annotated[CurrentTenant, Depends(require_role("owner"))]

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _service(session: SessionDep) -> DatasetService:
    return DatasetService(DatasetRepo(session))


@router.get("", response_model=list[schemas.DatasetOut])
async def list_datasets(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.DatasetOut]:
    return await _service(session).list_datasets(tenant)


@router.post("", response_model=schemas.DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    data: schemas.DatasetCreate, tenant: WriteTenantDep, session: SessionDep
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
    payload: schemas.CohortImportRequest, tenant: WriteTenantDep, session: SessionDep
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
    tenant: WriteTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    files: list[UploadFile],
    name: str | None = Form(default=None),  # noqa: B008
    study_id: UUID | None = Form(default=None),  # noqa: B008
) -> schemas.UploadResult:
    payload = [((f.filename or "upload.csv"), await f.read()) for f in files]
    return await _service(session).upload_dataset(
        tenant, settings, files=payload, name=name, study_id=study_id
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
    tenant: WriteTenantDep,
    session: SessionDep,
) -> list[schemas.ColumnOut]:
    return await _service(session).replace_columns(tenant, dataset_id, payload)


@router.get("/{dataset_id}/files", response_model=list[schemas.DatasetFileOut])
async def list_files(
    dataset_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.DatasetFileOut]:
    return await _service(session).list_files(tenant, dataset_id)


@router.post(
    "/{dataset_id}/files",
    response_model=schemas.UploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def add_files(
    dataset_id: UUID,
    tenant: WriteTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    files: list[UploadFile],
) -> schemas.UploadResult:
    payload = [((f.filename or "upload.csv"), await f.read()) for f in files]
    return await _service(session).add_files(tenant, settings, dataset_id, payload)


@router.delete("/{dataset_id}/files/{file_id}", response_model=schemas.UploadResult)
async def remove_file(
    dataset_id: UUID,
    file_id: UUID,
    tenant: WriteTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> schemas.UploadResult:
    result, storage_path = await _service(session).remove_file(
        tenant, settings, dataset_id, file_id
    )
    background_tasks.add_task(purge_objects, settings, str(tenant.tenant_id), [storage_path])
    return result


@router.post("/{dataset_id}/data-dictionary", response_model=schemas.DataDictionaryResult)
async def parse_data_dictionary(
    dataset_id: UUID,
    tenant: WriteTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    file: UploadFile,
) -> schemas.DataDictionaryResult:
    """Parse an uploaded data dictionary into a structured data model. A dictionary-shaped
    CSV/XLSX is parsed deterministically; free-form input (.txt/.md or loose tables) is
    structured by the LLM (requires an Anthropic key, else 503)."""
    data = await file.read()
    return await _service(session).parse_data_dictionary(
        tenant, settings, dataset_id, filename=file.filename or "dictionary.csv", data=data
    )


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def erase_dataset(
    dataset_id: UUID,
    tenant: OwnerTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> None:
    """GDPR Art 17 — permanently erase a dataset and all its backing storage objects.
    Owner-only. DB rows are deleted in this request (committed on response); backing
    storage objects are purged post-commit in a BackgroundTask so the DB is durable
    before any irreversible byte removal."""
    paths = await _service(session).erase_dataset(tenant, dataset_id)
    background_tasks.add_task(purge_objects, settings, str(tenant.tenant_id), paths)


@router.get("/{dataset_id}/export", response_model=schemas.DatasetExport)
async def export_dataset(
    dataset_id: UUID,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> schemas.DatasetExport:
    """GDPR Art 15/20 — access and portability export. Returns a JSON bundle of
    the dataset metadata, profiled columns, and file metadata (no raw bytes).
    Emits a usage_events row for the audit trail."""
    return await _service(session).export_dataset(tenant, dataset_id)
