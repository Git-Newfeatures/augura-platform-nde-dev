# Subsystem A2 — Dataset upload → parse → profile — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** `POST /datasets/upload` (multipart) stores the raw file via `core.storage`, parses CSV/XLSX server-side, profiles columns, and persists `Dataset` + `DatasetColumn` — no DB migration.

**Architecture:** New `parsing.py` (CSV stdlib + XLSX openpyxl) and `profiling.py` (column stats) in the existing `datasets` module; a service method `upload_dataset` reusing `DatasetRepo.create_dataset` + `replace_columns`; a router endpoint. Errors follow the platform `AppError`/problem+json model. Backend-only (frontend rewire = A5).

**Tech Stack:** FastAPI (`UploadFile`/`Form` → needs `python-multipart`), `openpyxl`, stdlib `csv`, SQLAlchemy async, pytest.

**Spec:** `docs/specs/2026-06-16-subsystem-a2-dataset-upload-parse-design.md`

**Conventions (from D/A1):** scoped `git add` only (never `-A`/`.`); run from `apps/api/`; api-client regen via clean worktree at HEAD; commits end with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer. Baseline: ruff/pyright/lint-imports clean; pytest 74 passed/20 skipped.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `apps/api/pyproject.toml` + `uv.lock` (modify) | add `python-multipart`, `openpyxl` |
| `apps/api/src/augura_api/core/errors.py` (modify) | `PayloadTooLargeError` (413), `UnsupportedMediaTypeError` (415) |
| `apps/api/src/augura_api/modules/datasets/profiling.py` (create) | `profile_column` → column stats |
| `apps/api/src/augura_api/modules/datasets/parsing.py` (create) | `parse_upload` → sheets |
| `apps/api/src/augura_api/modules/datasets/schemas.py` (modify) | `UploadResult` |
| `apps/api/src/augura_api/modules/datasets/service.py` (modify) | `upload_dataset` |
| `apps/api/src/augura_api/modules/datasets/router.py` (modify) | `POST /datasets/upload` |
| `apps/api/tests/test_dataset_profiling.py` (create) | profiler unit tests |
| `apps/api/tests/test_dataset_parsing.py` (create) | parser unit tests |
| `apps/api/tests/test_app_routes.py` (modify) | `/datasets/upload` in OpenAPI |
| `apps/api/tests/integration/test_datasets_upload.py` (create) | DB upload integration |
| `packages/api-client/{openapi.json,src/schema.d.ts}` (regen) | contract |

---

## Task 1: deps + error classes

- [ ] **Step 1:** Add deps. Run: `cd apps/api && uv add python-multipart openpyxl`. Confirm they land in `pyproject.toml` `[project.dependencies]` and `uv.lock` updates.

- [ ] **Step 2:** Add error classes to `apps/api/src/augura_api/core/errors.py` (after `ConflictError`):

```python
class PayloadTooLargeError(AppError):
    code = "payload_too_large"
    http_status = 413
    title = "Payload too large"


class UnsupportedMediaTypeError(AppError):
    code = "unsupported_media_type"
    http_status = 415
    title = "Unsupported media type"
```

- [ ] **Step 3:** Verify the app still boots + baseline holds.

Run: `cd apps/api && uv run python -c "from augura_api.main import create_app; create_app()" && uv run pytest -q`
Expected: no import error; pytest 74 passed / 20 skipped (unchanged).

- [ ] **Step 4: Commit**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/src/augura_api/core/errors.py
git commit -m "feat(datasets): add upload deps (python-multipart, openpyxl) + 413/415 errors

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: column profiler

**Files:** `apps/api/src/augura_api/modules/datasets/profiling.py`, `apps/api/tests/test_dataset_profiling.py`

- [ ] **Step 1: Write the failing unit test**

