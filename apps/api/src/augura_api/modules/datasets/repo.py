"""Accès base du module datasets — chaque méthode exige un TenantId."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.models import (
    CohortBiomarker,
    CohortMember,
    Dataset,
    DatasetColumn,
)


class DatasetRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_datasets(self, tenant_id: TenantId) -> list[Dataset]:
        res = await self.session.execute(
            select(Dataset).where(Dataset.org_id == tenant_id).order_by(Dataset.created_at.desc())
        )
        return list(res.scalars().all())

    async def get_dataset(self, tenant_id: TenantId, dataset_id: UUID) -> Dataset | None:
        res = await self.session.execute(
            select(Dataset).where(Dataset.org_id == tenant_id, Dataset.id == dataset_id)
        )
        return res.scalar_one_or_none()

    async def create_dataset(
        self,
        tenant_id: TenantId,
        *,
        name: str,
        study_id: UUID | None,
        storage_path: str | None,
        row_count: int | None,
    ) -> Dataset:
        dataset = Dataset(
            org_id=tenant_id,
            name=name,
            study_id=study_id,
            storage_path=storage_path,
            row_count=row_count,
        )
        self.session.add(dataset)
        await self.session.flush()
        await self.session.refresh(dataset)
        return dataset

    async def list_columns(self, dataset_id: UUID) -> list[DatasetColumn]:
        res = await self.session.execute(
            select(DatasetColumn)
            .where(DatasetColumn.dataset_id == dataset_id)
            .order_by(DatasetColumn.sheet, DatasetColumn.name)
        )
        return list(res.scalars().all())

    async def replace_columns(
        self, dataset_id: UUID, columns: list[schemas.ColumnIn]
    ) -> list[DatasetColumn]:
        await self.session.execute(
            delete(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id)
        )
        rows = [
            DatasetColumn(
                dataset_id=dataset_id,
                sheet=c.sheet,
                name=c.name,
                value_kind=c.value_kind,
                n_total=c.n_total,
                n_non_null=c.n_non_null,
                null_pct=c.null_pct,
                n_distinct=c.n_distinct,
                value_min=c.min,
                value_max=c.max,
                top_values=c.top_values,
                proposed_role=c.proposed_role,
                proposed_group=c.proposed_group,
                proposed_canonical_id=c.proposed_canonical_id,
                confidence=c.confidence,
                rationale=c.rationale,
                user_decision=c.user_decision,
                final_role=c.final_role,
                final_canonical_id=c.final_canonical_id,
            )
            for c in columns
        ]
        self.session.add_all(rows)
        await self.session.flush()
        return await self.list_columns(dataset_id)

    async def list_cohorts(self, tenant_id: TenantId) -> list[tuple[str, int]]:
        res = await self.session.execute(
            select(CohortMember.cohort_name, func.count())
            .where(CohortMember.org_id == tenant_id)
            .group_by(CohortMember.cohort_name)
            .order_by(CohortMember.cohort_name)
        )
        return [(str(name), int(n)) for name, n in res.all()]

    async def cohort_members(self, tenant_id: TenantId, cohort_name: str) -> list[CohortMember]:
        res = await self.session.execute(
            select(CohortMember)
            .where(CohortMember.org_id == tenant_id, CohortMember.cohort_name == cohort_name)
            .order_by(CohortMember.member_id)
        )
        return list(res.scalars().all())

    async def cohort_biomarkers(
        self, tenant_id: TenantId, cohort_name: str
    ) -> list[CohortBiomarker]:
        res = await self.session.execute(
            select(CohortBiomarker)
            .where(
                CohortBiomarker.org_id == tenant_id,
                CohortBiomarker.cohort_name == cohort_name,
            )
            .order_by(CohortBiomarker.member_id, CohortBiomarker.timepoint_months)
        )
        return list(res.scalars().all())
