# Multi-CSV datasets — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one dataset hold several CSVs (same columns, appended) — each file a vertical tile, addable/removable anytime, profiled/mapped/DQ'd once over the union.

**Architecture:** New `dataset_files` table (N files → 1 dataset), RLS via `tenant_via_dataset` (copied from `dataset_columns`). A shared `combine_sheets` helper builds the per-sheet union of columns and concatenates rows (blank-filled). A single `_reprofile` service step recomputes `dataset_columns` (union) and `datasets.row_count` (sum) on every change. DQ reads all files and runs on the concatenation. Frontend: the Add modal creates one dataset; a vertical "Files" tile list adds/removes files.

**Tech Stack:** FastAPI · SQLAlchemy async · asyncpg · Pydantic · alembic · React 19 · Vite · Tailwind · openapi-typescript.

**Spec:** [docs/superpowers/specs/2026-06-22-multi-csv-datasets-design.md](../specs/2026-06-22-multi-csv-datasets-design.md)

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `apps/api/supabase/schema.sql` | canonical bundle table | modify (add `dataset_files`) |
| `apps/api/supabase/policies.sql` | RLS bundle | modify (add policy) |
| `apps/api/alembic/versions/0010_dataset_files.py` | migrate existing DBs + backfill | create |
| `apps/api/src/augura_api/modules/datasets/models.py` | `DatasetFile` ORM model | modify |
| `apps/api/src/augura_api/modules/datasets/combine.py` | union/concat + warnings (pure) | create |
| `apps/api/src/augura_api/modules/datasets/schemas.py` | `DatasetFileOut`, `file_count`, `warnings`, `files` | modify |
| `apps/api/src/augura_api/modules/datasets/repo.py` | file CRUD + `file_count` subquery | modify |
| `apps/api/src/augura_api/modules/datasets/service.py` | multi-file upload, add/remove, `_reprofile` | modify |
| `apps/api/src/augura_api/modules/datasets/router.py` | multi upload + `/files` routes | modify |
| `apps/api/src/augura_api/modules/dq/service.py` | run DQ over all files (concat) | modify |
| `apps/api/tests/test_dataset_combine.py` | unit: union/warnings | create |
| `apps/api/tests/test_dq_service.py` | unit: DQ fake repo gains `list_files` | modify |
| `apps/api/tests/integration/test_datasets_upload.py` | update to multi-file signature | modify |
| `apps/api/tests/integration/test_dataset_files.py` | add/remove/RLS/file_count | create |
| `packages/api-client/openapi.json` + `src/schema.d.ts` | regenerated client | regen |
| `apps/web/src/intake/intakeApi.js` | upload(multi)/add/remove/list | modify |
| `apps/web/src/workspace/DatasetsPage.jsx` | modal + vertical Files tiles + tab | modify |
| `apps/web/src/workspace/dataClient.js` | `file_count` in list rows | modify |

---

## Task 1: DB bundle — `dataset_files` table, RLS, migration + backfill

**Files:**
- Modify: `apps/api/supabase/schema.sql` (datasets section, after `dataset_columns` index ~line 124)
- Modify: `apps/api/supabase/policies.sql` (after the `dataset_columns` policy ~line 147)
- Create: `apps/api/alembic/versions/0010_dataset_files.py`

- [ ] **Step 1: Add the table to `schema.sql`** (insert right after `create index … ix_dataset_columns_dataset …`)

```sql
create table if not exists dataset_files (
    id           uuid primary key default gen_random_uuid(),
    dataset_id   uuid not null references datasets(id) on delete cascade,
    filename     text not null,
    storage_path text not null,
    row_count    integer,
    headers      jsonb,
    position     integer not null default 0,
    created_at   timestamptz not null default now()
);
create index if not exists ix_dataset_files_dataset on dataset_files(dataset_id);
```

- [ ] **Step 2: Add the RLS policy to `policies.sql`** (right after the `dataset_columns` `tenant_via_dataset` policy block)

```sql
alter table dataset_files enable row level security;
alter table dataset_files force row level security;
create policy tenant_via_dataset on dataset_files
    using (exists (
        select 1 from datasets d
        where d.id = dataset_files.dataset_id
          and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ))
    with check (exists (
        select 1 from datasets d
        where d.id = dataset_files.dataset_id
          and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    ));
```

- [ ] **Step 3: Create the idempotent migration** `apps/api/alembic/versions/0010_dataset_files.py`