`apps/api/tests/test_dataset_profiling.py`:
```python
"""Tests du profiler de colonnes (datasets)."""

from augura_api.modules.datasets.profiling import profile_column


def test_numeric_column() -> None:
    p = profile_column("hba1c", ["5.1", "6.2", "7.0", "", "5.5"])
    assert p.value_kind == "numeric"
    assert p.n_total == 5
    assert p.n_non_null == 4
    assert p.value_min == 5.1
    assert p.value_max == 7.0
    assert abs(p.null_pct - 0.2) < 1e-9


def test_categorical_top_values() -> None:
    p = profile_column("sex", ["M", "F", "F", "F", "M"])
    assert p.value_kind == "categorical"
    assert p.n_distinct == 2
    top = {d["value"]: d["count"] for d in p.top_values}
    assert top == {"F": 3, "M": 2}
    assert p.value_min is None


def test_date_column() -> None:
    p = profile_column("visit_dt", ["2024-01-01", "2024-02-15", "2024-03-30"])
    assert p.value_kind == "date"


def test_all_missing() -> None:
    p = profile_column("empty", ["", "NA", "n/a"])
    assert p.n_non_null == 0
    assert p.null_pct == 1.0
    assert p.value_kind == "text"
```

- [ ] **Step 2: Run — verify FAIL** (`ModuleNotFoundError`). `cd apps/api && uv run pytest tests/test_dataset_profiling.py -q`

- [ ] **Step 3: Write `profiling.py`**

`apps/api/src/augura_api/modules/datasets/profiling.py`:
```python
"""Profilage de colonnes — porté/condensé de l'MVP profiler.js.

Produit exactement les champs persistés dans dataset_columns. Le profiler DQ
complet (quartiles, sentinelles, outliers) est porté en A3.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

_MISSING = {"", "na", "n/a"}
_SAMPLE = 200
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True)
class ColumnProfile:
    value_kind: str
    n_total: int
    n_non_null: int
    null_pct: float
    n_distinct: int
    value_min: float | None
    value_max: float | None
    top_values: list[dict[str, object]]


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_date(s: str) -> bool:
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def profile_column(name: str, values: list[str]) -> ColumnProfile:
    n_total = len(values)
    non_null = [v for v in values if v.strip().lower() not in _MISSING]
    n_non_null = len(non_null)
    null_pct = 0.0 if n_total == 0 else round(1 - n_non_null / n_total, 6)
    n_distinct = len(set(non_null))

    sample = non_null[:_SAMPLE]

    def frac(pred) -> float:  # noqa: ANN001
        return sum(1 for v in sample if pred(v)) / len(sample) if sample else 0.0

    if frac(_is_float) >= 0.8:
        value_kind = "numeric"
    elif frac(_is_date) >= 0.8:
        value_kind = "date"
    elif n_non_null and n_distinct <= 50 and (n_distinct / n_non_null) <= 0.5:
        value_kind = "categorical"
    else:
        value_kind = "text"

    value_min: float | None = None
    value_max: float | None = None
    if value_kind == "numeric":
        nums = [float(v) for v in non_null if _is_float(v)]
        if nums:
            value_min, value_max = min(nums), max(nums)

    top_values = [
        {"value": val, "count": cnt} for val, cnt in Counter(non_null).most_common(10)
    ]
    return ColumnProfile(
        value_kind=value_kind,
        n_total=n_total,
        n_non_null=n_non_null,
        null_pct=null_pct,
        n_distinct=n_distinct,
        value_min=value_min,
        value_max=value_max,
        top_values=top_values,
    )
```

- [ ] **Step 4: Run — PASS.** `cd apps/api && uv run pytest tests/test_dataset_profiling.py -q`; then `uv run ruff check ... && uv run pyright src/augura_api/modules/datasets/profiling.py`.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/augura_api/modules/datasets/profiling.py apps/api/tests/test_dataset_profiling.py
git commit -m "feat(datasets): column profiler (value_kind + stats + top_values)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: file parser

**Files:** `apps/api/src/augura_api/modules/datasets/parsing.py`, `apps/api/tests/test_dataset_parsing.py`

- [ ] **Step 1: Write the failing unit test**

