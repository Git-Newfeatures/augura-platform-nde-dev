"""Logique du module datasets : CRUD, colonnes (profiling), lecture cohortes."""

from uuid import UUID, uuid4

from augura_api.core.config import Settings
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
    def _to_out(dataset: Dataset, column_count: int, file_count: int = 0) -> schemas.DatasetOut:
        return schemas.DatasetOut.model_validate(dataset).model_copy(
            update={"column_count": column_count, "file_count": file_count}
        )

    async def list_datasets(self, tenant: CurrentTenant) -> list[schemas.DatasetOut]:
        rows = await self.repo.list_datasets(tenant.tenant_id)
        return [self._to_out(d, col, files) for d, col, files in rows]

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
        return self._to_out(
            dataset,
            await self.repo.count_columns(dataset_id),
            await self.repo.count_files(dataset_id),
        )

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

    async def _files_out(self, dataset_id: UUID) -> list[schemas.DatasetFileOut]:
        rows = await self.repo.list_files(dataset_id)
        return [
            schemas.DatasetFileOut(
                id=f.id,
                filename=f.filename,
                row_count=f.row_count,
                column_count=len(f.headers or []),
                position=f.position,
                created_at=f.created_at,
            )
            for f in rows
        ]

    async def list_files(
        self, tenant: CurrentTenant, dataset_id: UUID
    ) -> list[schemas.DatasetFileOut]:
        await self._require_dataset(tenant, dataset_id)
        return await self._files_out(dataset_id)

    async def _reprofile(self, settings: Settings, dataset_id: UUID) -> list[schemas.ColumnOut]:
        # Re-read every file, build the union of columns and concatenate rows, then
        # profile the union once. Called after any add/remove so dataset_columns and
        # datasets.row_count always reflect the full set of files.
        from augura_api.core.storage import read_bytes
        from augura_api.modules.datasets.combine import combine_sheets
        from augura_api.modules.datasets.parsing import Sheet, parse_upload
        from augura_api.modules.datasets.profiling import profile_column

        files = await self.repo.list_files(dataset_id)
        parsed: list[tuple[str, list[Sheet]]] = []
        for f in files:
            data = await read_bytes(settings, f.storage_path)
            parsed.append((f.filename, parse_upload(f.filename, data)))
        combined = combine_sheets(parsed)

        cols: list[schemas.ColumnIn] = []
        for sheet in combined:
            for idx, header in enumerate(sheet.headers):
                values = [row[idx] if idx < len(row) else "" for row in sheet.rows]
                p = profile_column(header, values)
                cols.append(
                    schemas.ColumnIn(
                        sheet=sheet.name,
                        name=header,
                        value_kind=p.value_kind,
                        n_total=p.n_total,
                        n_non_null=p.n_non_null,
                        null_pct=p.null_pct,
                        n_distinct=p.n_distinct,
                        min=p.value_min,
                        max=p.value_max,
                        top_values=p.top_values,
                    )
                )
        row_count = sum(len(s.rows) for s in combined) if files else None
        first_ref = files[0].storage_path if files else None
        await self.repo.set_storage_and_rowcount(
            dataset_id, storage_path=first_ref, row_count=row_count
        )
        column_rows = await self.repo.replace_columns(dataset_id, cols)
        return [schemas.ColumnOut.model_validate(c) for c in column_rows]

    async def upload_dataset(
        self,
        tenant: CurrentTenant,
        settings: Settings,
        *,
        files: list[tuple[str, bytes]],
        name: str | None,
        study_id: UUID | None,
    ) -> schemas.UploadResult:
        from augura_api.core.storage import save_bytes
        from augura_api.modules.datasets.combine import file_headers
        from augura_api.modules.datasets.parsing import parse_upload

        # Parse everything first so a bad file aborts before any write (raises 413/415/400).
        parsed = [(fn, parse_upload(fn, data), data) for fn, data in files]
        dataset = await self.repo.create_dataset(
            tenant.tenant_id,
            name=name or files[0][0],
            study_id=study_id,
            storage_path=None,
            row_count=None,
        )
        for pos, (fn, sheets, data) in enumerate(parsed):
            ref = await save_bytes(
                settings,
                org_id=str(tenant.tenant_id),
                name=f"{uuid4()}-{fn}",
                data=data,
            )
            await self.repo.add_file(
                dataset.id,
                filename=fn,
                storage_path=ref,
                row_count=sum(len(s.rows) for s in sheets),
                headers=file_headers(sheets),
                position=pos,
            )
        columns = await self._reprofile(settings, dataset.id)
        files_out = await self._files_out(dataset.id)
        refreshed = await self._require_dataset(tenant, dataset.id)
        return schemas.UploadResult(
            dataset=self._to_out(refreshed, len(columns), len(files_out)),
            columns=columns,
            files=files_out,
            warnings=[],
        )

    async def add_files(
        self,
        tenant: CurrentTenant,
        settings: Settings,
        dataset_id: UUID,
        files: list[tuple[str, bytes]],
    ) -> schemas.UploadResult:
        from augura_api.core.storage import save_bytes
        from augura_api.modules.datasets.combine import file_headers, file_warnings
        from augura_api.modules.datasets.parsing import parse_upload

        await self._require_dataset(tenant, dataset_id)
        established: list[str] = []
        for f in await self.repo.list_files(dataset_id):
            for h in f.headers or []:
                if h not in established:
                    established.append(h)

        parsed = [(fn, parse_upload(fn, data), data) for fn, data in files]
        warnings: list[str] = []
        pos = await self.repo.next_position(dataset_id)
        for fn, sheets, data in parsed:
            hdrs = file_headers(sheets)
            warnings.extend(file_warnings(established, hdrs, fn))
            for h in hdrs:
                if h not in established:
                    established.append(h)
            ref = await save_bytes(
                settings,
                org_id=str(tenant.tenant_id),
                name=f"{uuid4()}-{fn}",
                data=data,
            )
            await self.repo.add_file(
                dataset_id,
                filename=fn,
                storage_path=ref,
                row_count=sum(len(s.rows) for s in sheets),
                headers=hdrs,
                position=pos,
            )
            pos += 1
        columns = await self._reprofile(settings, dataset_id)
        files_out = await self._files_out(dataset_id)
        refreshed = await self._require_dataset(tenant, dataset_id)
        return schemas.UploadResult(
            dataset=self._to_out(refreshed, len(columns), len(files_out)),
            columns=columns,
            files=files_out,
            warnings=warnings,
        )

    async def remove_file(
        self, tenant: CurrentTenant, settings: Settings, dataset_id: UUID, file_id: UUID
    ) -> schemas.UploadResult:
        await self._require_dataset(tenant, dataset_id)
        target = await self.repo.get_file(dataset_id, file_id)
        if target is None:
            raise NotFoundError("file not found", file_id=str(file_id))
        await self.repo.delete_file(dataset_id, file_id)
        columns = await self._reprofile(settings, dataset_id)
        files_out = await self._files_out(dataset_id)
        refreshed = await self._require_dataset(tenant, dataset_id)
        return schemas.UploadResult(
            dataset=self._to_out(refreshed, len(columns), len(files_out)),
            columns=columns,
            files=files_out,
            warnings=[],
        )

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