```python
"""dataset_files: one dataset holds many CSV files (union of columns)

Adds the dataset_files table + its tenant_via_dataset RLS policy (mirrors
dataset_columns), and backfills one file row per existing single-file dataset so
legacy datasets keep working as "a dataset with one file". Idempotent: CREATE …
IF NOT EXISTS, DROP POLICY IF EXISTS, and a NOT EXISTS-guarded backfill. The table
also lives in the canonical bundle schema.sql executed by 0001_baseline.

Revision ID: 0010_dataset_files
Revises: 0009_artifacts_kind_document
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_dataset_files"
down_revision: str | None = "0009_artifacts_kind_document"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists dataset_files (
            id           uuid primary key default gen_random_uuid(),
            dataset_id   uuid not null references datasets(id) on delete cascade,
            filename     text not null,
            storage_path text not null,
            row_count    integer,
            headers      jsonb,
            position     integer not null default 0,
            created_at   timestamptz not null default now()
        );
        """
    )
    op.execute(
        "create index if not exists ix_dataset_files_dataset on dataset_files(dataset_id);"
    )
    op.execute("alter table dataset_files enable row level security;")
    op.execute("alter table dataset_files force row level security;")
    op.execute("drop policy if exists tenant_via_dataset on dataset_files;")
    op.execute(
        """
        create policy tenant_via_dataset on dataset_files
            using (exists (
                select 1 from datasets d
                where d.id = dataset_files.dataset_id
                  and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
            ))
            with check (exists (
                select 1 from datasets d
                where d.id = dataset_files.dataset_id
                  and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
            ));
        """
    )
    op.execute(
        """
        insert into dataset_files (dataset_id, filename, storage_path, row_count, position)
        select d.id, d.name, d.storage_path, d.row_count, 0
        from datasets d
        where d.storage_path is not null
          and not exists (select 1 from dataset_files f where f.dataset_id = d.id);
        """
    )


def downgrade() -> None:
    op.execute("drop policy if exists tenant_via_dataset on dataset_files;")
    op.execute("drop table if exists dataset_files;")
```

- [ ] **Step 4: Verify alembic sees a single linear head**

Run: `cd apps/api && uv run alembic heads`
Expected: prints `0010_dataset_files (head)` and nothing else.

- [ ] **Step 5: Commit**

```bash
git add apps/api/supabase/schema.sql apps/api/supabase/policies.sql apps/api/alembic/versions/0010_dataset_files.py
git commit -m "feat(datasets): dataset_files table + RLS + backfill migration"
```

> RLS isolation on the new table is proven by the `db-bundle` CI job (real Postgres). Prod: apply `0010` to the live DB via the Supabase MCP (`execute_sql`, project `fqmoylmvjoafihiuiiuj`) — Modal runs neither migrations nor seed.

---

## Task 2: `DatasetFile` ORM model

**Files:**
- Modify: `apps/api/src/augura_api/modules/datasets/models.py` (add class after `DatasetColumn`, ~line 59)

- [ ] **Step 1: Add the model** (imports `JSONB`, `ForeignKey`, `Integer`, `Text`, `DateTime`, `text` already present)

```python
class DatasetFile(Base):
    __tablename__ = "dataset_files"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    headers: Mapped[list[Any] | None] = mapped_column(JSONB)
    position: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
```

- [ ] **Step 2: Verify it imports & types** — Run: `cd apps/api && uv run python -c "from augura_api.modules.datasets.models import DatasetFile; print(DatasetFile.__tablename__)"` → Expected: `dataset_files`

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/augura_api/modules/datasets/models.py
git commit -m "feat(datasets): DatasetFile ORM model"
```

---

## Task 3: `combine.py` — union + warnings (pure, TDD)

**Files:**
- Create: `apps/api/src/augura_api/modules/datasets/combine.py`
- Test: `apps/api/tests/test_dataset_combine.py`

- [ ] **Step 1: Write the failing test** `apps/api/tests/test_dataset_combine.py`

```python
"""Unit tests for the multi-file union/concat helper (no DB)."""

from augura_api.modules.datasets.combine import (
    combine_sheets,
    file_headers,
    file_warnings,
)
from augura_api.modules.datasets.parsing import parse_upload


def test_union_appends_new_columns_and_blank_fills() -> None:
    f1 = parse_upload("a.csv", b"id,age\n1,40\n2,50\n")
    f2 = parse_upload("b.csv", b"id,age,crp\n3,60,5\n")
    combined = combine_sheets([("a.csv", f1), ("b.csv", f2)])
    assert len(combined) == 1
    sheet = combined[0]
    assert sheet.headers == ["id", "age", "crp"]
    assert len(sheet.rows) == 3
    assert sheet.rows[0] == ["1", "40", ""]
    assert sheet.rows[2] == ["3", "60", "5"]


def test_file_headers_dedup_across_sheets() -> None:
    sheets = parse_upload("a.csv", b"id,age\n1,40\n")
    assert file_headers(sheets) == ["id", "age"]


def test_file_warnings_added_and_missing() -> None:
    assert file_warnings(["id", "age"], ["id", "age", "crp"], "b.csv") == [
        "b.csv added column(s): crp"
    ]
    assert file_warnings(["id", "age", "crp"], ["id", "age"], "c.csv") == [
        "c.csv missing column(s): crp — filled blank"
    ]
    assert file_warnings(["id", "age"], ["id", "age"], "d.csv") == []