`apps/api/tests/test_dataset_parsing.py`:
```python
"""Tests du parseur de fichiers (CSV/XLSX)."""

import io

import pytest
from openpyxl import Workbook

from augura_api.core.errors import PayloadTooLargeError, UnsupportedMediaTypeError
from augura_api.modules.datasets.parsing import MAX_UPLOAD_BYTES, parse_upload


def test_parse_csv() -> None:
    data = b"id,age,sex\n1,40,M\n2,55,F\n"
    sheets = parse_upload("cohort.csv", data)
    assert len(sheets) == 1
    s = sheets[0]
    assert s.headers == ["id", "age", "sex"]
    assert s.rows == [["1", "40", "M"], ["2", "55", "F"]]


def test_parse_xlsx() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["id", "age"])
    ws.append([1, 40])
    ws.append([2, 55])
    buf = io.BytesIO()
    wb.save(buf)
    sheets = parse_upload("cohort.xlsx", buf.getvalue())
    assert sheets[0].headers == ["id", "age"]
    assert sheets[0].rows == [["1", "40"], ["2", "55"]]


def test_unsupported_extension() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        parse_upload("data.xls", b"\x00\x01")


def test_oversize() -> None:
    with pytest.raises(PayloadTooLargeError):
        parse_upload("big.csv", b"x" * (MAX_UPLOAD_BYTES + 1))
```

- [ ] **Step 2: Run — verify FAIL.** `cd apps/api && uv run pytest tests/test_dataset_parsing.py -q`

- [ ] **Step 3: Write `parsing.py`**

`apps/api/src/augura_api/modules/datasets/parsing.py`:
```python
"""Parsing serveur des fichiers de données (CSV via stdlib, XLSX via openpyxl).

Renvoie une liste de feuilles {name, headers, rows} — données brutes en str
(le profilage et la DQ s'appliquent ensuite). Pas de .xls binaire (415).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from openpyxl import load_workbook

from augura_api.core.errors import (
    BadRequestError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


@dataclass(frozen=True)
class Sheet:
    name: str
    headers: list[str]
    rows: list[list[str]]


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise BadRequestError("fichier illisible (encodage non supporté)")


def _parse_csv(data: bytes) -> Sheet:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [[(c or "").strip() for c in row] for row in reader if any(c.strip() for c in row)]
    if not rows:
        raise BadRequestError("CSV vide")
    headers = rows[0]
    return Sheet(name="data", headers=headers, rows=rows[1:])


def _parse_xlsx(data: bytes) -> list[Sheet]:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets: list[Sheet] = []
    for ws in wb.worksheets:
        rows_iter = ws.iter_rows(values_only=True)
        all_rows = [
            ["" if c is None else str(c) for c in row]
            for row in rows_iter
            if any(c is not None and str(c).strip() for c in row)
        ]
        if not all_rows:
            continue
        sheets.append(Sheet(name=ws.title, headers=all_rows[0], rows=all_rows[1:]))
    wb.close()
    if not sheets:
        raise BadRequestError("classeur XLSX vide")
    return sheets


def parse_upload(filename: str, data: bytes) -> list[Sheet]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError(
            "fichier trop volumineux", max_bytes=MAX_UPLOAD_BYTES, size=len(data)
        )
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "csv":
        return [_parse_csv(data)]
    if ext == "xlsx":
        return _parse_xlsx(data)
    raise UnsupportedMediaTypeError("format non supporté (utiliser .csv ou .xlsx)", ext=ext)
```

- [ ] **Step 4: Run — PASS.** `cd apps/api && uv run pytest tests/test_dataset_parsing.py -q`; `uv run ruff check ... && uv run pyright src/augura_api/modules/datasets/parsing.py`.

- [ ] **Step 5: Commit**
```bash
git add apps/api/src/augura_api/modules/datasets/parsing.py apps/api/tests/test_dataset_parsing.py
git commit -m "feat(datasets): server-side CSV/XLSX parser

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: upload endpoint (service + router + schema)

**Files:** `schemas.py`, `service.py`, `router.py`, `tests/test_app_routes.py`

- [ ] **Step 1: Extend the route test** — in `test_app_routes.py` add `"/datasets/upload"` to the `test_openapi_exposes_routes` tuple. Run → FAIL.

- [ ] **Step 2: Add `UploadResult` to `schemas.py`** (after `DatasetOut`):
```python
class UploadResult(BaseModel):
    dataset: DatasetOut
    columns: list[ColumnOut]
