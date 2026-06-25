"""Database access for the datasets module — every method requires a TenantId."""

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.models import (
    CohortBiomarker,
    CohortMember,
    Dataset,
    DatasetColumn,
    DatasetFile,
)


class DatasetRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_datasets(self, tenant_id: TenantId) -> list[tuple[Dataset, int, int]]:
        """Datasets of the tenant + column count + file count (correlated subqueries
        on dataset_columns / dataset_files, intra-module)."""
        col_count = (
            select(func.count(DatasetColumn.id))
            .where(DatasetColumn.dataset_id == Dataset.id)
            .correlate(Dataset)
            .scalar_subquery()
        )
        file_count = (
            select(func.count(DatasetFile.id))
            .where(DatasetFile.dataset_id == Dataset.id)
            .correlate(Dataset)
            .scalar_subquery()
        )
        res = await self.session.execute(
            select(
                Dataset,
                col_count.label("column_count"),
                file_count.label("file_count"),
            )
            .where(Dataset.org_id == tenant_id)
            .order_by(Dataset.created_at.desc())
        )
        return [(row[0], int(row[1]), int(row[2])) for row in res.all()]

    async def get_dataset(self, tenant_id: TenantId, dataset_id: UUID) -> Dataset | None:
        res = await self.session.execute(
            select(Dataset).where(Dataset.org_id == tenant_id, Dataset.id == dataset_id)
        )
        return res.scalar_one_or_none()

    async def count_columns(self, dataset_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(DatasetColumn.id)).where(DatasetColumn.dataset_id == dataset_id)
        )
        return int(res.scalar_one())

    async def count_files(self, dataset_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(DatasetFile.id)).where(DatasetFile.dataset_id == dataset_id)
        )
        return int(res.scalar_one())

    async def list_files(self, dataset_id: UUID) -> list[DatasetFile]:
        res = await self.session.execute(
            select(DatasetFile)
            .where(DatasetFile.dataset_id == dataset_id)
            .order_by(DatasetFile.position, DatasetFile.created_at)
        )
        return list(res.scalars().all())

    async def get_file(self, dataset_id: UUID, file_id: UUID) -> DatasetFile | None:
        res = await self.session.execute(
            select(DatasetFile).where(
                DatasetFile.dataset_id == dataset_id, DatasetFile.id == file_id
            )
        )
        return res.scalar_one_or_none()

    async def next_position(self, dataset_id: UUID) -> int:
        res = await self.session.execute(
            select(func.coalesce(func.max(DatasetFile.position), -1) + 1).where(
                DatasetFile.dataset_id == dataset_id
            )
        )
        return int(res.scalar_one())

    async def add_file(
        self,
        dataset_id: UUID,
        *,
        filename: str,
        storage_path: str,
        row_count: int | None,
        headers: list[str],
        position: int,
    ) -> DatasetFile:
        row = DatasetFile(
            dataset_id=dataset_id,
            filename=filename,
            storage_path=storage_path,
            row_count=row_count,
            headers=headers,
            position=position,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def delete_file(self, dataset_id: UUID, file_id: UUID) -> None:
        await self.session.execute(
            delete(DatasetFile).where(
                DatasetFile.dataset_id == dataset_id, DatasetFile.id == file_id
            )
        )

    async def set_storage_and_rowcount(
        self, dataset_id: UUID, *, storage_path: str | None, row_count: int | None
    ) -> None:
        await self.session.execute(
            update(Dataset)
            .where(Dataset.id == dataset_id)
            .values(storage_path=storage_path, row_count=row_count)
        )

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

    async def list_active_pii_patterns(self) -> list[tuple[str, str]]:
        """(key, pattern) for active PII catalog rows. Global read-only catalog
        (RLS backend_read allows it under a tenant session)."""
        from sqlalchemy import text

        res = await self.session.execute(
            text(
                "select key, pattern from pii_pattern_catalog"
                " where active = true order by sort_order"
            )
        )
        return [(row.key, row.pattern) for row in res.all()]

    async def import_cohort(
        self,
        tenant_id: TenantId,
        *,
        cohort_name: str,
        dataset_id: UUID | None,
        members: list[schemas.CohortMemberIn],
        biomarkers: list[schemas.CohortBiomarkerIn],
    ) -> tuple[int, int]:
        """Replaces the cohort (members + biomarkers) for (tenant, cohort_name) — the
        write path for the cohort_* tables. Delete-then-insert for idempotence."""
        await self.session.execute(
            delete(CohortMember).where(
                CohortMember.org_id == tenant_id, CohortMember.cohort_name == cohort_name
            )
        )
        await self.session.execute(
            delete(CohortBiomarker).where(
                CohortBiomarker.org_id == tenant_id, CohortBiomarker.cohort_name == cohort_name
            )
        )
        for m in members:
            self.session.add(
                CohortMember(
                    org_id=tenant_id,
                    dataset_id=dataset_id,
                    cohort_name=cohort_name,
                    member_id=m.member_id,
                    age=m.age,
                    sex=m.sex,
                    bmi=m.bmi,
                    engagement_group=m.engagement_group,
                    country=m.country,
                )
            )
        for b in biomarkers:
            self.session.add(
                CohortBiomarker(
                    org_id=tenant_id,
                    dataset_id=dataset_id,
                    cohort_name=cohort_name,
                    member_id=b.member_id,
                    timepoint_months=b.timepoint_months,
                    hba1c_pct=b.hba1c_pct,
                    ldl_mgdl=b.ldl_mgdl,
                    hs_crp_mgl=b.hs_crp_mgl,
                    adherence_pct=b.adherence_pct,
                )
            )
        await self.session.flush()
        return len(members), len(biomarkers)