```

- [ ] **Step 2: Run it — Expected: FAIL** (`ModuleNotFoundError: …datasets.combine`)

Run: `cd apps/api && uv run pytest tests/test_dataset_combine.py -q`

- [ ] **Step 3: Implement** `apps/api/src/augura_api/modules/datasets/combine.py`

```python
"""Combine several uploaded files of one dataset into a logical table.

Files share columns ("se suivent"). Per sheet name we build the union of headers
(first-seen order, new headers appended) and concatenate rows aligned by header
name — blanks where a file lacks a column. CSV files have a single sheet 'data',
so the common case is a plain union + append.
"""

from __future__ import annotations

from dataclasses import dataclass

from augura_api.modules.datasets.parsing import Sheet


@dataclass(frozen=True)
class CombinedSheet:
    name: str
    headers: list[str]
    rows: list[list[str]]


def file_headers(sheets: list[Sheet]) -> list[str]:
    """Distinct headers of one file, across its sheets, in first-seen order."""
    out: list[str] = []
    for sheet in sheets:
        for h in sheet.headers:
            if h not in out:
                out.append(h)
    return out


def combine_sheets(files: list[tuple[str, list[Sheet]]]) -> list[CombinedSheet]:
    order: list[str] = []
    headers: dict[str, list[str]] = {}
    rows: dict[str, list[list[str]]] = {}
    for _filename, sheets in files:
        for sheet in sheets:
            if sheet.name not in headers:
                order.append(sheet.name)
                headers[sheet.name] = []
                rows[sheet.name] = []
            for h in sheet.headers:
                if h not in headers[sheet.name]:
                    headers[sheet.name].append(h)
    for _filename, sheets in files:
        for sheet in sheets:
            hdr = headers[sheet.name]
            pos = {h: i for i, h in enumerate(sheet.headers)}
            for row in sheet.rows:
                rows[sheet.name].append(
                    [row[pos[h]] if h in pos and pos[h] < len(row) else "" for h in hdr]
                )
    return [CombinedSheet(name=n, headers=headers[n], rows=rows[n]) for n in order]


def file_warnings(established: list[str], new_headers: list[str], filename: str) -> list[str]:
    """Human-readable diff of an added file's headers vs the established union."""
    added = [h for h in new_headers if h not in established]
    missing = [h for h in established if h not in new_headers]
    out: list[str] = []
    if added:
        out.append(f"{filename} added column(s): {', '.join(added)}")
    if missing:
        out.append(f"{filename} missing column(s): {', '.join(missing)} — filled blank")
    return out
```

- [ ] **Step 4: Run it — Expected: PASS**

Run: `cd apps/api && uv run pytest tests/test_dataset_combine.py -q`

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/datasets/combine.py apps/api/tests/test_dataset_combine.py
git commit -m "feat(datasets): combine_sheets union/concat helper"
```

---

## Task 4: Schemas — `DatasetFileOut`, `file_count`, `warnings`, `files`

**Files:**
- Modify: `apps/api/src/augura_api/modules/datasets/schemas.py`

- [ ] **Step 1: Add `file_count` to `DatasetOut`** (after `column_count: int = 0`, ~line 22)

```python
    file_count: int = 0
```

- [ ] **Step 2: Add `DatasetFileOut`** (after `DatasetCreate`, ~line 31)

```python
class DatasetFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    row_count: int | None = None
    column_count: int = 0
    position: int = 0
    created_at: datetime
```

- [ ] **Step 3: Extend `UploadResult`** (replace the existing class, ~lines 82-84)

```python
class UploadResult(BaseModel):
    dataset: DatasetOut
    columns: list[ColumnOut]
    files: list[DatasetFileOut] = []
    warnings: list[str] = []
```

- [ ] **Step 4: Verify import** — Run: `cd apps/api && uv run python -c "from augura_api.modules.datasets import schemas; print(schemas.DatasetFileOut.model_fields.keys())"`
Expected: includes `filename`, `column_count`, `position`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/datasets/schemas.py
git commit -m "feat(datasets): file_count + files/warnings in dataset schemas"
```

---

## Task 5: Repo — `file_count` subquery + file CRUD

**Files:**
- Modify: `apps/api/src/augura_api/modules/datasets/repo.py`

- [ ] **Step 1: Update imports** (top of file)

```python
from sqlalchemy import delete, func, select, update
```

and add `DatasetFile` to the models import:

```python
from augura_api.modules.datasets.models import (
    CohortBiomarker,
    CohortMember,
    Dataset,
    DatasetColumn,
    DatasetFile,
)
```

- [ ] **Step 2: Replace `list_datasets`** so it also returns `file_count`

```python
    async def list_datasets(self, tenant_id: TenantId) -> list[tuple[Dataset, int, int]]:
        """Datasets of the tenant + column count + file count (correlated subqueries)."""
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
```

- [ ] **Step 3: Add file methods** (after `count_columns`, before `create_dataset`)

```python
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
```

- [ ] **Step 4: Verify import & types** — Run: `cd apps/api && uv run pyright src/augura_api/modules/datasets/repo.py`
Expected: 0 errors. (`list_datasets` callers are fixed in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/datasets/repo.py
git commit -m "feat(datasets): repo file CRUD + file_count subquery"
```

