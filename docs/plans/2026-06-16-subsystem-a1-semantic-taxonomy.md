# Subsystem A1 — Semantic taxonomy (DQ-subset) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add the 7 DQ-subset taxonomy tables (public schema, read-only RLS, seeded from MVP CSVs) plus a `semantic` backend module (repo for A3/A4 + `GET /semantic/concepts`), and regenerate the api-client.

**Architecture:** Mirrors subsystem D exactly (global read-only reference tables, `FOR SELECT` backend-gate RLS, vertical-slice module, bundle seed, clean-worktree api-client regen). New: a committed CSV→SQL seed generator because the seed is ~1,700 rows.

**Tech Stack:** Postgres + RLS, SQLAlchemy async, Pydantic v2, FastAPI, pytest, ruff/pyright/import-linter, openapi-typescript.

**Spec:** `docs/specs/2026-06-16-subsystem-a1-semantic-taxonomy-design.md`
**DDL source:** `/tmp/augura-src/supabase/migrations/20260610000000_create_semantic_schema.sql`
**Seed CSVs:** `/tmp/augura-src/obsolete/standards/*.csv`

**Conventions (from D — do not deviate):** module layout mirrors `modules/reference`; `supabase/*.sql` is the single source of truth (alembic baseline runs it); RLS reference tables use explicit per-table `alter table` + `create policy backend_read ... for select` (the bundle test asserts literal table names); commits use scoped `git add <files>` only (NEVER `-A`/`.`); run backend cmds from `apps/api/`; api-client regen via clean worktree at HEAD (the working tree may carry unrelated WIP). Baseline to preserve: `ruff check` clean, `pytest` 70 passed / 17 skipped.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `apps/api/supabase/schema.sql` (modify) | Add 7 taxonomy tables + 2 indexes |
| `apps/api/supabase/policies.sql` (modify) | `FOR SELECT` RLS on the 7 tables |
| `apps/api/scripts/gen_semantic_seed.py` (create) | Deterministic CSV→SQL seed generator |
| `apps/api/supabase/seed.sql` (modify) | Append generated taxonomy seed |
| `apps/api/tests/test_gen_semantic_seed.py` (create) | Generator unit test |
| `apps/api/tests/db/test_supabase_bundle.py` (modify) | `EXPECTED_TABLES` += 7; seed + RLS asserts |
| `apps/api/src/augura_api/modules/semantic/{__init__,models,schemas,repo,service,router}.py` (create) | `semantic` vertical-slice module |
| `apps/api/src/augura_api/main.py` (modify) | Mount `semantic_router` |
| `apps/api/tests/test_semantic_service.py` (create) | Service unit test |
| `apps/api/tests/test_app_routes.py` (modify) | `/semantic/concepts` in OpenAPI + 401 |
| `apps/api/tests/integration/test_semantic_repo.py` (create) | DB + RLS integration |
| `packages/api-client/{openapi.json,src/schema.d.ts}` (regen) | Contract + client |

---

## Task 1: DB bundle — 7 taxonomy tables + RLS

**Files:** `apps/api/supabase/schema.sql`, `apps/api/supabase/policies.sql`, `apps/api/tests/db/test_supabase_bundle.py`

- [ ] **Step 1: Update the bundle test first**

In `apps/api/tests/db/test_supabase_bundle.py`, add to `EXPECTED_TABLES` (exact-set assertion): `"taxonomy_concepts"`, `"taxonomy_synonyms"`, `"taxonomy_dq_valid_values"`, `"taxonomy_measurement_units"`, `"unit_conversions"`, `"table_archetypes"`, `"dq_constraints"`.

Add a test:

```python
def test_taxonomy_tables_have_select_only_rls() -> None:
    policies = _read("policies.sql")
    for t in (
        "taxonomy_concepts", "taxonomy_synonyms", "taxonomy_dq_valid_values",
        "taxonomy_measurement_units", "unit_conversions", "table_archetypes", "dq_constraints",
    ):
        assert f"alter table {t} enable row level security" in policies
        assert f"create policy backend_read on {t}" in policies
```

- [ ] **Step 2: Run the bundle tests — verify they FAIL**

Run: `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py -q`
Expected: FAIL (missing tables in schema + missing RLS).