```

- [ ] **Step 3: Add `upload_dataset` to `service.py`** (import additions at top: `from augura_api.core.storage import save_bytes`, `from augura_api.core.config import Settings`, `from uuid import uuid4`, and the parsing/profiling modules):

```python
    async def upload_dataset(
        self,
        tenant: CurrentTenant,
        settings: Settings,
        *,
        filename: str,
        data: bytes,
        name: str | None,
        study_id: UUID | None,
    ) -> schemas.UploadResult:
        from augura_api.core.storage import save_bytes
        from augura_api.modules.datasets.parsing import parse_upload
        from augura_api.modules.datasets.profiling import profile_column

        sheets = parse_upload(filename, data)  # raises 413/415/400
        ref = save_bytes(
            settings,
            org_id=str(tenant.tenant_id),
            name=f"{uuid4()}-{filename}",
            data=data,
        )
        row_count = sum(len(s.rows) for s in sheets)
        dataset = await self.repo.create_dataset(
            tenant.tenant_id,
            name=name or filename,
            study_id=study_id,
            storage_path=ref,
            row_count=row_count,
        )
        cols: list[schemas.ColumnIn] = []
        for sheet in sheets:
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
        column_rows = await self.repo.replace_columns(dataset.id, cols)
        return schemas.UploadResult(
            dataset=DatasetService._to_out(dataset, len(column_rows)),
            columns=[schemas.ColumnOut.model_validate(c) for c in column_rows],
        )
```
(If `_to_out` is a `@staticmethod` returning `DatasetOut`, the call above is correct; otherwise call `self._to_out`.)

- [ ] **Step 4: Add the route to `router.py`** (imports: `from fastapi import Form, UploadFile`, `from augura_api.core.deps import SettingsDep`):
```python
@router.post("/upload", response_model=schemas.UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    file: UploadFile,
    name: str | None = Form(default=None),
    study_id: UUID | None = Form(default=None),
) -> schemas.UploadResult:
    data = await file.read()
    return await _service(session).upload_dataset(
        tenant, settings, filename=file.filename or "upload.csv", data=data, name=name, study_id=study_id
    )
```
(Confirm `_service(session)` helper exists in router; if datasets uses an inline `DatasetService(DatasetRepo(session))`, match that pattern.)

- [ ] **Step 5: Run + checks.** `cd apps/api && uv run pytest tests/test_app_routes.py -q` → PASS. Then `uv run ruff check src/augura_api/modules/datasets tests/test_app_routes.py`, `uv run pyright src/augura_api/modules/datasets`, `uv run lint-imports` (datasets may import core.storage — core is allowed; ensure no cross data-module import) → all clean.

- [ ] **Step 6: Commit**
```bash
git add apps/api/src/augura_api/modules/datasets/schemas.py \
        apps/api/src/augura_api/modules/datasets/service.py \
        apps/api/src/augura_api/modules/datasets/router.py \
        apps/api/tests/test_app_routes.py
git commit -m "feat(datasets): POST /datasets/upload — store + parse + profile

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: integration test (DB upload)

**Files:** `apps/api/tests/integration/test_datasets_upload.py`

- [ ] **Step 1: Write the integration test**

`apps/api/tests/integration/test_datasets_upload.py`:
```python
"""Intégration : upload dataset → parse → profile → persistance (+ RLS)."""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.config import get_settings
from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
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
        pytest.skip("AUGURA_DATABASE_URL absent — test d'intégration sauté")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(session: AsyncSession, tenant: TenantId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(USER))
    await session.execute(set_tenant_stmt(tenant))


async def test_upload_persists_dataset_and_profiled_columns(
    sm: async_sessionmaker[AsyncSession], tmp_path,  # noqa: ANN001
) -> None:
    tenant = TenantId(uuid4())
    settings = get_settings()
    object.__setattr__(settings, "artifacts_dir", str(tmp_path))  # local storage in tmp
    csv = b"member_id,age,sex\n1,40,M\n2,55,F\n3,,F\n"

    async with sm() as session, session.begin():
        await _scope(session, tenant)
        svc = DatasetService(DatasetRepo(session))
        result = await svc.upload_dataset(
            CurrentTenant(tenant_id=tenant, user_id=USER, role="owner"),
            settings,
            filename="cohort.csv",
            data=csv,
            name=None,
            study_id=None,
        )

    assert result.dataset.row_count == 3
    assert result.dataset.storage_path
    by_name = {c.name: c for c in result.columns}
    assert by_name["age"].value_kind == "numeric"
    assert by_name["sex"].value_kind == "categorical"
    assert by_name["sex"].n_distinct == 2
```