---

## Task 6: Service — multi-file upload, add/remove, `_reprofile`

**Files:**
- Modify: `apps/api/src/augura_api/modules/datasets/service.py`
- Modify: `apps/api/tests/integration/test_datasets_upload.py` (call-site updated to the new signature)

- [ ] **Step 1: Update `list_datasets` and `_to_out`** (the repo now yields 3-tuples)

Replace `_to_out` and `list_datasets`:

```python
    @staticmethod
    def _to_out(
        dataset: Dataset, column_count: int, file_count: int = 0
    ) -> schemas.DatasetOut:
        return schemas.DatasetOut.model_validate(dataset).model_copy(
            update={"column_count": column_count, "file_count": file_count}
        )

    async def list_datasets(self, tenant: CurrentTenant) -> list[schemas.DatasetOut]:
        rows = await self.repo.list_datasets(tenant.tenant_id)
        return [self._to_out(d, col, files) for d, col, files in rows]
```

- [ ] **Step 2: Update `get_dataset`** to also report `file_count`

```python
    async def get_dataset(self, tenant: CurrentTenant, dataset_id: UUID) -> schemas.DatasetOut:
        dataset = await self._require_dataset(tenant, dataset_id)
        return self._to_out(
            dataset,
            await self.repo.count_columns(dataset_id),
            await self.repo.count_files(dataset_id),
        )
```

- [ ] **Step 3: Replace `upload_dataset` and add `_reprofile`, `add_files`, `remove_file`, `list_files`, `_files_out`** (replace the whole existing `upload_dataset` method, keep `import_cohort` etc. untouched)

```python
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
        self, settings: Settings, dataset_id: UUID
    ) -> list[schemas.ColumnOut]:
        from augura_api.core.storage import read_bytes
        from augura_api.modules.datasets.combine import combine_sheets
        from augura_api.modules.datasets.parsing import parse_upload
        from augura_api.modules.datasets.profiling import profile_column

        files = await self.repo.list_files(dataset_id)
        parsed = []
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

        # Parse everything first so a bad file aborts before any write.
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
```

- [ ] **Step 4: Update the existing integration test call-site** in `apps/api/tests/integration/test_datasets_upload.py` (the `svc.upload_dataset(...)` call ~lines 69-76)

```python
        result = await svc.upload_dataset(
            CurrentTenant(tenant_id=tenant, user_id=USER, role="owner"),
            settings,
            files=[("cohort.csv", csv)],
            name=None,
            study_id=None,
        )
```

- [ ] **Step 5: Run pyright + the unit suite** (DB-less)