- [ ] **Step 3: Add the 7 tables to `schema.sql`**

Append to `apps/api/supabase/schema.sql` (before any trailing `commit;`). `taxonomy_concepts` MUST come first (children FK it). DDL ported from the MVP migration with `semantic.` stripped → public; all columns/checks/PKs/FKs kept verbatim:

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- Module: semantic (A1) — global DQ taxonomy (read-only). DDL ported from
-- the MVP semantic schema → public. Versioning/causal ontology = subsystem B.
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists taxonomy_concepts (
  local_concept_id text primary key,
  layer smallint not null check (layer between 0 and 2),
  concept_name text not null,
  review_section text,
  augura_domain text not null,
  omop_domain_id text,
  omop_target_table text,
  omop_target_concept_field text,
  namespace text,
  unit_source_value text,
  value_min numeric,
  value_max numeric,
  value_type text,
  design_rationale text,
  review_status text not null,
  version text not null,
  active boolean not null,
  canonical_unit text,
  temporality text,
  dq_column_role text,
  fhir_crosswalk text,
  sdtm_crosswalk text,
  unit_coverage_status text,
  range_support_status text,
  check (value_min is null or value_max is null or value_min <= value_max)
);

create table if not exists taxonomy_synonyms (
  local_concept_id text not null references taxonomy_concepts(local_concept_id),
  synonym text not null,
  synonym_type text not null,
  source text not null,
  review_status text not null,
  primary key (local_concept_id, synonym)
);

create table if not exists taxonomy_dq_valid_values (
  local_concept_id text not null references taxonomy_concepts(local_concept_id),
  value text not null,
  label text not null,
  coding_system text not null,
  review_status text not null,
  primary key (local_concept_id, value)
);

create table if not exists taxonomy_measurement_units (
  unit_id text primary key,
  concept_id text not null references taxonomy_concepts(local_concept_id),
  ucum_code text not null,
  display_label text not null,
  source_aliases text not null,
  status text not null,
  quantity_kind text not null,
  is_preferred boolean not null,
  review_status text not null,
  version text not null
);

create table if not exists unit_conversions (
  conversion_id text primary key,
  from_ucum text not null,
  to_ucum text not null,
  quantity_kind text not null,
  applicable_concept_id text references taxonomy_concepts(local_concept_id),
  conversion_type text not null,
  equation_id text not null,
  scale_factor numeric,
  "offset" numeric,
  precision integer not null,
  bidirectional boolean not null,
  provenance text not null,
  review_status text not null,
  version text not null
);

create table if not exists table_archetypes (
  archetype_id text primary key,
  archetype_name text not null,
  key_selectors text not null,
  semantic_score numeric not null check (semantic_score between 0 and 1),
  is_surrogate boolean not null,
  description_template text not null,
  review_status text not null,
  version text not null,
  active boolean not null
);

create table if not exists dq_constraints (
  constraint_id text primary key,
  target_scope text not null,
  subject_concept_or_role text not null,
  operator text not null,
  object_concept_or_role text,
  parameters text,
  applies_when text not null,
  severity text not null,
  implementation_id text not null,
  evidence_source text not null,
  status text not null,
  version text not null
);

create index if not exists taxonomy_synonyms_synonym_idx on taxonomy_synonyms (lower(synonym));
create index if not exists taxonomy_measurement_units_concept_idx on taxonomy_measurement_units (concept_id);
```

- [ ] **Step 4: Add RLS to `policies.sql`**

Before the final `commit;`, add (explicit per-table, like D):

```sql
-- ── Semantic taxonomy (A1): global, read-only (FOR SELECT) ───────────────
alter table taxonomy_concepts enable row level security;
alter table taxonomy_concepts force row level security;
create policy backend_read on taxonomy_concepts
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table taxonomy_synonyms enable row level security;
alter table taxonomy_synonyms force row level security;
create policy backend_read on taxonomy_synonyms
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table taxonomy_dq_valid_values enable row level security;
alter table taxonomy_dq_valid_values force row level security;
create policy backend_read on taxonomy_dq_valid_values
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table taxonomy_measurement_units enable row level security;
alter table taxonomy_measurement_units force row level security;
create policy backend_read on taxonomy_measurement_units
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table unit_conversions enable row level security;
alter table unit_conversions force row level security;
create policy backend_read on unit_conversions
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table table_archetypes enable row level security;
alter table table_archetypes force row level security;
create policy backend_read on table_archetypes
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);

