# Multi-CSV datasets — design

- Date: 2026-06-22
- Status: approved (design), pending implementation plan
- Area: `apps/api` (datasets, dq) + `apps/web` (DatasetsPage) + DB bundle + api-client
- Owner: Quentin

## Problem

Today **one dataset = one file**. The "Add dataset" modal accepts multiple files but
creates *one separate dataset per file* (`uploadDatasets` loops `POST /datasets/upload`).
There is no way to register several CSVs as a **single logical dataset**, and no per-file
UI. We want: select several CSVs, give the set one name, and get **one dataset that
contains those CSVs**, each CSV rendered as its own **tile**, files **stacked vertically**.

## Decisions (from brainstorming)

1. **Model**: the named thing is **one dataset** that holds **N CSV files**. Not a folder of
   separate datasets.
2. **File relationship**: files share the **same columns** — sequential parts of one logical
   table. Row count = **sum** across files; profiling / mapping / DQ run **once** for the whole
   dataset.
3. **Column mismatch**: **warn but allow** — combine into the **union** of columns, leaving
   blanks where a file lacks a column. Each add returns human-readable warnings.
4. **Lifecycle**: **add & remove files anytime** (re-profile on every change). Removing the last
   file is allowed → leaves an empty dataset.
5. **Layout**: each CSV is a **full-width card stacked vertically** (same idiom as the current
   dataset list rows), with a remove (✕) action, an "Add files" affordance **at the bottom**,
   and union warnings shown inline.
6. **Tab rename**: dataset-detail tab **"Upload" → "Files"**.

Non-goals: folders/collections of datasets; heterogeneous multi-table datasets; per-file
mapping/DQ; cross-file schema reconciliation beyond name-based union; deleting the stored
object on file removal (left as an orphan in v1, see Open items).

## Architecture overview

```
Add modal / Files tab ──► POST /datasets/upload         (1..N files → 1 dataset)
                          POST /datasets/{id}/files      (add files, re-profile)
                          DELETE /datasets/{id}/files/{file_id}  (remove, re-profile)
                          GET  /datasets/{id}/files       (tiles)

datasets (1) ──< dataset_files (N)      new table, RLS via tenant_via_dataset
datasets.row_count   = sum(file row counts)         (kept)
datasets.storage_path = first file's ref            (legacy compat; DQ guard)
dataset_columns      = profiled UNION of all files  (kept, recomputed on change)
```

A single `_reprofile(dataset)` service helper is the heart: read every `dataset_files` row,
parse each, build the per-sheet **union** of columns, concatenate rows (blank-filled), profile
the union, `replace_columns`, and update `datasets.row_count`.

## Data model

New table in `apps/api/supabase/schema.sql` (datasets section), mirroring `dataset_columns`:

```sql
create table if not exists dataset_files (
    id           uuid primary key default gen_random_uuid(),
    dataset_id   uuid not null references datasets(id) on delete cascade,
    filename     text not null,
    storage_path text not null,
    row_count    integer,
    headers      jsonb,          -- this file's own header list (drives union + mismatch warnings)
    position     integer not null default 0,   -- display/order ("qui se suivent")
    created_at   timestamptz not null default now()
);
create index if not exists ix_dataset_files_dataset on dataset_files(dataset_id);
```

RLS in `apps/api/supabase/policies.sql` (copy the `dataset_columns` policy verbatim, renamed):

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

No structural change to `datasets`. `storage_path` and `row_count` are kept; `storage_path`
is set to the **first** file's ref for backward compatibility (DQ guard `not dataset.storage_path`,
any external reference).

SQLAlchemy: add `DatasetFile` model in `modules/datasets/models.py` (mirrors `DatasetColumn`,
`dataset_id` FK with `ondelete="CASCADE"`, `headers` as `JSONB`, `position` Integer).

### Migration `0010_dataset_files` (idempotent — schema-bundle invariant)

Because `0001_baseline` runs `schema.sql`+`policies.sql`, and migrations `0002+` must be
idempotent and re-runnable on an already-migrated DB:

1. `CREATE TABLE IF NOT EXISTS dataset_files (…)` + `CREATE INDEX IF NOT EXISTS …`.
2. `ALTER TABLE … ENABLE/FORCE ROW LEVEL SECURITY`; `DROP POLICY IF EXISTS tenant_via_dataset
   ON dataset_files; CREATE POLICY …`.
3. **Backfill** (idempotent via `NOT EXISTS`):
   ```sql
   insert into dataset_files (dataset_id, filename, storage_path, row_count, position)
   select d.id, d.name, d.storage_path, d.row_count, 0
   from datasets d
   where d.storage_path is not null
     and not exists (select 1 from dataset_files f where f.dataset_id = d.id);
   ```
   (`headers` stays NULL for backfilled rows; it is only needed for future mismatch warnings and
   is repopulated whenever a file is added/removed and `_reprofile` runs.)

