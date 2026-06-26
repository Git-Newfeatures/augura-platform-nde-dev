"""Datasets module logic: CRUD, columns (profiling), cohort reads."""

from uuid import UUID, uuid4

import structlog

from augura_api.core.config import Settings
from augura_api.core.db import get_sessionmaker, set_tenant_stmt, set_user_stmt
from augura_api.core.errors import BadRequestError, NotFoundError
from augura_api.core.storage import delete_bytes
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules import analytics
from augura_api.modules.datasets import schemas
from augura_api.modules.datasets.models import Dataset
from augura_api.modules.datasets.parsing import Sheet
from augura_api.modules.datasets.repo import DatasetRepo

_log = structlog.get_logger(__name__)


async def purge_objects(settings: Settings, org_id: str, paths: list[str]) -> None:
    """Best-effort post-commit storage deletion.

    Must be called AFTER the dedicated committed session has returned (i.e. after
    DB rows are durably committed).  Per-path failures are logged and skipped —
    orphaned objects are recoverable via a storage audit; orphaned DB rows are not.

    NOTE: this is NOT called from a FastAPI BackgroundTask.  FastAPI 0.136.x runs
    background tasks BEFORE yield-dependency teardown (i.e. before
    get_session's `async with session.begin()` commits), so the old pattern was
    incorrect: storage deletion could run before the DB commit.  The correct
    pattern is: commit deterministically in a dedicated session, then call this
    function synchronously in the same coroutine after that commit returns.
    """
    for path in paths:
        try:
            await delete_bytes(settings, path, expected_org=org_id)
        except Exception as exc:
            _log.error(
                "purge_objects: failed to delete storage object (orphaned object, not a row)",
                storage_path=path,
                org_id=org_id,
                error=str(exc),
            )


