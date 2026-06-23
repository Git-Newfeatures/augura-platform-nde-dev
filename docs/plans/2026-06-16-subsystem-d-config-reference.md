# Subsystem D — Config / Reference endpoints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve tenant CESL profile + the `cesl-sources` and `study-designs` reference catalogs from the FastAPI backend, back them with seeded RLS-protected tables, and rewire `LucisApp.jsx` off the dead `/api/*` fetches onto the api-client.

**Architecture:** New vertical-slice backend module `reference` (`router/service/repo/models/schemas`), mounted in `main.py`. Two global reference tables added to the canonical SQL bundle (`supabase/schema.sql` + `policies.sql` + `seed.sql`); the alembic baseline executes the bundle so `alembic upgrade head` builds them. Frontend reads via the existing `apiJson` helper. Tenant is resolved from the JWT (no slug param).

**Tech Stack:** FastAPI, SQLAlchemy (async), Pydantic v2, Postgres + RLS, pytest/pytest-asyncio, ruff/pyright/import-linter, openapi-typescript, React.

**Spec:** `docs/specs/2026-06-16-subsystem-d-config-reference-design.md`

**Conventions discovered (do not deviate):**
- Module layout mirrors `apps/api/src/augura_api/modules/studies/` exactly.
- `supabase/*.sql` is the single source of truth; `alembic/versions/0001_baseline.py` runs `schema.sql`+`functions.sql`+`policies.sql`. `seed.sql` is applied separately (`psql -f`, as superuser in CI → bypasses RLS).
- Reference tables are **global** (no `org_id`), read-only for tenant sessions: RLS policy is `for select` only (a `for all`/`using` policy would let INSERT pass because WITH CHECK defaults to USING).
- Lint/test commands run from `apps/api/`: `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright`, `uv run lint-imports`, `uv run pytest -q`. Integration tests need `AUGURA_DATABASE_URL` (skip otherwise) and are also run with `-m integration`.
- api-client regen: `uv run --directory apps/api python scripts/dump_openapi.py > packages/api-client/openapi.json` then `( cd packages/api-client && npm run generate )`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `apps/api/supabase/schema.sql` (modify) | Add `cesl_sources`, `cesl_study_designs` tables |
| `apps/api/supabase/policies.sql` (modify) | Enable RLS (`for select` read gate) on the two tables |
| `apps/api/supabase/seed.sql` (modify) | Seed the reconstructed catalog rows |
| `apps/api/tests/db/test_supabase_bundle.py` (modify) | Add tables to `EXPECTED_TABLES`; assert seed + RLS |
| `apps/api/src/augura_api/modules/reference/__init__.py` (create) | Public interface — exports `router` |
| `apps/api/src/augura_api/modules/reference/models.py` (create) | ORM: `Org`, `CeslSource`, `CeslStudyDesign` |
| `apps/api/src/augura_api/modules/reference/schemas.py` (create) | Pydantic: `TenantProfileOut`, `CeslSourceOut`, `StudyDesignOut` |
| `apps/api/src/augura_api/modules/reference/repo.py` (create) | DB access: `get_org`, `list_cesl_sources`, `list_study_designs` |
| `apps/api/src/augura_api/modules/reference/service.py` (create) | `ReferenceService` — maps ORM → schema, 404 on missing org |
| `apps/api/src/augura_api/modules/reference/router.py` (create) | HTTP adapter — 3 GET routes |
| `apps/api/src/augura_api/main.py` (modify) | Mount `reference_router` |
| `apps/api/tests/test_reference_service.py` (create) | Unit: service mapping + NotFound (fake repo, no DB) |
| `apps/api/tests/test_app_routes.py` (modify) | Assert `/reference/*` in OpenAPI + 401 |
| `apps/api/tests/integration/test_reference_repo.py` (create) | DB+RLS: read catalogs, tenant org, write-denied |
| `packages/api-client/openapi.json` + `src/schema.d.ts` (regen) | Generated contract + client |
| `apps/web/src/LucisApp.jsx` (modify) | Rewire 3 config fetches onto `apiJson` |

---

## Task 1: DB bundle — reference tables, RLS, seed

