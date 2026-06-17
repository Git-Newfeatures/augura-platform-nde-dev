"""Logique du module datasets : CRUD, colonnes (profiling), lecture cohortes."""

from uuid import UUID

from augura_api.core.errors import NotFoundError
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules import analytics
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.models import Dataset
from augura_api.modules.datasets.repo import DatasetRepo


class DatasetService:
    def __init__(self, repo: DatasetRepo) -> None:
        self.repo = repo

    async def _require_dataset(self, tenant: CurrentTenant, dataset_id: UUID) -> Dataset:
        dataset = await self.repo.get_dataset(tenant.tenant_id, dataset_id)
        if dataset is None:
            raise NotFoundError("dataset introuvable", dataset_id=str(dataset_id))
        return dataset

    @staticmethod
    def _to_out(dataset: Dataset, column_count: int) -> schemas.DatasetOut:
        return schemas.DatasetOut.model_validate(dataset).model_copy(
            update={"column_count": column_count}
        )

    async def list_datasets(self, tenant: CurrentTenant) -> list[schemas.DatasetOut]:
        rows = await self.repo.list_datasets(tenant.tenant_id)
        return [self._to_out(dataset, count) for dataset, count in rows]

    async def create_dataset(
        self, tenant: CurrentTenant, data: schemas.DatasetCreate
    ) -> schemas.DatasetOut:
        dataset = await self.repo.create_dataset(
            tenant.tenant_id,
            name=data.name,
            study_id=data.study_id,
            storage_path=data.storage_path,
            row_count=data.row_count,
        )
        return self._to_out(dataset, 0)

    async def get_dataset(self, tenant: CurrentTenant, dataset_id: UUID) -> schemas.DatasetOut:
        dataset = await self._require_dataset(tenant, dataset_id)
        return self._to_out(dataset, await self.repo.count_columns(dataset_id))

    async def list_columns(
        self, tenant: CurrentTenant, dataset_id: UUID
    ) -> list[schemas.ColumnOut]:
        await self._require_dataset(tenant, dataset_id)
        rows = await self.repo.list_columns(dataset_id)
        return [schemas.ColumnOut.model_validate(r) for r in rows]

    async def replace_columns(
        self, tenant: CurrentTenant, dataset_id: UUID, payload: schemas.ColumnsPut
    ) -> list[schemas.ColumnOut]:
        await self._require_dataset(tenant, dataset_id)
        rows = await self.repo.replace_columns(dataset_id, payload.columns)
        return [schemas.ColumnOut.model_validate(r) for r in rows]

    async def list_cohorts(self, tenant: CurrentTenant) -> list[schemas.CohortSummary]:
        return [
            schemas.CohortSummary(cohort_name=name, n_members=n)
            for name, n in await self.repo.list_cohorts(tenant.tenant_id)
        ]

    async def cohort_members(
        self, tenant: CurrentTenant, cohort_name: str
    ) -> list[schemas.CohortMemberOut]:
        rows = await self.repo.cohort_members(tenant.tenant_id, cohort_name)
        return [schemas.CohortMemberOut.model_validate(r) for r in rows]

    async def cohort_biomarkers(
        self, tenant: CurrentTenant, cohort_name: str
    ) -> list[schemas.CohortBiomarkerOut]:
        rows = await self.repo.cohort_biomarkers(tenant.tenant_id, cohort_name)
        return [schemas.CohortBiomarkerOut.model_validate(r) for r in rows]

    async def import_cohort(
        self, tenant: CurrentTenant, payload: schemas.CohortImportRequest
    ) -> schemas.CohortImportResult:
        n_members, n_biomarkers = await self.repo.import_cohort(
            tenant.tenant_id,
            cohort_name=payload.cohort_name,
            dataset_id=payload.dataset_id,
            members=payload.members,
            biomarkers=payload.biomarkers,
        )
        await analytics.log_usage(
            self.repo.session,
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            event_type="cohort.imported",
            route="/datasets/cohorts/import",
            metadata={
                "cohort_name": payload.cohort_name,
                "members": n_members,
                "biomarkers": n_biomarkers,
            },
        )
        return schemas.CohortImportResult(
            cohort_name=payload.cohort_name, members=n_members, biomarkers=n_biomarkers
        )