alter table dq_constraints enable row level security;
alter table dq_constraints force row level security;
create policy backend_read on dq_constraints
  for select using (nullif(current_setting('app.tenant_id', true), '') is not null);
```

- [ ] **Step 5: Run the bundle tests — verify they PASS**

Run: `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py -q`
Expected: PASS. Also `uv run ruff check tests/db/test_supabase_bundle.py` passes.

- [ ] **Step 6: Commit**

```bash
git add apps/api/supabase/schema.sql apps/api/supabase/policies.sql apps/api/tests/db/test_supabase_bundle.py
git commit -m "feat(semantic): A1 taxonomy tables (public) + read-only RLS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Seed generator + generated seed

**Files:** `apps/api/scripts/gen_semantic_seed.py`, `apps/api/tests/test_gen_semantic_seed.py`, `apps/api/supabase/seed.sql`

- [ ] **Step 1: Write the generator unit test (TDD)**

Create `apps/api/tests/test_gen_semantic_seed.py`:

```python
"""Test of the semantic seed generator (CSV → SQL)."""

import csv
from pathlib import Path

from scripts.gen_semantic_seed import rows_to_sql


def _write_csv(p: Path, header: list[str], rows: list[list[str]]) -> None:
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_rows_to_sql_handles_nulls_quotes_bools_nums(tmp_path: Path) -> None:
    csv_path = tmp_path / "table_archetypes.csv"
    _write_csv(
        csv_path,
        ["archetype_id", "archetype_name", "key_selectors", "semantic_score",
         "is_surrogate", "description_template", "review_status", "version", "active"],
        [["a1", "O'Brien grain", "person|time", "0.8", "false", "", "approved", "v1", "true"]],
    )
    sql = rows_to_sql("table_archetypes", csv_path)
    assert "insert into table_archetypes" in sql
    assert "on conflict do nothing" in sql
    assert "'O''Brien grain'" in sql          # single-quote escaped
    assert "0.8" in sql and ", true" in sql    # numeric + boolean unquoted
    assert "false" in sql
    assert "NULL" in sql                        # empty description_template → NULL
```

- [ ] **Step 2: Run it — verify it FAILS**

Run: `cd apps/api && uv run pytest tests/test_gen_semantic_seed.py -q`
Expected: FAIL — `ModuleNotFoundError: scripts.gen_semantic_seed` / `rows_to_sql`.

- [ ] **Step 3: Write the generator**

Create `apps/api/scripts/gen_semantic_seed.py`:

```python
"""Generates the semantic taxonomy seed SQL from the MVP CSVs.

Usage: python scripts/gen_semantic_seed.py <csv_dir> > seed_fragment.sql
Deterministic: quoted columns, escaped values, empties → NULL, bool/num unquoted.
The produced fragment is meant to be pasted into supabase/seed.sql.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Boolean and numeric columns per table (the rest = text). Aligns with the DDL.
BOOL_COLS: dict[str, set[str]] = {
    "taxonomy_concepts": {"active"},
    "table_archetypes": {"is_surrogate", "active"},
    "taxonomy_measurement_units": {"is_preferred"},
    "unit_conversions": {"bidirectional"},
}
NUM_COLS: dict[str, set[str]] = {
    "taxonomy_concepts": {"layer", "value_min", "value_max"},
    "table_archetypes": {"semantic_score"},
    "unit_conversions": {"scale_factor", "offset", "precision"},
}
# Insertion order (FK: concepts first).
TABLES = [
    "taxonomy_concepts", "taxonomy_synonyms", "taxonomy_dq_valid_values",
    "taxonomy_measurement_units", "unit_conversions", "table_archetypes", "dq_constraints",
]


def _lit(table: str, col: str, raw: str) -> str:
    val = (raw or "").strip()
    if val == "":
        return "NULL"
    if col in BOOL_COLS.get(table, set()):
        return "true" if val.lower() in ("true", "t", "1", "yes") else "false"
    if col in NUM_COLS.get(table, set()):
        return val  # numeric literal as-is
    return "'" + val.replace("'", "''") + "'"  # quoted text, escaped


def rows_to_sql(table: str, csv_path: Path) -> str:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        col_sql = ", ".join(f'"{c}"' for c in cols)
        lines: list[str] = []
        for row in reader:
            vals = ", ".join(_lit(table, c, row.get(c, "")) for c in cols)
            lines.append(f"insert into {table} ({col_sql}) values ({vals}) on conflict do nothing;")
    return "\n".join(lines)


def main() -> None:
    csv_dir = Path(sys.argv[1])
    out: list[str] = ["-- ===== semantic taxonomy seed (A1) — generated by gen_semantic_seed.py ====="]
    for table in TABLES:
        csv_path = csv_dir / f"{table}.csv"
        if not csv_path.exists():
            print(f"-- WARNING: {csv_path} missing, table {table} not seeded", file=sys.stderr)
            continue
        out.append(f"-- {table}")
        out.append(rows_to_sql(table, csv_path))
    print("\n".join(out))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the generator test — verify it PASSES**

Run: `cd apps/api && uv run pytest tests/test_gen_semantic_seed.py -q`
Expected: PASS.

- [ ] **Step 5: Generate the seed and append to `seed.sql`**

Run:
```bash
cd apps/api
uv run python scripts/gen_semantic_seed.py /tmp/augura-src/obsolete/standards >> supabase/seed.sql
```
Then sanity-check the appended block:
```bash
grep -c "insert into taxonomy_concepts " supabase/seed.sql    # expect 171
grep -c "insert into taxonomy_synonyms " supabase/seed.sql    # expect 1372
grep -c "insert into dq_constraints " supabase/seed.sql        # expect 32
```
Expected counts: 171 / 1372 / 32. If `taxonomy_synonyms.csv` etc. differ slightly, record the actual counts (do not fail — the CSVs are the source of truth).

- [ ] **Step 6: Extend the bundle seed assertions**

In `apps/api/tests/db/test_supabase_bundle.py`, add:

```python
def test_seed_includes_semantic_taxonomy() -> None:
    seed = _read("seed.sql").lower()
    for t in ("taxonomy_concepts", "dq_constraints", "table_archetypes", "taxonomy_measurement_units"):
        assert f"insert into {t} " in seed
```

Run: `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py -q` → PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/scripts/gen_semantic_seed.py apps/api/tests/test_gen_semantic_seed.py apps/api/supabase/seed.sql apps/api/tests/db/test_supabase_bundle.py
git commit -m "feat(semantic): A1 taxonomy seed generator + generated seed (~1.7k rows)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `semantic` module — models, schemas, repo, service

**Files:** `apps/api/src/augura_api/modules/semantic/{__init__,models,schemas,repo,service}.py`, `apps/api/tests/test_semantic_service.py`

- [ ] **Step 1: Write the service unit test (TDD)**

Create `apps/api/tests/test_semantic_service.py`:

```python
"""Unit tests for the semantic service — ORM→schema mapping without a database."""

from augura_api.modules.semantic.models import TaxonomyConcept
from augura_api.modules.semantic.service import SemanticService


class _FakeRepo:
    async def list_concepts(self, *, domain: str | None = None, active: bool = True):
        return [
            TaxonomyConcept(
                local_concept_id="hba1c", layer=1, concept_name="HbA1c",
                augura_domain="cardiometabolic", review_status="approved",
                version="v1", active=True, value_type="numeric",
            )
        ]


async def test_concepts_maps_rows() -> None:
    out = await SemanticService(_FakeRepo()).concepts()  # type: ignore[arg-type]
    assert out[0].local_concept_id == "hba1c"
    assert out[0].concept_name == "HbA1c"
    assert out[0].augura_domain == "cardiometabolic"
```

- [ ] **Step 2: Run — verify FAIL** (`ModuleNotFoundError: augura_api.modules.semantic`).

Run: `cd apps/api && uv run pytest tests/test_semantic_service.py -q`

- [ ] **Step 3: Create `__init__.py`** (placeholder; router export in Task 4)

`apps/api/src/augura_api/modules/semantic/__init__.py`:
```python
"""semantic module — global DQ taxonomy (read-only, A1)."""
```

- [ ] **Step 4: Create `models.py`** (7 ORM tables — only the columns A1/A3/A4 read are mapped; unmapped columns are fine to omit since the module never writes)

`apps/api/src/augura_api/modules/semantic/models.py`:
```python
"""SQLAlchemy models for the semantic module (DDL created by the bundle)."""