class DatasetService:
    def __init__(self, repo: DatasetRepo) -> None:
        self.repo = repo

    async def _require_dataset(self, tenant: CurrentTenant, dataset_id: UUID) -> Dataset:
        dataset = await self.repo.get_dataset(tenant.tenant_id, dataset_id)
        if dataset is None:
            raise NotFoundError("dataset not found", dataset_id=str(dataset_id))
        return dataset

    async def _reject_pii_headers(self, parsed: list[tuple[str, list[Sheet]]]) -> None:
        """Fail closed if any uploaded column header matches an active PII pattern
        (direct identifiers must not be persisted). 400 with the flagged columns."""
        from augura_api.modules.datasets.pii import PiiPattern, scan_headers_for_pii

        rows = await self.repo.list_active_pii_patterns()
        patterns = [PiiPattern(key=k, pattern=p) for k, p in rows]
        headers: list[str] = [h for _fn, sheets in parsed for s in sheets for h in s.headers]
        hits = scan_headers_for_pii(headers, patterns)
        if hits:
            flagged = sorted({h.column for h in hits})
            raise BadRequestError(
                "upload rejected: column headers look like direct identifiers (remove or "
                "pseudonymize them before upload)",
                columns=flagged,
            )

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

    async def parse_data_dictionary(
        self,
        tenant: CurrentTenant,
        settings: Settings,
        dataset_id: UUID,
        *,
        filename: str,
        data: bytes,
    ) -> schemas.DataDictionaryResult:
        await self._require_dataset(tenant, dataset_id)
        from augura_api.modules.datasets.data_dictionary import parse_data_dictionary

        return await parse_data_dictionary(settings, filename, data)

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

    async def _reprofile(
        self, settings: Settings, tenant: CurrentTenant, dataset_id: UUID
    ) -> list[schemas.ColumnOut]:
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
            data = await read_bytes(settings, f.storage_path, expected_org=str(tenant.tenant_id))
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
        await self._reject_pii_headers([(fn, sheets) for fn, sheets, _data in parsed])
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
        columns = await self._reprofile(settings, tenant, dataset.id)
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
        await self._reject_pii_headers([(fn, sheets) for fn, sheets, _data in parsed])
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
        columns = await self._reprofile(settings, tenant, dataset_id)
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
        """Delete a file row from the dataset, reprofile, then purge the storage object.

        Ordering guarantee (mirrors erase_dataset — same FastAPI bg-task ordering fix):
          1. Verify dataset ownership and retrieve the target file (request session).
          2. In a DEDICATED committed session: delete the file row + reprofile so
             both mutations are in the same committed transaction.
          3. AFTER that commit returns, purge the storage object (best-effort).
          4. Re-read the refreshed dataset/files/columns via the request session
             for the UploadResult response shape.
        """
        # Step 1: verify ownership and capture the file's storage path.
        await self._require_dataset(tenant, dataset_id)
        target = await self.repo.get_file(dataset_id, file_id)
        if target is None:
            raise NotFoundError("file not found", file_id=str(file_id))
        removed_path: str | None = target.storage_path

        # Step 2: delete the file row and reprofile in a dedicated committed session.
        sm = get_sessionmaker(settings)
        async with sm() as s, s.begin():
            await s.execute(set_user_stmt(tenant.user_id))
            await s.execute(set_tenant_stmt(tenant.tenant_id))
            inner = DatasetService(DatasetRepo(s))
            await inner.repo.delete_file(dataset_id, file_id)
            await inner._reprofile(settings, tenant, dataset_id)
        # s.begin() context has exited → deletion + reprofile are durably committed.

        # Step 3: purge the storage object (best-effort, post-commit).
        if removed_path:
            await purge_objects(settings, str(tenant.tenant_id), [removed_path])

        # Step 4: re-read the refreshed state via the request session for the response.
        columns = await self._reprofile(settings, tenant, dataset_id)
        files_out = await self._files_out(dataset_id)
        refreshed = await self._require_dataset(tenant, dataset_id)
        return schemas.UploadResult(
            dataset=self._to_out(refreshed, len(columns), len(files_out)),
            columns=columns,
            files=files_out,
            warnings=[],
        )

    async def erase_dataset(
        self, tenant: CurrentTenant, settings: Settings, dataset_id: UUID
    ) -> None:
        """GDPR Art 17 erasure: delete the dataset row + all child rows (cascade),
        then purge the backing storage objects.

        Ordering guarantee:
          1. Verify ownership via the request session (raises NotFoundError if not found).
          2. Collect storage paths from the request session (read-only, no writes).
          3. Commit the DB row deletion in a DEDICATED session whose transaction
             commits deterministically when its context manager exits — this is the
             durable point of no return for the rows.
          4. Only AFTER that commit returns, call purge_objects (best-effort).

        This avoids the FastAPI BackgroundTask ordering bug: on FastAPI 0.136.x,
        background tasks execute BEFORE yield-dependency teardown, meaning they run
        before get_session's `async with session.begin()` commits.  By using our own
        dedicated session here we own the commit point and can sequence storage
        deletion deterministically after it.

        If the dedicated-session commit raises, purge_objects is never called and no
        bytes are touched.  If purge_objects fails per-path, the objects are orphaned
        (recoverable via storage audit) but the rows are already gone — the safe
        direction.

        Note: broader erasure across generated_documents, artifacts, corpus chunks,
        literature_snapshots, and agent_cache is deferred to `erase_tenant_data` (a
        full-org erasure orchestrator, to be built as a follow-up to this task).
        """
        # Step 1+2: verify ownership and gather paths (request session, read-only).
        dataset = await self._require_dataset(tenant, dataset_id)
        files = await self.repo.list_files(dataset.id)
        paths = [f.storage_path for f in files]

        # Step 3: commit the deletion in a dedicated session we fully control.
        sm = get_sessionmaker(settings)
        async with sm() as s, s.begin():
            await s.execute(set_user_stmt(tenant.user_id))
            await s.execute(set_tenant_stmt(tenant.tenant_id))
            await DatasetRepo(s).delete_dataset(tenant.tenant_id, dataset_id)
        # s.begin() context has exited → rows are durably committed.

        # Step 4: purge storage objects synchronously (best-effort, post-commit).
        await purge_objects(settings, str(tenant.tenant_id), paths)

    async def export_dataset(
        self, tenant: CurrentTenant, dataset_id: UUID
    ) -> schemas.DatasetExport:
        """GDPR Art 15/20 access/portability: returns a JSON bundle of the dataset
        metadata, profiled columns, and file metadata. Raw bytes are excluded
        (this is a metadata export for portability, not a bulk data dump).

        A usage_events row with event_type='dataset.exported' is emitted for the
        audit trail (HIPAA 164.312(b))."""
        dataset = await self._require_dataset(tenant, dataset_id)
        columns = await self.repo.list_columns(dataset_id)
        files = await self._files_out(dataset_id)
        col_count = len(columns)
        file_count = len(files)

        await analytics.log_usage(
            self.repo.session,
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            event_type="dataset.exported",
            route=f"/datasets/{dataset_id}/export",
            metadata={"dataset_id": str(dataset_id), "column_count": col_count},
        )

        return schemas.DatasetExport(
            dataset=self._to_out(dataset, col_count, file_count),
            columns=[schemas.ColumnOut.model_validate(c) for c in columns],
            files=files,
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