Run: `cd apps/api && uv run pyright src/augura_api/modules/datasets/service.py && uv run pytest tests/test_dataset_combine.py tests/test_dataset_parsing.py tests/test_dataset_profiling.py -q`
Expected: 0 pyright errors; tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/datasets/service.py apps/api/tests/integration/test_datasets_upload.py
git commit -m "feat(datasets): multi-file upload, add/remove files, reprofile union"
```

---

## Task 7: Router — multi upload + `/files` routes

**Files:**
- Modify: `apps/api/src/augura_api/modules/datasets/router.py`

- [ ] **Step 1: Update the import** for `UploadFile` list (already imports `Form, UploadFile`)

No import change needed.

- [ ] **Step 2: Replace the `/upload` handler** (~lines 69-86)

```python
@router.post("/upload", response_model=schemas.UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    tenant: CurrentTenantDep,
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
```

- [ ] **Step 3: Add the `/files` routes** (after the `replace_columns` handler at the end of the file)

```python
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
    tenant: CurrentTenantDep,
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
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> schemas.UploadResult:
    return await _service(session).remove_file(tenant, settings, dataset_id, file_id)
```

- [ ] **Step 4: Verify the app builds & routes register**

Run: `cd apps/api && uv run python -c "from augura_api.main import create_app; app=create_app(); print([r.path for r in app.routes if '/files' in getattr(r,'path','')])"`
Expected: lists `/datasets/{dataset_id}/files` and `/datasets/{dataset_id}/files/{file_id}`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/datasets/router.py
git commit -m "feat(datasets): multi-file upload route + /files add/list/delete"
```

---

## Task 8: DQ over all files (concatenation)

**Files:**
- Modify: `apps/api/src/augura_api/modules/dq/service.py`
- Modify: `apps/api/tests/test_dq_service.py` (fake repo gains `list_files`)

- [ ] **Step 1: Update the unit test** `apps/api/tests/test_dq_service.py` — give the fake repo `list_files` and keep the FileNotFoundError→404 assertion

```python
class _FakeDatasetRepo:
    async def get_dataset(self, tenant_id: object, dataset_id: object) -> object:
        return SimpleNamespace(storage_path="org/x/f.csv", name="f.csv")

    async def list_files(self, dataset_id: object) -> list[object]:
        return [SimpleNamespace(filename="f.csv", storage_path="org/x/f.csv")]
```

- [ ] **Step 2: Run it — Expected: FAIL** (current service ignores `list_files`; once we switch the read loop it must still 404)

Run: `cd apps/api && uv run pytest tests/test_dq_service.py -q`
Expected after Step 3 it PASSES; before Step 3 it still passes via the old path — so this step documents intent; proceed to Step 3.

- [ ] **Step 3: Rewrite `DqService.run`** to read every file and run on the concatenation

```python
    async def run(
        self,
        tenant: CurrentTenant,
        settings: Settings,
        dataset_id: UUID,
        *,
        weight_profile: str = "exploratory",
    ) -> schemas.DqRunResult:
        from augura_api.modules.datasets.combine import combine_sheets

        dataset = await self.datasets.get_dataset(tenant.tenant_id, dataset_id)
        if dataset is None:
            raise NotFoundError("dataset not found", dataset_id=str(dataset_id))
        files = await self.datasets.list_files(dataset_id)
        if not files:
            raise NotFoundError("dataset has no file", dataset_id=str(dataset_id))
        parsed = []
        raw = b""
        try:
            for f in files:
                data = await read_bytes(settings, f.storage_path)
                raw += data
                parsed.append((f.filename, parse_upload(f.filename, data)))
        except FileNotFoundError as exc:
            raise NotFoundError("dataset file unavailable", dataset_id=str(dataset_id)) from exc
        combined = combine_sheets(parsed)
        bundle = run_dq(
            [{"name": s.name, "headers": s.headers, "rows": s.rows} for s in combined],
            raw_bytes=raw,
            weight_profile=weight_profile,
        )
        row = await self.repo.create_bundle(
            tenant.tenant_id,
            dataset_id=dataset_id,
            score_profile=weight_profile,
            overall_score=bundle["summary"]["overall_score"],
            status=bundle["meta"]["status"],
            requires_resolution=bundle["summary"]["requires_resolution"],
            bundle=bundle,
        )
        return schemas.DqRunResult(
            bundle_id=row.id,
            status=row.status,
            overall_score=float(row.overall_score) if row.overall_score is not None else None,
        )
```

- [ ] **Step 4: Run unit test + pyright — Expected: PASS / 0 errors**

Run: `cd apps/api && uv run pytest tests/test_dq_service.py -q && uv run pyright src/augura_api/modules/dq/service.py`

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/augura_api/modules/dq/service.py apps/api/tests/test_dq_service.py
git commit -m "feat(dq): run checks over the concatenation of all dataset files"
```

---

## Task 9: Integration tests — add/remove/file_count/RLS

**Files:**
- Create: `apps/api/tests/integration/test_dataset_files.py`

- [ ] **Step 1: Write the test** (mirrors `test_datasets_upload.py` fixtures)

```python
"""Integration: multi-file datasets — upload N, add, remove, file_count, RLS."""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.config import get_settings
from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.datasets.repo import DatasetRepo
from augura_api.modules.datasets.service import DatasetService

pytestmark = pytest.mark.integration

USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(session: AsyncSession, tenant: TenantId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(USER))
    await session.execute(set_tenant_stmt(tenant))


def _settings(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("AUGURA_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("AUGURA_ENV", os.environ.get("AUGURA_ENV", "dev"))
    get_settings.cache_clear()
    return get_settings()


async def _make_org(session: AsyncSession, tenant: TenantId) -> None:
    await session.execute(
        text("insert into orgs (id, name, slug) values (cast(:i as uuid), 'IT', :s)").bindparams(
            i=str(tenant), s="it-" + uuid4().hex[:8]
        )
    )


async def test_upload_multi_unions_columns_and_sums_rows(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    tenant_ctx = CurrentTenant(tenant_id=tenant, user_id=USER, role="owner")

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await _make_org(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        result = await svc.upload_dataset(
            tenant_ctx,
            settings,
            files=[
                ("a.csv", b"id,age\n1,40\n2,50\n"),
                ("b.csv", b"id,age,crp\n3,60,5\n"),
            ],
            name="cohort",
            study_id=None,
        )

    assert result.dataset.row_count == 3
    assert result.dataset.file_count == 2
    assert {c.name for c in result.columns} == {"id", "age", "crp"}
    assert len(result.files) == 2


async def test_add_then_remove_file_reprofiles(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    tenant_ctx = CurrentTenant(tenant_id=tenant, user_id=USER, role="owner")

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        await _make_org(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        created = await svc.upload_dataset(
            tenant_ctx, settings, files=[("a.csv", b"id,age\n1,40\n")], name="c", study_id=None
        )
        dsid = created.dataset.id

        added = await svc.add_files(tenant_ctx, settings, dsid, [("b.csv", b"id,age,crp\n2,50,9\n")])
        assert added.dataset.file_count == 2
        assert added.dataset.row_count == 2
        assert any("crp" in w for w in added.warnings)

        files = await svc.list_files(tenant_ctx, dsid)
        to_remove = next(f for f in files if f.filename == "b.csv")
        removed = await svc.remove_file(tenant_ctx, settings, dsid, to_remove.id)
        assert removed.dataset.file_count == 1
        assert removed.dataset.row_count == 1
        assert "crp" not in {c.name for c in removed.columns}


async def test_files_are_tenant_isolated(
    sm: async_sessionmaker[AsyncSession],
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = TenantId(uuid4())
    intruder = TenantId(uuid4())
    settings = _settings(tmp_path, monkeypatch)
    owner_ctx = CurrentTenant(tenant_id=owner, user_id=USER, role="owner")

    async with sm() as session, session.begin():
        await _scope(session, owner)
        await _make_org(session, owner)
        created = await DatasetService(DatasetRepo(session)).upload_dataset(
            owner_ctx, settings, files=[("a.csv", b"id\n1\n")], name="c", study_id=None
        )
        dsid = created.dataset.id

    # A different tenant must not see the owner's files (RLS via dataset).
    async with sm() as session, session.begin():
        await _scope(session, intruder)
        await _make_org(session, intruder)
        intruder_ctx = CurrentTenant(tenant_id=intruder, user_id=USER, role="owner")
        with pytest.raises(NotFoundError):
            await DatasetService(DatasetRepo(session)).list_files(intruder_ctx, dsid)
```

- [ ] **Step 2: Run (skips without DB; passes with a throwaway Supabase branch)**

Run: `cd apps/api && AUGURA_DATABASE_URL="$AUGURA_DATABASE_URL" uv run pytest tests/integration/test_dataset_files.py -q`
Expected: PASS (or `skipped` if `AUGURA_DATABASE_URL` is unset). Never point at the prod ref `fqmoylmvjoafihiuiiuj` (the guard fails hard).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/integration/test_dataset_files.py
git commit -m "test(datasets): multi-file upload/add/remove + RLS isolation"
```

---

## Task 10: Regenerate the API client

**Files:**
- Modify (generated): `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts`

- [ ] **Step 1: Dump the OpenAPI**

Run: `cd /Users/quentin/Desktop/Augure/augura-platform && uv run --project apps/api python apps/api/scripts/dump_openapi.py`
Expected: writes `packages/api-client/openapi.json` (now containing `/datasets/{dataset_id}/files` + `file_count`/`warnings`/`files`).

- [ ] **Step 2: Generate the TS types**

Run: `npm --prefix packages/api-client run generate`
Expected: updates `packages/api-client/src/schema.d.ts`.

- [ ] **Step 3: Commit**

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate for multi-file datasets"
```

---

## Task 11: Frontend — intake API helpers

**Files:**
- Modify: `apps/web/src/intake/intakeApi.js`

- [ ] **Step 1: Replace the upload helpers** (drop `uploadDatasets`; `uploadDataset` now takes an array)

```javascript
// Helpers for the intake pipeline (upload → map → DQ), wired to the FastAPI backend.
import { apiFetch, apiJson } from '../api'

// Create ONE dataset from one or more CSV/Excel files (same columns, appended).
export async function uploadDataset(files, { name, studyId } = {}) {
  const fd = new FormData()
  for (const f of Array.from(files || [])) fd.append('files', f)
  if (name) fd.append('name', name)
  if (studyId) fd.append('study_id', studyId)
  const res = await apiFetch('/datasets/upload', { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`upload ${res.status}: ${(await res.text()).slice(0, 300)}`)
  return res.json() // { dataset, columns, files, warnings }
}

// Append more files to an existing dataset → re-profiled { dataset, columns, files, warnings }.
export async function addFiles(id, files) {
  const fd = new FormData()
  for (const f of Array.from(files || [])) fd.append('files', f)
  const res = await apiFetch(`/datasets/${id}/files`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`add files ${res.status}: ${(await res.text()).slice(0, 300)}`)
  return res.json()
}

export const removeFile = (id, fileId) =>
  apiJson(`/datasets/${id}/files/${fileId}`, { method: 'DELETE' })
export const listFiles = (id) => apiJson(`/datasets/${id}/files`)

export const mapDataset = (id) => apiJson(`/datasets/${id}/map`, { method: 'POST' })
export const runDq = (id) => apiJson(`/datasets/${id}/dq`, { method: 'POST' })
export const getDq = (id) => apiJson(`/datasets/${id}/dq`)
export const listColumns = (id) => apiJson(`/datasets/${id}/columns`)
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/intake/intakeApi.js
git commit -m "feat(web): intake API for multi-file datasets (upload/add/remove/list)"
```

---

## Task 12: Frontend — Add modal (one dataset) + vertical Files tiles + tab

**Files:**
- Modify: `apps/web/src/workspace/DatasetsPage.jsx`
- Modify: `apps/web/src/workspace/dataClient.js`

- [ ] **Step 1: `dataClient.js` — expose `file_count`** (in `normDatasets`, ~lines 43-52)

```javascript
const normDatasets = (rows, studyNameById = new Map()) =>
  (rows ?? []).map((d) => ({
    id: d.id,
    name: d.name,
    rows: d.row_count != null ? d.row_count.toLocaleString() : '—',
    cols: d.column_count ?? '—',
    files: d.file_count ?? 0,
    study: studyNameById.get(d.study_id) ?? '',
    state: d.status ?? 'pending',
    when: relTime(d.created_at),
  }))
```

- [ ] **Step 2: List row meta — show file count when > 1** (in `DatasetsPage`, the row meta ~lines 994-996)

```jsx
              <div className="w-40 flex-shrink-0 text-right font-mono text-[12.5px] text-muted-foreground">
                {d.files > 1 ? `${d.files} files · ` : ''}{d.rows} rows · {d.cols} cols
              </div>
```

- [ ] **Step 3: Replace `UploadPanel` with `FilesPanel`** (replace the whole `function UploadPanel(...) {…}` block, ~lines 152-216). Imports already include `Upload`, `X`, `Database`, `Card`, `SectionTitle`, `ColumnsTable`, `useState`, `useRef`, `useEffect`; add `Trash2`, `Plus`, `FileSpreadsheet` to the existing `lucide-react` import line and `addFiles`, `removeFile`, `listFiles` to the `intakeApi` import.

```jsx
function FilesPanel({ dataset, columns, onChanged }) {
  const [files, setFiles] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [warnings, setWarnings] = useState([])
  const fileRef = useRef(null)

  async function refresh() {
    setFiles(await listFiles(dataset.id).catch(() => []))
  }
  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset.id])

  async function handleAdd(fileList) {
    const picked = Array.from(fileList || [])
    if (!picked.length) return
    setBusy(true)
    setError(null)
    try {
      const res = await addFiles(dataset.id, picked)
      setWarnings(res?.warnings || [])
      await refresh()
      onChanged?.()
    } catch (e) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleRemove(fileId) {
    setBusy(true)
    setError(null)
    try {
      const res = await removeFile(dataset.id, fileId)
      setWarnings(res?.warnings || [])
      await refresh()
      onChanged?.()
    } catch (e) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="gap-0 rounded-xl border p-5">
        <SectionTitle
          icon={<Upload size={15} className="text-primary" />}
          sub="CSV or Excel files with the same columns — appended into one dataset, profiled server-side."
        >
          Files
        </SectionTitle>

        {warnings.length > 0 && (
          <div className="mb-3 flex flex-col gap-1 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-[12px] text-primary">
            {warnings.map((w, i) => (
              <span key={i}>{w}</span>
            ))}
          </div>
        )}

        <div className="flex flex-col gap-2.5">
          {files === null ? (
            <span className="text-[12px] italic text-muted-foreground">Loading files…</span>
          ) : files.length === 0 ? (
            <span className="text-[12px] text-muted-foreground">No files yet — add one below.</span>
          ) : (
            files.map((f) => (
              <div
                key={f.id}
                className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3.5"
              >
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                  <FileSpreadsheet size={17} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-[13px] text-foreground">{f.filename}</div>
                  <div className="mt-0.5 text-[11.5px] text-muted-foreground">
                    {f.row_count != null ? `${Number(f.row_count).toLocaleString()} rows` : '—'} ·{' '}
                    {f.column_count ?? 0} cols
                  </div>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRemove(f.id)}
                  aria-label={`Remove ${f.filename}`}
                  className="flex-shrink-0 text-muted-foreground transition-colors hover:text-destructive disabled:opacity-40"
                >
                  <X size={16} />
                </button>
              </div>
            ))
          )}

          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            multiple
            className="hidden"
            onChange={(e) => handleAdd(e.target.files)}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            onDrop={(e) => {
              e.preventDefault()
              handleAdd(e.dataTransfer.files)
            }}
            onDragOver={(e) => e.preventDefault()}
            className="flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-secondary/40 px-4 py-4 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary/80 disabled:opacity-50"
          >
            <Plus size={15} />
            {busy ? 'Working…' : 'Add files'}
          </button>
          {error && <span className="text-[11px] text-destructive">{error}</span>}
        </div>
      </Card>

      {columns && columns.length > 0 && <ColumnsTable columns={columns} />}
    </div>
  )
}
```

- [ ] **Step 4: Wire the renamed tab + panel** in `DatasetDetail`

In the `SubTabs` `tabs` array (~line 512) rename the first tab label:

```jsx
          { id: 'upload', label: 'Files', icon: <Upload size={14} /> },
```

Replace the upload-tab render (~line 524) — pass the dataset + refresh hook:

```jsx
      {sub === 'upload' && (
        <FilesPanel
          dataset={d}
          columns={columns}
          onChanged={async () => {
            setColumns(await listColumns(d.id).catch(() => []))
            setMeta(await apiJson(`/datasets/${d.id}`).catch(() => null))
          }}
        />
      )}
```

- [ ] **Step 5: Update `AddDatasetModal` to create ONE dataset** — always show the name field, drop the per-file loop. Replace the `multi`-dependent pieces:

Replace the `submit` function (~lines 736-771):

```jsx
  async function submit() {
    if (!files.length || busy) return
    setBusy(true)
    setError(null)
    try {
      const result = await uploadDataset(files, {
        name: name.trim() || undefined,
        studyId: studyId || undefined,
      })
      onUploaded(result)
    } catch (e) {
      setError(String(e?.message || e))
      setBusy(false)
    }
  }
```

Replace the `ctaLabel` (~lines 773-779):

```jsx
  const ctaLabel = busy ? 'Uploading…' : 'Add dataset'
```

Make the name field always visible (remove the `{!multi && (` guard around the Dataset-name `<label>`, ~lines 805-815) so it always renders. Update the modal subtitle (~lines 790-793):

```jsx
              Register a cohort dataset — select one or more CSV/Excel files with the same
              columns to combine them into one dataset.
```

The selected-files list (`multi &&` block, ~lines 852-873) can stay but change its guard from `multi` to `files.length > 0` so it shows even for a single file. The `multi` const (`const multi = files.length > 1`) and the progress/`failed` state become unused — remove `progress`, `failed`, `setProgress`, `setFailed`, and the `uploadDatasets` import; remove the `busy && multi && progress` block (~lines 875-880) and the `failed.length` block (~lines 882-890).

- [ ] **Step 6: Lint + build**

Run: `cd apps/web && npm run lint && npm run build`
Expected: no eslint errors; build succeeds.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/workspace/DatasetsPage.jsx apps/web/src/workspace/dataClient.js
git commit -m "feat(web): single-dataset modal + vertical file tiles (add/remove)"
```

---

## Task 13: Full CI gate + push

- [ ] **Step 1: Backend gate** (exactly what CI runs)

Run:
```bash
cd apps/api
uv run ruff format --check . && uv run ruff check .
uv run pyright
uv run lint-imports
uv run pytest -q
```
Expected: all pass. (Integration tests skip without `AUGURA_DATABASE_URL`; run them against a throwaway Supabase branch to fully verify — never the prod ref.)

- [ ] **Step 2: Frontend gate**

Run: `cd apps/web && npm run lint && npm run build` → Expected: pass.

- [ ] **Step 3: OpenAPI drift check** (regen again; git must be clean)

Run:
```bash
cd /Users/quentin/Desktop/Augure/augura-platform
uv run --project apps/api python apps/api/scripts/dump_openapi.py
npm --prefix packages/api-client run generate
git diff --exit-code packages/api-client/openapi.json packages/api-client/src/schema.d.ts
```
Expected: no diff (exit 0).

- [ ] **Step 4: Push**

```bash
git push origin Quentin
```

- [ ] **Step 5: Apply migration to prod DB** (manual — Modal won't). Via Supabase MCP `execute_sql` on project `fqmoylmvjoafihiuiiuj`, run the `upgrade()` SQL from `0010_dataset_files.py` (table + index + RLS policy + backfill). Then redeploy Modal (`bash apps/api/scripts/deploy_modal.sh`) so the new routes are live.

---

## Self-review notes

- **Spec coverage:** table+RLS+backfill (T1), model (T2), union/warnings (T3), schemas (T4), repo (T5), service multi/add/remove/reprofile (T6), routes (T7), DQ concat (T8), tests incl. RLS (T9), client regen (T10), intake API (T11), modal+vertical tiles+tab (T12), CI+push+prod apply (T13). All spec sections mapped.
- **Type consistency:** `upload_dataset(..., files: list[tuple[str,bytes]], name, study_id)` used identically in service, router, and both integration tests; `add_files`/`remove_file`/`list_files`/`_reprofile`/`_files_out` signatures consistent across T6/T7/T8/T9; `UploadResult` always carries `dataset, columns, files, warnings`; `list_datasets` 3-tuple consumed in T6 Step 1.
- **No placeholders:** every code/command step is concrete.
- **Risk:** re-reading all files on each change (≤25 MB each) — acceptable for v1. Orphaned storage object on remove (no `delete_bytes` yet) — documented in the spec.