from sqlalchemy import Boolean, Integer, Numeric, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class TaxonomyConcept(Base):
    __tablename__ = "taxonomy_concepts"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    layer: Mapped[int] = mapped_column(SmallInteger)
    concept_name: Mapped[str] = mapped_column(Text)
    augura_domain: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str | None] = mapped_column(Text)
    value_min: Mapped[float | None] = mapped_column(Numeric)
    value_max: Mapped[float | None] = mapped_column(Numeric)
    canonical_unit: Mapped[str | None] = mapped_column(Text)
    unit_source_value: Mapped[str | None] = mapped_column(Text)
    dq_column_role: Mapped[str | None] = mapped_column(Text)
    range_support_status: Mapped[str | None] = mapped_column(Text)
    unit_coverage_status: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)


class TaxonomySynonym(Base):
    __tablename__ = "taxonomy_synonyms"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    synonym: Mapped[str] = mapped_column(Text, primary_key=True)
    synonym_type: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)


class TaxonomyDqValidValue(Base):
    __tablename__ = "taxonomy_dq_valid_values"
    local_concept_id: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    coding_system: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)


class TaxonomyMeasurementUnit(Base):
    __tablename__ = "taxonomy_measurement_units"
    unit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    concept_id: Mapped[str] = mapped_column(Text)
    ucum_code: Mapped[str] = mapped_column(Text)
    display_label: Mapped[str] = mapped_column(Text)
    source_aliases: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    quantity_kind: Mapped[str] = mapped_column(Text)
    is_preferred: Mapped[bool] = mapped_column(Boolean)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)


class UnitConversion(Base):
    __tablename__ = "unit_conversions"
    conversion_id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_ucum: Mapped[str] = mapped_column(Text)
    to_ucum: Mapped[str] = mapped_column(Text)
    quantity_kind: Mapped[str] = mapped_column(Text)
    applicable_concept_id: Mapped[str | None] = mapped_column(Text)
    conversion_type: Mapped[str] = mapped_column(Text)
    equation_id: Mapped[str] = mapped_column(Text)
    scale_factor: Mapped[float | None] = mapped_column(Numeric)
    offset: Mapped[float | None] = mapped_column("offset", Numeric)
    precision: Mapped[int] = mapped_column(Integer)
    bidirectional: Mapped[bool] = mapped_column(Boolean)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)


class TableArchetype(Base):
    __tablename__ = "table_archetypes"
    archetype_id: Mapped[str] = mapped_column(Text, primary_key=True)
    archetype_name: Mapped[str] = mapped_column(Text)
    key_selectors: Mapped[str] = mapped_column(Text)
    semantic_score: Mapped[float] = mapped_column(Numeric)
    is_surrogate: Mapped[bool] = mapped_column(Boolean)
    description_template: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)


class DqConstraint(Base):
    __tablename__ = "dq_constraints"
    constraint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    target_scope: Mapped[str] = mapped_column(Text)
    subject_concept_or_role: Mapped[str] = mapped_column(Text)
    operator: Mapped[str] = mapped_column(Text)
    object_concept_or_role: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[str | None] = mapped_column(Text)
    applies_when: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    implementation_id: Mapped[str] = mapped_column(Text)
    evidence_source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
```

- [ ] **Step 5: Create `schemas.py`**

`apps/api/src/augura_api/modules/semantic/schemas.py`:
```python
"""Pydantic schemas — public contract of the semantic module."""

from pydantic import BaseModel, ConfigDict


class ConceptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    local_concept_id: str
    concept_name: str
    augura_domain: str
    layer: int
    value_type: str | None = None
    value_min: float | None = None
    value_max: float | None = None
    canonical_unit: str | None = None
    dq_column_role: str | None = None
    range_support_status: str | None = None
    active: bool