The same table must be added to `schema.sql`/`policies.sql` for fresh bundles. Per the repo
invariant, a table added to `schema.sql` **bypasses alembic on an already-migrated DB**, so the
`0010` migration is what brings existing DBs (incl. prod) up to date.

**Prod**: Modal deploy runs neither migrations nor seed → apply `0010` to the live DB manually
via the **Supabase MCP** (`execute_sql`, project `fqmoylmvjoafihiuiiuj`), since the `.env`
app role is non-privileged.

## Backend contract

### Schemas (`modules/datasets/schemas.py`)

```python
class DatasetFileOut(BaseModel):              # one tile
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    row_count: int | None = None
    column_count: int = 0                      # len(headers) if present
    position: int = 0
    created_at: datetime

class DatasetOut(...):                         # add:
    file_count: int = 0

class UploadResult(...):                       # add:
    warnings: list[str] = []
    files: list[DatasetFileOut] = []
```

`UploadResult` is reused by upload, add-files, and remove (each returns the refreshed dataset,
union columns, file tiles, and any warnings).

### Endpoints (`modules/datasets/router.py`)

| Method | Route | Behaviour |
|---|---|---|
| `POST` | `/datasets/upload` | accept **`files: list[UploadFile]`** (1..N) → create **one** dataset with all files → `_reprofile` → `UploadResult`. Name = form `name` or first filename. |
| `POST` | `/datasets/{id}/files` | accept `files: list[UploadFile]` → append to existing dataset → `_reprofile` → `UploadResult` (with warnings). |
| `DELETE` | `/datasets/{id}/files/{file_id}` | remove the file row → `_reprofile` → `UploadResult`. |
| `GET` | `/datasets/{id}/files` | `list[DatasetFileOut]`. |
| `GET` | `/datasets` | unchanged shape + `file_count`. |

`POST /datasets/upload` changes its multipart field from `file` to `files` (breaking, but the
only consumer is `apps/web`; the api-client is regenerated). Keep the route declaration order:
`/cohorts...` and `/upload` before `/{dataset_id}`; declare `/{id}/files` after `/{id}`.

### Repo (`modules/datasets/repo.py`)

- `list_datasets`: add a `file_count` correlated subquery alongside the existing `column_count`.
- New: `list_files(dataset_id)`, `add_file(dataset_id, *, filename, storage_path, row_count,
  headers, position)`, `get_file(dataset_id, file_id)`, `delete_file(dataset_id, file_id)`,
  `next_position(dataset_id)`, `set_storage_and_rowcount(dataset_id, storage_path, row_count)`.
- All file methods are reachable only through an org-scoped `dataset_id` (RLS enforces tenant).

### Service (`modules/datasets/service.py`)

- `upload_dataset(tenant, settings, *, files=[(filename, data)…], name, study_id)`: parse each
  (`parse_upload` raises 413/415/400), `save_bytes` each with a `f"{uuid4()}-{filename}"` ref
  (unique — `build_ref` is deterministic), create the dataset, insert `dataset_files`, set
  `datasets.storage_path` = first ref, then `_reprofile`.
- `add_files(tenant, settings, dataset_id, files)`: require dataset, append `dataset_files`
  (positions after current max), `_reprofile`, compute warnings vs the pre-existing union.
- `remove_file(tenant, settings, dataset_id, file_id)`: require dataset + file, delete row,
  `_reprofile` (if no files remain → row_count 0, columns cleared, storage_path NULL).
- `_reprofile(tenant, settings, dataset)`: for each file `await read_bytes` → `parse_upload`;
  group sheets by sheet name; build the union of headers per sheet (first-seen order, new
  appended); concatenate rows aligning by header name (missing → `""`); `profile_column` per
  union column; `replace_columns`; update `datasets.row_count` = sum of file row counts and
  `storage_path` = first remaining ref.
- Warnings (returned by add): per added file, `"<file> added column(s): a, b"` (columns new to
  the union) and `"<file> missing column(s): x — filled blank"` (union columns absent in the file).

### DQ (`modules/dq/service.py`)

`run()` currently reads the single `dataset.storage_path`. Change it to read **all**
`dataset_files`, parse each, build the same per-sheet union/concatenation as `_reprofile`
(extract the union/concat into a shared helper used by both), and pass `raw_bytes` =
concatenation of the file bytes (the DQ engine only uses `raw_bytes` for a sha256 fingerprint
and a first-10 KiB sniff — concatenation is correct for the fingerprint). The
`not dataset.storage_path` guard still holds because upload sets it to the first file's ref;
prefer guarding on "has at least one file" instead. Mapping is unaffected (it consumes the
profiled union in `dataset_columns`).