**Files:**
- Modify: `apps/api/supabase/schema.sql`
- Modify: `apps/api/supabase/policies.sql`
- Modify: `apps/api/supabase/seed.sql`
- Test: `apps/api/tests/db/test_supabase_bundle.py`

- [ ] **Step 1: Update the bundle test first (it pins the schema — will fail until schema.sql matches)**

In `apps/api/tests/db/test_supabase_bundle.py`, add the two tables to `EXPECTED_TABLES` (the set is asserted for exact equality):

```python
EXPECTED_TABLES = {
    "orgs",
    "memberships",
    "studies",
    "study_members",
    "study_state",
    "datasets",
    "dataset_columns",
    "cohort_members",
    "cohort_biomarkers",
    "documents",
    "chunks",
    "agent_runs",
    "agent_cache",
    "simulation_runs",
    "simulation_results",
    "jobs",
    "generated_documents",
    "usage_events",
    "outbox_events",
    "artifacts",
    "cesl_sources",
    "cesl_study_designs",
}
```

Then add two new tests at the end of the file:

```python
def test_seed_includes_cesl_reference_catalogs() -> None:
    seed = _read("seed.sql").lower()
    assert "insert into cesl_sources" in seed
    assert "insert into cesl_study_designs" in seed


def test_reference_tables_have_select_only_rls() -> None:
    policies = _read("policies.sql")
    for t in ("cesl_sources", "cesl_study_designs"):
        assert f"alter table {t} enable row level security" in policies
        assert f"create policy backend_read on {t}" in policies
    # Read-only: the reference policy is FOR SELECT (no tenant write).
    assert "for select" in policies
```

- [ ] **Step 2: Run the bundle tests — verify they fail**

Run: `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py -q`
Expected: FAIL — `test_schema_declares_every_expected_table` (missing `cesl_sources`, `cesl_study_designs`), plus the two new tests fail.

- [ ] **Step 3: Add the tables to `schema.sql`**