```

- [ ] **Step 6: Create `repo.py`** (all 7 tables — methods A3/A4 will consume internally)

`apps/api/src/augura_api/modules/semantic/repo.py`:
```python
"""Database access for the semantic module — global catalogs (read-only)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.modules.semantic.models import (
    DqConstraint,
    TableArchetype,
    TaxonomyConcept,
    TaxonomyDqValidValue,
    TaxonomyMeasurementUnit,
    TaxonomySynonym,
    UnitConversion,
)


class SemanticRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_concepts(
        self, *, domain: str | None = None, active: bool = True
    ) -> list[TaxonomyConcept]:
        stmt = select(TaxonomyConcept)
        if active:
            stmt = stmt.where(TaxonomyConcept.active.is_(True))
        if domain:
            stmt = stmt.where(TaxonomyConcept.augura_domain == domain)
        stmt = stmt.order_by(TaxonomyConcept.local_concept_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_synonyms(self) -> list[TaxonomySynonym]:
        return list((await self.session.execute(select(TaxonomySynonym))).scalars().all())

    async def list_valid_values(self) -> list[TaxonomyDqValidValue]:
        return list((await self.session.execute(select(TaxonomyDqValidValue))).scalars().all())

    async def list_measurement_units(self) -> list[TaxonomyMeasurementUnit]:
        return list((await self.session.execute(select(TaxonomyMeasurementUnit))).scalars().all())

    async def list_unit_conversions(self) -> list[UnitConversion]:
        return list((await self.session.execute(select(UnitConversion))).scalars().all())

    async def list_archetypes(self, *, active: bool = True) -> list[TableArchetype]:
        stmt = select(TableArchetype)
        if active:
            stmt = stmt.where(TableArchetype.active.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_constraints(self, *, status: str | None = "active") -> list[DqConstraint]:
        stmt = select(DqConstraint)
        if status:
            stmt = stmt.where(DqConstraint.status == status)
        return list((await self.session.execute(stmt)).scalars().all())
```

- [ ] **Step 7: Create `service.py`**

`apps/api/src/augura_api/modules/semantic/service.py`:
```python
"""Business logic for the semantic module. The router is a thin adapter."""

from typing import Protocol

from augura_api.modules.semantic import schemas
from augura_api.modules.semantic.models import TaxonomyConcept


class _ConceptReader(Protocol):
    async def list_concepts(
        self, *, domain: str | None = ..., active: bool = ...
    ) -> list[TaxonomyConcept]: ...


class SemanticService:
    def __init__(self, repo: _ConceptReader) -> None:
        self.repo = repo

    async def concepts(
        self, *, domain: str | None = None, active: bool = True
    ) -> list[schemas.ConceptOut]:
        rows = await self.repo.list_concepts(domain=domain, active=active)
        return [schemas.ConceptOut.model_validate(r) for r in rows]
```

- [ ] **Step 8: Run the service unit test — PASS**

Run: `cd apps/api && uv run pytest tests/test_semantic_service.py -q` → PASS.
Run: `uv run ruff check src/augura_api/modules/semantic tests/test_semantic_service.py && uv run pyright src/augura_api/modules/semantic` → clean.

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/augura_api/modules/semantic/__init__.py \
        apps/api/src/augura_api/modules/semantic/models.py \
        apps/api/src/augura_api/modules/semantic/schemas.py \
        apps/api/src/augura_api/modules/semantic/repo.py \
        apps/api/src/augura_api/modules/semantic/service.py \
        apps/api/tests/test_semantic_service.py
git commit -m "feat(semantic): A1 module — models, schemas, repo, service

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: router + mount + route tests

**Files:** `apps/api/src/augura_api/modules/semantic/router.py`, `.../semantic/__init__.py`, `apps/api/src/augura_api/main.py`, `apps/api/tests/test_app_routes.py`

- [ ] **Step 1: Extend route tests** — in `test_app_routes.py`, add `"/semantic/concepts"` to the `test_openapi_exposes_routes` tuple, and add `"/semantic/concepts"` to the `test_protected_routes_require_auth` tuple.

- [ ] **Step 2: Run — verify FAIL.** `cd apps/api && uv run pytest tests/test_app_routes.py -q`

- [ ] **Step 3: Create `router.py`**

`apps/api/src/augura_api/modules/semantic/router.py`:
```python
"""HTTP adapter for the semantic module."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.semantic import schemas
from augura_api.modules.semantic.repo import SemanticRepo
from augura_api.modules.semantic.service import SemanticService