> Note: if `Settings` is a frozen pydantic model and `object.__setattr__` is rejected, instead set `AUGURA_ARTIFACTS_DIR` env (check `core/config.py` for the field name) before `get_settings.cache_clear(); get_settings()`. The implementer should adapt to the real settings field for the artifacts dir.

- [ ] **Step 2: Run locally — SKIPPED** (no DB). Commit.
```bash
git add apps/api/tests/integration/test_datasets_upload.py
git commit -m "test(datasets): integration — upload persists dataset + profiled columns

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: regenerate api-client (clean worktree)

- [ ] **Step 1:** Clean-worktree regen (as in A1-T6):
```bash
cd /Users/quentin/Desktop/Augure/augura-platform
git worktree add --detach /tmp/augura-a2-clean HEAD
( cd /tmp/augura-a2-clean/apps/api && uv sync --dev >/dev/null 2>&1 && AUGURA_ENV=dev uv run python scripts/dump_openapi.py ) > packages/api-client/openapi.json
( cd packages/api-client && npm install --no-audit --no-fund >/dev/null 2>&1 && npm run generate )
git worktree remove --force /tmp/augura-a2-clean
```
- [ ] **Step 2:** Verify diff adds `/datasets/upload` (+ `UploadResult` schema), no unrelated changes; `npx tsc --noEmit` clean.
- [ ] **Step 3: Commit**
```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate contract for POST /datasets/upload

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: full verification + real-DB validation

- [ ] **Step 1: Static gates** (from `apps/api/`): `uv run ruff format --check .` (only your files must be clean), `uv run ruff check .`, `uv run pyright`, `uv run lint-imports`, `uv run pytest -q` (expect baseline + new profiler/parser/route tests passed, +1 integration skipped, no failures).

- [ ] **Step 2: Real-DB validation** — pgvector container, apply bundle, run the datasets upload integration test:
```bash
docker run -d --name augura-a2-validate -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=augura -p 5433:5432 pgvector/pgvector:pg16
# wait pg_isready, then apply bundle via asyncpg (schema/functions/policies/seed) as in A1-T7, then:
cd apps/api
export AUGURA_ENV=dev AUGURA_DATABASE_URL="postgresql://postgres:postgres@localhost:5433/augura"
uv run pytest tests/integration/test_datasets_upload.py -q   # expect PASS
docker rm -f augura-a2-validate
```
Expected: integration test PASS (dataset + profiled columns persisted under RLS).

---

## Self-Review (completed during planning)

- **Spec coverage:** deps + errors (T1), profiler (T2), parser incl. 413/415/empty (T3), endpoint store→parse→profile→persist (T4), integration+RLS (T5), api-client (T6), validation (T7). No DB migration (reuses Dataset/DatasetColumn).
- **Placeholders:** none — full code for profiler, parser, service, router, tests.
- **Type consistency:** `profile_column → ColumnProfile` fields map 1:1 into `ColumnIn(min=value_min, max=value_max, ...)`; `replace_columns(list[ColumnIn])` matches; `UploadResult{dataset: DatasetOut, columns: list[ColumnOut]}`; `save_bytes(settings, *, org_id, name, data)` signature matches `core/storage.py`.
- **Error model:** `PayloadTooLargeError`/`UnsupportedMediaTypeError` subclass `AppError` → problem+json automatically.
- **Open adaptation:** the integration test's artifacts-dir override must match the real `core/config.py` settings field — implementer adapts (noted inline).