Append to `apps/api/supabase/schema.sql` (after the `artifacts` table, before any trailing `commit;` if present — match the file's existing transaction structure):

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- Module: reference — global CESL catalogs (not tenant-scoped, read-only)
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists cesl_sources (
    code        text primary key,
    label       text not null,
    doc_type    text,
    description text,
    base_url    text,
    result_unit text,
    sort_order  int     not null default 0,
    active      boolean not null default true
);

create table if not exists cesl_study_designs (
    code       text primary key,
    label      text not null,
    group_name text,
    sort_order int     not null default 0,
    active     boolean not null default true
);
```

- [ ] **Step 4: Add RLS to `policies.sql`**

In `apps/api/supabase/policies.sql`, **before** the final `commit;`, add a dedicated read-only gate (mirrors the infra `backend_session` loop but `for select` only):

```sql
-- ── Reference catalogs (cesl_sources, cesl_study_designs) ─────────────────
-- Global, read-only for tenant sessions. RLS enabled + "backend session" gate
-- in READ only (FOR SELECT): anon/PostgREST denied, backend
-- (app.tenant_id set) allowed to read. No write policy ⇒ INSERT/
-- UPDATE/DELETE denied for augura_app; the seed enters via the privileged role.
do $$
declare
    t text;
begin
    foreach t in array array['cesl_sources', 'cesl_study_designs']
    loop
        execute format('alter table %I enable row level security;', t);
        execute format('alter table %I force row level security;', t);
        execute format($f$
            create policy backend_read on %I
            for select
            using (nullif(current_setting('app.tenant_id', true), '') is not null);
        $f$, t);
    end loop;
end
$$;
```

- [ ] **Step 5: Seed the catalogs in `seed.sql`**

Append to `apps/api/supabase/seed.sql` (idempotent via `on conflict do nothing`):

```sql
-- ─────────────────────────────────────────────────────────────────────────
-- CESL reference catalogs (config, not demo data).
-- Reconstructed from the MVP constants (4 sources of the E1 agent + designs).
-- To be replaced by the authoritative Supabase export if access to the MVP project is provided.
-- ─────────────────────────────────────────────────────────────────────────

insert into cesl_sources (code, label, doc_type, description, base_url, result_unit, sort_order, active) values
  ('pubmed',         'PubMed',            'study',         'Peer-reviewed biomedical literature (NCBI PubMed).',                'https://pubmed.ncbi.nlm.nih.gov/',                                            'studies',   10, true),
  ('clinicaltrials', 'ClinicalTrials.gov','trial',         'Registered interventional and observational clinical trials.',      'https://clinicaltrials.gov/',                                                 'trials',    20, true),
  ('maude',          'MAUDE',             'adverse_event', 'FDA Manufacturer and User Facility Device Experience adverse events.','https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfMAUDE/search.cfm',       'events',    30, true),
  ('guidance',       'FDA Guidance',      'guidance',      'FDA regulatory guidance documents.',                                'https://www.fda.gov/regulatory-information/search-fda-guidance-documents',     'documents', 40, true)
on conflict (code) do nothing;

insert into cesl_study_designs (code, label, group_name, sort_order, active) values
  ('retro_cohort',     'Retrospective cohort',     'observational', 10, true),
  ('pre_post',         'Pre/post',                 'observational', 20, true),
  ('external_matched', 'External matched control', 'observational', 30, true),
  ('mediation',        'Causal mediation',         'mechanistic',   40, true),
  ('prospective',      'Prospective cohort',       'prospective',   50, true)
on conflict (code) do nothing;
```

- [ ] **Step 6: Run the bundle tests — verify they pass**

Run: `cd apps/api && uv run pytest tests/db/test_supabase_bundle.py -q`
Expected: PASS (all bundle tests, including the two new ones).

- [ ] **Step 7: Commit**

```bash
git add apps/api/supabase/schema.sql apps/api/supabase/policies.sql apps/api/supabase/seed.sql apps/api/tests/db/test_supabase_bundle.py
git commit -m "feat(reference): cesl_sources + cesl_study_designs tables, RLS, seed

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: reference module — models, schemas, repo, service

**Files:**
- Create: `apps/api/src/augura_api/modules/reference/__init__.py`
- Create: `apps/api/src/augura_api/modules/reference/models.py`
- Create: `apps/api/src/augura_api/modules/reference/schemas.py`
- Create: `apps/api/src/augura_api/modules/reference/repo.py`
- Create: `apps/api/src/augura_api/modules/reference/service.py`
- Test: `apps/api/tests/test_reference_service.py`

- [ ] **Step 1: Write the failing service unit test**

Create `apps/api/tests/test_reference_service.py`:

```python
"""Unit tests for the reference service — ORM→schema mapping without a database (fake repo)."""

from uuid import UUID

import pytest

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.reference.models import CeslSource, CeslStudyDesign, Org
from augura_api.modules.reference.service import ReferenceService

TENANT = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


def _tenant() -> CurrentTenant:
    return CurrentTenant(tenant_id=TENANT, user_id=USER, role="owner")


class _FakeRepo:
    def __init__(self, org: Org | None) -> None:
        self._org = org

    async def get_org(self, tenant_id: TenantId) -> Org | None:
        return self._org

    async def list_cesl_sources(self) -> list[CeslSource]:
        return [CeslSource(code="pubmed", label="PubMed", sort_order=10, active=True)]

    async def list_study_designs(self) -> list[CeslStudyDesign]:
        return [CeslStudyDesign(code="retro_cohort", label="Retrospective cohort", sort_order=10, active=True)]


async def test_tenant_profile_maps_org() -> None:
    org = Org(id=TENANT, name="Lucis", slug="lucis", cesl_profile={"clinical_domain": ["cardiometabolic"]})
    svc = ReferenceService(_FakeRepo(org))  # type: ignore[arg-type]
    out = await svc.tenant_profile(_tenant())
    assert out.slug == "lucis"
    assert out.cesl_profile == {"clinical_domain": ["cardiometabolic"]}


async def test_tenant_profile_missing_org_raises_404() -> None:
    svc = ReferenceService(_FakeRepo(None))  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await svc.tenant_profile(_tenant())


async def test_cesl_sources_and_designs_map() -> None:
    org = Org(id=TENANT, name="Lucis", slug="lucis", cesl_profile={})
    svc = ReferenceService(_FakeRepo(org))  # type: ignore[arg-type]
    sources = await svc.cesl_sources()
    designs = await svc.study_designs()
    assert sources[0].code == "pubmed"
    assert designs[0].label == "Retrospective cohort"
```

- [ ] **Step 2: Run it — verify it fails (import errors)**

Run: `cd apps/api && uv run pytest tests/test_reference_service.py -q`
Expected: FAIL — `ModuleNotFoundError: augura_api.modules.reference`.

- [ ] **Step 3: Create the package `__init__.py` (placeholder — router export added in Task 3)**

Create `apps/api/src/augura_api/modules/reference/__init__.py`:

```python
"""reference module — tenant profile + CESL catalogs (read-only)."""
```

- [ ] **Step 4: Create `models.py`**

Create `apps/api/src/augura_api/modules/reference/models.py`:

```python
"""SQLAlchemy models for the reference module (DDL created by the SQL bundle)."""

from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from augura_api.core.db import Base


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text)
    cesl_profile: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )


class CeslSource(Base):
    __tablename__ = "cesl_sources"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    result_unit: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class CeslStudyDesign(Base):
    __tablename__ = "cesl_study_designs"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    group_name: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
```

- [ ] **Step 5: Create `schemas.py`**

Create `apps/api/src/augura_api/modules/reference/schemas.py`:

```python
"""Pydantic schemas — public contract of the reference module."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TenantProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    cesl_profile: dict[str, Any]


class CeslSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    doc_type: str | None = None
    description: str | None = None
    base_url: str | None = None
    result_unit: str | None = None
    sort_order: int


class StudyDesignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    group_name: str | None = None
    sort_order: int
```

- [ ] **Step 6: Create `repo.py`**

Create `apps/api/src/augura_api/modules/reference/repo.py`:

```python
"""Database access for the reference module.

`orgs` is read scoped to the current tenant (the `tenant_self` RLS exposes only
its row; the explicit filter is defense in depth). The CESL catalogs
are global (read-only, "backend FOR SELECT" RLS).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.reference.models import CeslSource, CeslStudyDesign, Org


class ReferenceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_org(self, tenant_id: TenantId) -> Org | None:
        res = await self.session.execute(select(Org).where(Org.id == tenant_id))
        return res.scalar_one_or_none()

    async def list_cesl_sources(self) -> list[CeslSource]:
        res = await self.session.execute(
            select(CeslSource).where(CeslSource.active.is_(True)).order_by(CeslSource.sort_order)
        )
        return list(res.scalars().all())

    async def list_study_designs(self) -> list[CeslStudyDesign]:
        res = await self.session.execute(
            select(CeslStudyDesign)
            .where(CeslStudyDesign.active.is_(True))
            .order_by(CeslStudyDesign.sort_order)
        )
        return list(res.scalars().all())
```

- [ ] **Step 7: Create `service.py`**

Create `apps/api/src/augura_api/modules/reference/service.py`:

```python
"""Business logic for the reference module. The router is a thin adapter."""

from typing import Protocol

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.reference import schemas
from augura_api.modules.reference.models import CeslSource, CeslStudyDesign, Org


class _RefReader(Protocol):
    async def get_org(self, tenant_id: TenantId) -> Org | None: ...
    async def list_cesl_sources(self) -> list[CeslSource]: ...
    async def list_study_designs(self) -> list[CeslStudyDesign]: ...


class ReferenceService:
    def __init__(self, repo: _RefReader) -> None:
        self.repo = repo

    async def tenant_profile(self, tenant: CurrentTenant) -> schemas.TenantProfileOut:
        org = await self.repo.get_org(tenant.tenant_id)
        if org is None:
            raise NotFoundError("organization not found", tenant_id=str(tenant.tenant_id))
        return schemas.TenantProfileOut.model_validate(org)

    async def cesl_sources(self) -> list[schemas.CeslSourceOut]:
        rows = await self.repo.list_cesl_sources()
        return [schemas.CeslSourceOut.model_validate(r) for r in rows]

    async def study_designs(self) -> list[schemas.StudyDesignOut]:
        rows = await self.repo.list_study_designs()
        return [schemas.StudyDesignOut.model_validate(r) for r in rows]
```

- [ ] **Step 8: Run the unit test — verify it passes**

Run: `cd apps/api && uv run pytest tests/test_reference_service.py -q`
Expected: PASS (3 tests).

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/augura_api/modules/reference/__init__.py \
        apps/api/src/augura_api/modules/reference/models.py \
        apps/api/src/augura_api/modules/reference/schemas.py \
        apps/api/src/augura_api/modules/reference/repo.py \
        apps/api/src/augura_api/modules/reference/service.py \
        apps/api/tests/test_reference_service.py
git commit -m "feat(reference): models, schemas, repo, service

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: router + app mount + route tests

**Files:**
- Create: `apps/api/src/augura_api/modules/reference/router.py`
- Modify: `apps/api/src/augura_api/modules/reference/__init__.py`
- Modify: `apps/api/src/augura_api/main.py`
- Test: `apps/api/tests/test_app_routes.py`

- [ ] **Step 1: Extend the route tests first**

In `apps/api/tests/test_app_routes.py`, add the three paths to the `for path in (...)` tuple in `test_openapi_exposes_routes` (after `/analytics/admin`):

```python
        "/reference/tenant",
        "/reference/cesl-sources",
        "/reference/study-designs",
```

And add `/reference/tenant` to the `for path in (...)` tuple in `test_protected_routes_require_auth`:

```python
        for path in ("/studies", "/corpus/feed", "/datasets", "/datasets/cohorts", "/reference/tenant"):
```

- [ ] **Step 2: Run the route tests — verify they fail**

Run: `cd apps/api && uv run pytest tests/test_app_routes.py -q`
Expected: FAIL — `/reference/tenant` etc. not in `paths`; the new auth path returns 404 not 401.

- [ ] **Step 3: Create `router.py`**

Create `apps/api/src/augura_api/modules/reference/router.py`:

```python
"""HTTP adapter for the reference module (single FastAPI gateway)."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.reference import schemas
from augura_api.modules.reference.repo import ReferenceRepo
from augura_api.modules.reference.service import ReferenceService

router = APIRouter(prefix="/reference", tags=["reference"])


def _service(session: SessionDep) -> ReferenceService:
    return ReferenceService(ReferenceRepo(session))


@router.get("/tenant", response_model=schemas.TenantProfileOut)
async def tenant(
    tenant: CurrentTenantDep, session: SessionDep
) -> schemas.TenantProfileOut:
    return await _service(session).tenant_profile(tenant)


@router.get("/cesl-sources", response_model=list[schemas.CeslSourceOut])
async def cesl_sources(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CeslSourceOut]:
    return await _service(session).cesl_sources()


@router.get("/study-designs", response_model=list[schemas.StudyDesignOut])
async def study_designs(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.StudyDesignOut]:
    return await _service(session).study_designs()
```

- [ ] **Step 4: Export the router from `__init__.py`**

Replace `apps/api/src/augura_api/modules/reference/__init__.py` with:

```python
"""Public interface of the reference module — other modules import only this."""

from augura_api.modules.reference.router import router

__all__ = ["router"]
```

- [ ] **Step 5: Mount the router in `main.py`**

In `apps/api/src/augura_api/main.py`, add the import (alphabetical, after `jobs`):

```python
from augura_api.modules.jobs import router as jobs_router
from augura_api.modules.reference import router as reference_router
from augura_api.modules.simulation import router as simulation_router
```

And add the mount (after `analytics_router`):

```python
    app.include_router(analytics_router)
    app.include_router(reference_router)
```

- [ ] **Step 6: Run the route tests — verify they pass**

Run: `cd apps/api && uv run pytest tests/test_app_routes.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/augura_api/modules/reference/router.py \
        apps/api/src/augura_api/modules/reference/__init__.py \
        apps/api/src/augura_api/main.py \
        apps/api/tests/test_app_routes.py
git commit -m "feat(reference): mount /reference/{tenant,cesl-sources,study-designs}

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: integration test — DB + RLS

**Files:**
- Test: `apps/api/tests/integration/test_reference_repo.py`

- [ ] **Step 1: Write the integration test**

Create `apps/api/tests/integration/test_reference_repo.py`:

```python
"""Integration tests for the reference module — global catalogs + tenant org + RLS.

Skipped if AUGURA_DATABASE_URL is absent. In CI, they run after the seed, under the
augura_app role (NOT exempt from RLS).
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
from augura_api.modules.reference.repo import ReferenceRepo

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


async def test_reference_catalogs_are_readable_and_ordered(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    tenant = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        repo = ReferenceRepo(session)
        sources = await repo.list_cesl_sources()
        designs = await repo.list_study_designs()

    assert {s.code for s in sources} >= {"pubmed", "clinicaltrials", "maude", "guidance"}
    assert all(s.active for s in sources)
    assert [s.sort_order for s in sources] == sorted(s.sort_order for s in sources)
    assert {d.code for d in designs} >= {"retro_cohort", "mediation"}
    assert [d.sort_order for d in designs] == sorted(d.sort_order for d in designs)


async def test_tenant_reads_only_its_own_org(sm: async_sessionmaker[AsyncSession]) -> None:
    tenant = TenantId(uuid4())
    # INSERT of the org scoped to the current tenant: the orgs `tenant_self` policy
    # (using id = app.tenant_id, default WITH CHECK = USING) allows this row.
    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        await session.execute(
            text(
                "insert into orgs (id, name, slug, cesl_profile) "
                "values (cast(:id as uuid), :n, :s, cast(:p as jsonb))"
            ).bindparams(id=str(tenant), n="IT Org", s="it-" + uuid4().hex[:8], p='{"clinical_domain": ["x"]}')
        )

    async with sm() as session, session.begin():
        await _scope(session, tenant, USER)
        org = await ReferenceRepo(session).get_org(tenant)
        assert org is not None
        assert org.cesl_profile == {"clinical_domain": ["x"]}

    other = TenantId(uuid4())
    async with sm() as session, session.begin():
        await _scope(session, other, USER)
        assert await ReferenceRepo(session).get_org(tenant) is None  # RLS isolates


async def test_reference_tables_are_read_only_for_tenant(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    tenant = TenantId(uuid4())
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with sm() as session, session.begin():
            await _scope(session, tenant, USER)
            await session.execute(
                text(
                    "insert into cesl_sources (code, label) values (:c, :l)"
                ).bindparams(c="rogue-" + uuid4().hex[:6], l="nope")
            )
```

- [ ] **Step 2: Run it locally (expected: skipped without DB)**

Run: `cd apps/api && uv run pytest tests/integration/test_reference_repo.py -q`
Expected: SKIPPED (no `AUGURA_DATABASE_URL`) — this is correct locally; CI runs it against ephemeral Postgres with `-m integration`.

> If you have a disposable Supabase branch, set `AUGURA_DATABASE_URL` to it (never the demo project — the `_forbid_demo_db` guard fails the run) and re-run to see PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/integration/test_reference_repo.py
git commit -m "test(reference): integration — catalogs, tenant org, RLS read-only

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: regenerate OpenAPI contract + api-client

**Files:**
- Regen: `packages/api-client/openapi.json`
- Regen: `packages/api-client/src/schema.d.ts`

- [ ] **Step 1: Regenerate the contract and client**

Run (from repo root):

```bash
uv run --directory apps/api python scripts/dump_openapi.py > packages/api-client/openapi.json
( cd packages/api-client && npm install --no-audit --no-fund && npm run generate )
```

- [ ] **Step 2: Verify the new paths landed in the contract**

Run: `grep -E "/reference/(tenant|cesl-sources|study-designs)" packages/api-client/openapi.json`
Expected: all three paths present.

- [ ] **Step 3: Typecheck the client (matches CI `client-drift` job)**

Run: `cd packages/api-client && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "chore(api-client): regenerate contract for /reference/*

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: frontend — rewire LucisApp onto the api-client

**Files:**
- Modify: `apps/web/src/LucisApp.jsx`

- [ ] **Step 1: Add the `apiJson` import**

In `apps/web/src/LucisApp.jsx`, after line 21 (`import SimulationEngine from "./SimulationEngine";`), add:

```jsx
import { apiJson } from "./api";
```

- [ ] **Step 2: Replace the three config-fetch effects (current lines 117–145)**

Replace this block:

```jsx
  // ── Tenant CESL profile — fetched server-side to avoid RLS on anon reads ─────
  const [tenantProfile, setTenantProfile] = useState(null);
  useEffect(() => {
    if (!projectId) return;
    fetch(`/api/tenant?projectId=${encodeURIComponent(projectId)}`)
      .then(r => (r.ok ? r.json().catch(() => null) : null))
      .then(data => { if (data) setTenantProfile(data); })
      .catch(() => {});
  }, [projectId]);

  const [studyDesigns, setStudyDesigns] = useState({}); // { code: label }
  useEffect(() => {
    fetch('/api/study-designs')
      .then(r => (r.ok ? r.json().catch(() => []) : []))
      .then(data => {
        const map = {};
        (Array.isArray(data) ? data : []).forEach(d => { map[d.code] = d.label; });
        setStudyDesigns(map);
      })
      .catch(() => {});
  }, []);

  const [agentSources, setAgentSources] = useState([]); // [{ code, label, doc_type, ... }]
  useEffect(() => {
    fetch('/api/cesl-sources')
      .then(r => (r.ok ? r.json().catch(() => []) : []))
      .then(data => setAgentSources(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);
```

with:

```jsx
  // ── Tenant CESL profile — served by the backend (/reference/tenant, JWT-scoped).
  // No projectId param: the server resolves the tenant from the auth token.
  const [tenantProfile, setTenantProfile] = useState(null);
  useEffect(() => {
    apiJson('/reference/tenant')
      .then(data => { if (data) setTenantProfile(data); })
      .catch(() => {});
  }, []);

  const [studyDesigns, setStudyDesigns] = useState({}); // { code: label }
  useEffect(() => {
    apiJson('/reference/study-designs')
      .then(data => {
        const map = {};
        (Array.isArray(data) ? data : []).forEach(d => { map[d.code] = d.label; });
        setStudyDesigns(map);
      })
      .catch(() => {});
  }, []);

  const [agentSources, setAgentSources] = useState([]); // [{ code, label, doc_type, ... }]
  useEffect(() => {
    apiJson('/reference/cesl-sources')
      .then(data => setAgentSources(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);
```

- [ ] **Step 3: Confirm no dead `/api/` config calls remain**

Run: `grep -nE "/api/(tenant|study-designs|cesl-sources)" apps/web/src/LucisApp.jsx`
Expected: no matches.

- [ ] **Step 4: Build the web app to catch compile errors**

Run: `cd apps/web && npm run build`
Expected: build succeeds. (If unrelated errors from in-progress branch work appear, confirm they are not in `LucisApp.jsx` and not caused by this edit, then proceed.)

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/LucisApp.jsx
git commit -m "feat(web): load tenant/study-designs/cesl-sources via api-client

Replaces dead fetch('/api/*') calls; drops study-id-as-projectId bug.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend lint + types + import contracts + unit tests**

Run (from `apps/api/`):

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run lint-imports
uv run pytest -q
```

Expected: all green. `pytest -q` runs unit + route tests and **skips** integration (no DB) — confirm reference unit/route tests pass and integration tests show as skipped, not failed.

- [ ] **Step 2: Confirm the OpenAPI contract is not drifted**

Run (from repo root):

```bash
uv run --directory apps/api python scripts/dump_openapi.py > packages/api-client/openapi.json
( cd packages/api-client && npm run generate )
git diff --exit-code packages/api-client/openapi.json packages/api-client/src/schema.d.ts
```

Expected: no diff (already committed in Task 5).

- [ ] **Step 3: Final state check**

Run: `git status` and `git log --oneline -7`
Expected: clean tree; the Task 1–6 commits present.

---

## Self-Review (completed during planning)

- **Spec coverage:** tenant endpoint (T2/T3), cesl-sources (T2/T3), study-designs (T2/T3), tables (T1), RLS read-only (T1, verified T4), seed in bundle (T1), frontend rewire + bug fix (T6), api-client regen + drift (T5/T7), tests at every layer (T1–T4). All spec sections mapped.
- **Placeholder scan:** none — every code/SQL step is complete.
- **Type consistency:** `ReferenceService(repo)` ⇄ `_RefReader` protocol ⇄ `ReferenceRepo` (methods `get_org`/`list_cesl_sources`/`list_study_designs`); schema names (`TenantProfileOut`/`CeslSourceOut`/`StudyDesignOut`) consistent across schemas, service, router, tests; route prefix `/reference` consistent across router, main mount, route tests, regen check, and frontend paths.
- **RLS subtlety captured:** reference policy is `for select` (not `for all`) so tenant sessions cannot write — verified by `test_reference_tables_are_read_only_for_tenant`.