router = APIRouter(prefix="/semantic", tags=["semantic"])


@router.get("/concepts", response_model=list[schemas.ConceptOut])
async def concepts(
    tenant: CurrentTenantDep,
    session: SessionDep,
    domain: str | None = None,
    active: bool = True,
) -> list[schemas.ConceptOut]:
    return await SemanticService(SemanticRepo(session)).concepts(domain=domain, active=active)
```

- [ ] **Step 4: Export router from `__init__.py`**
```python
"""Public interface of the semantic module."""

from augura_api.modules.semantic.router import router

__all__ = ["router"]
```

- [ ] **Step 5: Mount in `main.py`** — add import (alphabetical, after `reference`) `from augura_api.modules.semantic import router as semantic_router` and `app.include_router(semantic_router)` after `reference_router`.

- [ ] **Step 6: Run route tests — PASS.** `cd apps/api && uv run pytest tests/test_app_routes.py -q`. Also `uv run lint-imports` → 2 kept / 0 broken.

- [ ] **Step 7: Commit**
```bash
git add apps/api/src/augura_api/modules/semantic/router.py \
        apps/api/src/augura_api/modules/semantic/__init__.py \
        apps/api/src/augura_api/main.py apps/api/tests/test_app_routes.py
git commit -m "feat(semantic): mount GET /semantic/concepts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: integration test (DB + RLS)

**Files:** `apps/api/tests/integration/test_semantic_repo.py`

- [ ] **Step 1: Write the integration test**

`apps/api/tests/integration/test_semantic_repo.py`:
```python
"""Integration of the semantic module — global taxonomy + read-only RLS.

Skipped if AUGURA_DATABASE_URL is absent. CI: after seed, under the augura_app role.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId
from augura_api.modules.semantic.repo import SemanticRepo

pytestmark = pytest.mark.integration

USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("AUGURA_DATABASE_URL")
    if not url:
        pytest.skip("AUGURA_DATABASE_URL absent — integration test skipped")
    engine = create_async_engine(to_asyncpg_url(url))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _scope(session: AsyncSession, tenant: TenantId, user: UserId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(user))
    await session.execute(set_tenant_stmt(tenant))


async def test_taxonomy_readable_and_seeded(sm: async_sessionmaker[AsyncSession]) -> None:
    tenant = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        repo = SemanticRepo(session)
        concepts = await repo.list_concepts()
        archetypes = await repo.list_archetypes()
        constraints = await repo.list_constraints()
    assert len(concepts) > 100          # ~171 seeded
    assert all(c.active for c in concepts)
    assert [c.local_concept_id for c in concepts] == sorted(c.local_concept_id for c in concepts)
    assert len(archetypes) >= 1
    assert len(constraints) >= 1


async def test_taxonomy_is_read_only_for_tenant(sm: async_sessionmaker[AsyncSession]) -> None:
    tenant = TenantId(uuid4())
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with sm() as session, session.begin():
            await _scope(session, tenant, USER)
            await session.execute(
                text(
                    "insert into taxonomy_concepts "
                    "(local_concept_id, layer, concept_name, augura_domain, review_status, version, active) "
                    "values (:i, 1, 'x', 'd', 'r', 'v', true)"
                ).bindparams(i="rogue-" + uuid4().hex[:6])
            )
```

- [ ] **Step 2: Run locally — expect SKIPPED** (no DB). `cd apps/api && uv run pytest tests/integration/test_semantic_repo.py -q` → skipped.

- [ ] **Step 3: Commit**
```bash
git add apps/api/tests/integration/test_semantic_repo.py
git commit -m "test(semantic): A1 integration — taxonomy readable, RLS read-only

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: regenerate api-client (clean worktree)

**Files:** `packages/api-client/{openapi.json,src/schema.d.ts}`

- [ ] **Step 1: Generate the contract from a clean worktree at HEAD** (avoids capturing any unrelated working-tree WIP):
```bash
cd /Users/quentin/Desktop/Augure/augura-platform
git worktree add --detach /tmp/augura-a1-clean HEAD
( cd /tmp/augura-a1-clean/apps/api && uv sync --dev >/dev/null 2>&1 \
  && AUGURA_ENV=dev uv run python scripts/dump_openapi.py ) > packages/api-client/openapi.json