## Frontend (`apps/web`)

### `src/intake/intakeApi.js`

- `uploadDataset(files, { name, studyId })` → one `POST /datasets/upload` with all `files`
  appended as `files`. Returns `{ dataset, columns, warnings, files }`.
- Remove `uploadDatasets` (one-per-file loop) — superseded.
- New: `addFiles(id, files)` → `POST /datasets/{id}/files`; `removeFile(id, fileId)` →
  `DELETE …`; `listFiles(id)` → `GET /datasets/{id}/files`.

### Add-dataset modal (`AddDatasetModal`)

- Name field **always visible** (default from the first file's stem). Multi-select just adds
  more files to the **one** dataset being created.
- CTA always "Add dataset" (drop the "Add N datasets" multi label and the per-file progress).
- Submit → `uploadDataset(files, {name, studyId})` → `onUploaded(result)` lands in the new
  dataset's detail. Surface `warnings` if present.
- Copy: "Select multiple CSVs to combine them into one dataset (same columns, appended)."

### Dataset detail (`DatasetDetail`) — "Files" tab

- Rename the `upload` tab label to **"Files"** (keep id `upload` or rename to `files`; update
  the empty-dataset default-tab logic accordingly).
- Replace `UploadPanel` with **`FilesPanel({ dataset, onChanged })`**:
  - `listFiles(dataset.id)` → render a **vertical stack of full-width cards**, one per file:
    file-spreadsheet icon · monospace filename · "N rows · M cols" · "added <relTime>" · remove ✕.
    Reuse the existing list-row card styling (border, `bg-secondary` icon chip, `font-mono`).
  - Below the stack: an **"Add files"** dashed dropzone/button → file picker (multiple) →
    `addFiles` → refresh files + columns + meta; show returned `warnings` inline (info banner).
  - Remove ✕ → `removeFile` → refresh. Allow removing the last file (empty dataset).
  - `onChanged` bubbles up so `DatasetDetail` re-fetches `columns`/`meta` (row/col header stats)
    after any add/remove.
- Note: the current Upload tab uploads a file that creates *another* new dataset (confusing);
  `FilesPanel` instead mutates the **current** dataset — an intentional improvement.

### `src/workspace/dataClient.js`

- `normDatasets`: expose `file_count`; the list row shows `"{file_count} files · {rows} rows ·
  {cols} cols"` when `file_count > 1` (else the existing `"{rows} rows · {cols} cols"`).

## API client regeneration

The contract changes (new endpoints, `file_count`, `warnings`, `files`, `/upload` field rename):

```bash
uv run python apps/api/scripts/dump_openapi.py          # → packages/api-client/openapi.json
npm --prefix packages/api-client run generate           # → src/schema.d.ts
```

CI drift-check fails if this is skipped.

## Testing

Backend (`apps/api/tests`, follow existing datasets/dq test style; integration tests need
`AUGURA_DATABASE_URL`):

- Upload N files → one dataset; `row_count` = sum; columns = union; `file_count` = N.
- Add file with a new column → union grows; warning lists the new column.
- Add file missing a column → union unchanged; warning lists the blank-filled column.
- Remove a file → re-profiled row_count/columns; remove last file → empty dataset.
- `GET /datasets` returns `file_count`; `GET /datasets/{id}/files` returns tiles.
- RLS: a member of org B cannot read/insert/delete `dataset_files` of org A (the db-bundle CI
  isolation proof should cover the new table).
- DQ over a 2-file dataset runs on the concatenation (bundle row count matches the union).

Frontend: lint + build. Manual: add modal multi-select creates one dataset; Files tab shows
vertical tiles; add/remove re-profiles and updates header stats; warnings render.

CI gate (must pass before push): `ruff format --check`, `ruff check`, `pyright` (strict),
`lint-imports`, `pytest`, web `eslint`/`build`, openapi drift-check.

## Open items / caveats

- Storage uses Supabase Storage in prod (cross-container consistent) and local disk in dev —
  this feature inherits that; no Modal 404 concern for new uploads.
- v1 leaves the stored object orphaned on file removal (no `storage.delete_bytes` yet). Add a
  `delete_bytes` helper later if storage hygiene matters.
- Re-profiling re-reads all files on every change (files ≤ 25 MB each). Acceptable for v1;
  could later store per-file partial profiles and merge.
- `parse_upload` already supports `.xlsx` (multi-sheet). The union is computed **per sheet
  name**, so the CSV case (single sheet `data`) is the clean common path; mixed xlsx sheets are
  handled but out of the primary UX scope.
