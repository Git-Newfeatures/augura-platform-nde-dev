# Subsystem A2 — Dataset upload → storage → parse → profile — Design

**Date:** 2026-06-16
**Status:** Proposed (awaiting review)
**Part of:** Subsystem **A** (Data Intake + DQ), slice **A2** (after A1). Build order A1→**A2**→(A3∥A4)→A5.

## Context

Today the frontend parses Excel/CSV **client-side** (`ExcelUpload.jsx` loads `xlsx.js` from a CDN), computes column summaries in-browser, and persists them via `PUT /datasets/{id}/columns`. No raw file is stored server-side. Decision (confirmed): move parsing+profiling **server-side**. A2 adds the backend capability — upload the raw file, store it via the merged `core.storage`, parse CSV/XLSX, profile columns, and persist `Dataset` + `DatasetColumn`. This stores the raw file for provenance/reproducibility, drops the external CDN dependency, and is the foundation the DQ engine (A3) reads.

## Goals

1. `POST /datasets/upload` (multipart): store raw file (`core.storage`) → parse → profile → create `Dataset` + `DatasetColumn` rows → return the dataset with columns.
2. Add server-side parsing (CSV via stdlib, XLSX via `openpyxl`) and a column profiler producing the existing `DatasetColumn` stat fields.
3. Tests at every layer + real-DB validation; api-client regenerated.

## Non-goals (deferred)

- **Frontend rewire** of `ExcelUpload`/`DatasetVerification` onto the new endpoint → **A5** (the endpoint is additive; the existing client-parse flow keeps working until A5 adopts it, avoiding collision with in-flight UI work).
- **Concept mapping / variable-check** (the column *mapping* fields `proposed_role`/`confidence`/`final_*` stay `pending`) → **A4**.
- **DQ checks** (findings, scores, bundle) → **A3**.
- **csv-predigest** (messy-file/data-dictionary heuristics + LLM) → later A-phase.
- **Legacy `.xls`** (binary) — support `.csv` + `.xlsx` only; `.xls` returns a clear 415.
- No DB migration — `datasets`/`dataset_columns` already have every needed field.

## Architecture

### Dependencies (add to `apps/api/pyproject.toml`)
- `python-multipart` (required for FastAPI `UploadFile`/`Form`).
- `openpyxl` (XLSX read). CSV uses the stdlib `csv`. (No pandas — too heavy.)

### Parsing — `src/augura_api/modules/datasets/parsing.py`
`parse_upload(filename: str, data: bytes) -> list[Sheet]` where `Sheet = {name: str, headers: list[str], rows: list[list[str]]}`.
- CSV: decode `utf-8-sig` (fallback `latin-1`); `csv.Sniffer` for delimiter (fallback `,`); first row = headers; one sheet named `"data"`. Cells coerced to `str` (empty → `""`).
- XLSX: `openpyxl.load_workbook(read_only=True, data_only=True)`; one `Sheet` per worksheet; first row = headers; `None` cells → `""`; values `str()`-ified.
- Extension/`content_type` gate: `.csv`/`.xlsx` only → else `UnsupportedMediaTypeError` (415).
- Size cap (configurable, default 25 MB) enforced before parse → 413 if exceeded.

### Profiling — `src/augura_api/modules/datasets/profiling.py`
`profile_column(name: str, values: list[str]) -> ColumnProfile` (ported/condensed from the MVP `profiler.js`), producing exactly the persisted fields:

| Field | Rule |
|-------|------|
| `value_kind` | `numeric` if ≥80% of non-empty sample (first 200) parse as float; else `date` if ≥80% parse as a date; else `categorical` if distinct/non-null ≤ 50 (and ≤ 50% ratio); else `text` |
| `n_total` | len(values) |
| `n_non_null` | count where value not in `{"", "na", "n/a"}` (case-insensitive) |
| `null_pct` | `1 - n_non_null/n_total` (0 if empty) |
| `n_distinct` | distinct non-null values |
| `min`/`max` | min/max of parsed floats (numeric only; else `None`) |
| `top_values` | up to 10 most frequent non-null values as `[{"value": str, "count": int}]` |

(A2's profiler is the lean subset that fills `DatasetColumn`. A3 ports the full DQ profiler — quartiles, sentinels, outliers — reusing this where sensible.)

### Endpoint — `datasets/router.py` + `service.py`
`POST /datasets/upload` — `UploadFile` + `Form` fields `name: str | None`, `study_id: UUID | None`.
Flow (in `DatasetService.upload_dataset`):
1. Read bytes; enforce size cap + extension.
2. `ref = core.storage.save_bytes(settings, org_id=str(tenant.tenant_id), name=<uuid>-<safe filename>, data=bytes)`.
3. `sheets = parse_upload(filename, bytes)`; `row_count = sum(len(s.rows) for s in sheets)`.
4. `dataset = repo.create(... name=name or filename, storage_path=ref, row_count=row_count, status="uploaded", study_id=...)`.
5. For each sheet/column: `profile_column` → `repo.add_columns(dataset_id, [...])` (mapping fields left default `pending`).
6. Return `DatasetOut` + the profiled `ColumnOut[]` (reuse existing schemas; add an `UploadResult { dataset, columns }` if cleaner).

Reuse the existing `DatasetRepo.create` (it already takes `storage_path`) and add `add_columns(dataset_id, rows)` if not present (the module already has `replace_columns`; reuse it).

### RLS / tenancy
Standard: `CurrentTenantDep` + `SessionDep`; `Dataset.org_id = tenant`, `dataset_columns` scoped via parent (existing policy). No new policy.

## Error handling
- 401 unauth; 413 too large; 415 unsupported type; 422 unparseable (empty/headerless) with a clear message; 5xx only on storage/DB failure.

## Testing
- **Unit — profiler:** numeric (min/max/value_kind), categorical (n_distinct, top_values counts), date detection, all-missing (null_pct=1), mixed → text.
- **Unit — parser:** small CSV bytes → sheet/headers/rows; small XLSX (built in-test via openpyxl) → sheets; `.xls`/`.txt` → 415; oversize → 413.
- **Route:** `POST /datasets/upload` in OpenAPI; 401 without auth.
- **Integration (DB):** upload a tiny CSV → one `Dataset` (storage_path set, row_count correct, status uploaded) + N `DatasetColumn` rows with profiled stats; tenant-scoped (RLS); file readable back via `core.storage.read_bytes`.
- **api-client drift:** regenerate (clean worktree); CI green.

## Acceptance criteria
1. `POST /datasets/upload` accepts a CSV or XLSX, stores the raw file, returns the dataset + profiled columns; 413/415/422 paths behave.
2. `dataset_columns` populated with correct `value_kind`/stats/`top_values`; mapping fields remain `pending`.
3. `python-multipart` + `openpyxl` added; app boots; no DB migration.
4. api-client regenerated; drift-check green.
5. Backend unit + route + integration tests pass; real-DB validation (upload → rows persisted) green.

## Risks / open items
- **Messy/multi-section CSVs** (data dictionaries) parse naively in A2 — the `csv-predigest` heuristics are deferred; A2 handles clean tabular files. Flagged.
- **openpyxl memory** on big files — mitigated by `read_only=True` + the size cap.
- **Frontend still uses CDN xlsx.js** until A5 adopts `/datasets/upload` — intentional (avoids colliding with in-flight UI work).
- **`name` vs `filename`**: `datasets` has no `filename` column; original filename is stored as `name` unless an explicit `name` is provided. No schema change.