( cd packages/api-client && npm install --no-audit --no-fund >/dev/null 2>&1 && npm run generate )
git worktree remove --force /tmp/augura-a1-clean
```

- [ ] **Step 2: Verify diff is ONLY `/semantic/concepts` + `ConceptOut`**
```bash
git show HEAD:packages/api-client/openapi.json > /tmp/oa_head.json
python3 - <<'PY'
import json
h=json.load(open('/tmp/oa_head.json')); n=json.load(open('packages/api-client/openapi.json'))
print("ADDED paths:", sorted(set(n['paths'])-set(h['paths'])))
print("ADDED schemas:", sorted(set(n.get('components',{}).get('schemas',{}))-set(h.get('components',{}).get('schemas',{}))))
PY
```
Expected: ADDED paths `['/semantic/concepts']`; ADDED schemas `['ConceptOut']`. Then `( cd packages/api-client && npx tsc --noEmit )` → clean.

- [ ] **Step 3: Commit**
```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate contract for /semantic/concepts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: full verification + real-DB validation

- [ ] **Step 1: Static gates** (from `apps/api/`): `uv run ruff format --check .` (only your files must be clean — pre-existing WIP format drift is not yours), `uv run ruff check .`, `uv run pyright`, `uv run lint-imports`, `uv run pytest -q` (expect baseline +5 passed [3 generator/service unit-ish + 2 bundle] and +2 skipped [integration], no failures).

- [ ] **Step 2: Real-DB validation** (mirrors D's proven validation). Start a pgvector container, apply the bundle via asyncpg as superuser (schema→functions→policies→seed), run the semantic integration tests, and an RLS smoke:
```bash
docker run -d --name augura-a1-validate -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=augura -p 5433:5432 pgvector/pgvector:pg16
# wait for pg_isready, then:
cd apps/api
export AUGURA_ENV=dev AUGURA_DATABASE_URL="postgresql://postgres:postgres@localhost:5433/augura"
uv run python - <<'PY'
import asyncio, asyncpg, os
url=os.environ["AUGURA_DATABASE_URL"]
strip=lambda s:"\n".join(l for l in s.splitlines() if l.strip().lower() not in("begin;","commit;"))
async def main():
    c=await asyncpg.connect(url, statement_cache_size=0)
    for f in ("schema.sql","functions.sql","policies.sql","seed.sql"):
        await c.execute(strip(open(f"supabase/{f}",encoding="utf-8").read()))
    for t in ("taxonomy_concepts","taxonomy_synonyms","dq_constraints","table_archetypes"):
        print(t, await c.fetchval(f"select count(*) from {t}"))
    await c.close()
asyncio.run(main())
PY
uv run pytest tests/integration/test_semantic_repo.py -q
docker rm -f augura-a1-validate
```
Expected: counts (~171 / ~1372 / 32 / 8), integration tests PASS.

- [ ] **Step 3: Confirm contract not drifted** — already validated via the clean worktree in Task 6 (do NOT re-dump from the working tree if it carries WIP).

---

## Self-Review (completed during planning)

- **Spec coverage:** 7 tables (T1), RLS read-only (T1, validated T7), seed generator + seed (T2), module models/repo/service for all 7 + read endpoint for concepts (T3/T4), tests at every layer (T1–T5), api-client (T6), real-DB validation (T7). All spec sections mapped.
- **Placeholder scan:** none — DDL, generator, module, and tests are complete.
- **Type consistency:** `SemanticService(repo)` ⇄ `_ConceptReader` ⇄ `SemanticRepo.list_concepts(domain=, active=)`; `ConceptOut` fields ⊆ `TaxonomyConcept` columns; model `offset` mapped to column `"offset"`; route prefix `/semantic` consistent across router/main/tests/regen check.
- **Reserved word:** `unit_conversions."offset"` quoted in DDL and mapped via `mapped_column("offset", Numeric)`; generator quotes all column identifiers, so `offset`/`precision` are safe.
