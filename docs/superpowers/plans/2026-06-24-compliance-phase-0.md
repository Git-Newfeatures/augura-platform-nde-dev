# Compliance Hardening — Phase 0 ("Stop the Bleeding") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the highest-risk, lowest-effort HIPAA/GDPR/SOC 2 gaps on the existing stack — make the audit trail tamper-resistant and attributable, stop PHI reaching LLMs, force verified TLS, harden auth/error/storage posture, and add baseline change-management controls — with zero language change and no data migration.

**Architecture:** Backend = FastAPI modular monolith (`apps/api`, `uv`, pyright strict), DB = Supabase Postgres with forced RLS under the non-BYPASSRLS `augura_app` role (bundle in `apps/api/supabase/*`). Frontend = React/Vite (`apps/web`). Changes are SQL-policy, config-validator, middleware, prompt-construction, and CI/IaC edits. Each task is TDD where testable.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy async · asyncpg · Pydantic v2 / pydantic-settings · pytest (`-m integration` for DB tests) · Alembic · Postgres 16 + pgvector · React 19 · GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-06-24-compliance-hardening-design.md](../specs/2026-06-24-compliance-hardening-design.md)

---

## Conventions for this plan

- **Run all backend commands from `apps/api`** unless stated otherwise. The local env is not auto-loaded — for any command needing the DB/keys run `set -a; . ./.env; set +a` first (integration tests skip cleanly without `AUGURA_DATABASE_URL`).
- **CI must stay green** after every task: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`. Frontend tasks also run `npm run lint && npm run build` from `apps/web`.
- **Comments/docstrings/code in English** (project convention).
- **Commits happen only on explicit user request** (`CLAUDE.md`). The commit steps below define the logical units; the executing skill commits when the user asks. Commit messages carry **no AI-attribution trailer**.
- **DB bundle invariant:** `apps/api/supabase/policies.sql` is the canonical source applied to fresh DBs and CI by `alembic 0001`. An already-migrated prod DB does **not** re-run it, so policy/grant changes ALSO ship as an idempotent `00NN` migration. The Modal deploy runs neither migrations nor seed → the migration is applied to prod separately (via `alembic upgrade head` against the live DB or the Supabase MCP `execute_sql`). Tasks 1 and 11 carry an explicit prod-apply step.

---

## Task 1: Make the audit trail append-only (`usage_events`, `outbox_events`)

Closes the two **critical** findings that the audit trail is *mutable* (the app role can `UPDATE`/`DELETE` its own audit rows via the `FOR ALL` policies) and that the frontend can forge rows (`grant insert on usage_events to authenticated`). After this task, `augura_app` may read + insert audit rows, never modify or delete them; `authenticated` (PostgREST) can no longer insert. `agent_cache` keeps read/write (it is a cache, not an audit log).

**Files:**
- Modify: `apps/api/supabase/policies.sql:44-69` (remove the `authenticated` insert grant) and `:186-219` (append-only policies)
- Create: `apps/api/alembic/versions/00NN_audit_append_only.py`
- Modify: `apps/api/tests/db/test_supabase_bundle.py` (structural guards)
- Create: `apps/api/tests/integration/test_audit_append_only.py` (runtime proof under `augura_app`)

- [ ] **Step 1: Write the structural guard tests (failing)**

Append to `apps/api/tests/db/test_supabase_bundle.py`:

```python
def test_usage_events_is_append_only() -> None:
    """The login-event forgery vector (authenticated INSERT) is removed and the app
    role cannot UPDATE/DELETE audit rows (Part 11 / HIPAA 164.312(b))."""
    policies = _read("policies.sql").lower()
    assert "grant insert on usage_events to authenticated" not in policies
    assert "create policy usage_events_insert on usage_events" in policies
    assert re.search(r"revoke[^;]*update[^;]*on usage_events from augura_app", policies, re.S)


def test_outbox_events_is_append_only() -> None:
    policies = _read("policies.sql").lower()
    assert "create policy outbox_events_insert on outbox_events" in policies
    assert re.search(r"revoke[^;]*on outbox_events from augura_app", policies, re.S)
```

- [ ] **Step 2: Run the guards to verify they fail**

Run: `uv run pytest tests/db/test_supabase_bundle.py -k append_only -q`
Expected: 2 FAILED (grant still present / insert policy absent).

- [ ] **Step 3: Remove the forgeable `authenticated` insert grant**

In `apps/api/supabase/policies.sql`, delete line 63 inside the lockdown `do $$` block:

```sql
        grant insert on usage_events to authenticated;
```

and update the comment just above the block (lines 46-48) to drop the "re-grant the only legitimate direct write" sentence, replacing it with:

```sql
-- Lockdown of the default Supabase grants (PostgREST). ALL data access goes
-- through the backend (role augura_app); anon/authenticated must not read/write
-- the tables directly. Login events are now recorded via the backend
-- (POST /analytics/events/login, Task 2), not a direct PostgREST insert.
```

- [ ] **Step 4: Replace the `usage_events` policy with append-only policies**

In `apps/api/supabase/policies.sql`, replace the whole `usage_events` block (currently lines 186-197) with:

```sql
-- ── usage_events: append-only audit (tenant/system reads; INSERT only) ────
alter table usage_events enable row level security;
alter table usage_events force row level security;
drop policy if exists tenant_or_system on usage_events;
drop policy if exists usage_events_read on usage_events;
drop policy if exists usage_events_insert on usage_events;
create policy usage_events_read on usage_events
    for select
    using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    );
create policy usage_events_insert on usage_events
    for insert
    with check (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    );
-- Append-only at the privilege level too: no UPDATE/DELETE/TRUNCATE for the app role.
revoke update, delete, truncate on usage_events from augura_app;
```

- [ ] **Step 5: Split the infra-table block — keep `agent_cache` read/write, make `outbox_events` append-only**

In `apps/api/supabase/policies.sql`, replace the `do $$ … array['agent_cache', 'outbox_events'] … $$;` block (currently lines 199-219) with:

```sql
-- ── agent_cache: shared deterministic cache, backend-session gated (read/write) ──
alter table agent_cache enable row level security;
alter table agent_cache force row level security;
drop policy if exists backend_session on agent_cache;
create policy backend_session on agent_cache
    using (nullif(current_setting('app.tenant_id', true), '') is not null)
    with check (nullif(current_setting('app.tenant_id', true), '') is not null);

-- ── outbox_events: append-only system audit, backend-session gated ────────
alter table outbox_events enable row level security;
alter table outbox_events force row level security;
drop policy if exists backend_session on outbox_events;
drop policy if exists outbox_events_read on outbox_events;
drop policy if exists outbox_events_insert on outbox_events;
create policy outbox_events_read on outbox_events
    for select
    using (nullif(current_setting('app.tenant_id', true), '') is not null);
create policy outbox_events_insert on outbox_events
    for insert
    with check (nullif(current_setting('app.tenant_id', true), '') is not null);
revoke update, delete, truncate on outbox_events from augura_app;
```

- [ ] **Step 6: Run the structural guards to verify they pass**

Run: `uv run pytest tests/db/test_supabase_bundle.py -k append_only -q`
Expected: 2 PASSED.

- [ ] **Step 7: Create the idempotent migration that converges already-migrated DBs**

Find the current head: `uv run alembic heads` (note the revision id, e.g. `0011`). Determine the next sequential filename prefix: `ls alembic/versions` (use the next number, shown below as `00NN`).

Create `apps/api/alembic/versions/00NN_audit_append_only.py`:

```python
"""audit append-only: usage_events + outbox_events (idempotent).

Converges DBs already migrated past the 0001 baseline (which applied the old
FOR ALL policies + the authenticated insert grant). Safe to re-run.
"""

from alembic import op

# revision identifiers — set down_revision to the current head from `alembic heads`.
revision = "00NN_audit_append_only"
down_revision = "<CURRENT_HEAD>"
branch_labels = None
depends_on = None

_UPGRADE = """
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke insert on usage_events from authenticated;
    end if;
end
$$;

drop policy if exists tenant_or_system on usage_events;
drop policy if exists usage_events_read on usage_events;
drop policy if exists usage_events_insert on usage_events;
create policy usage_events_read on usage_events
    for select using (
        org_id is null or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy usage_events_insert on usage_events
    for insert with check (
        org_id is null or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
revoke update, delete, truncate on usage_events from augura_app;

drop policy if exists backend_session on outbox_events;
drop policy if exists outbox_events_read on outbox_events;
drop policy if exists outbox_events_insert on outbox_events;
create policy outbox_events_read on outbox_events
    for select using (nullif(current_setting('app.tenant_id', true), '') is not null);
create policy outbox_events_insert on outbox_events
    for insert with check (nullif(current_setting('app.tenant_id', true), '') is not null);
revoke update, delete, truncate on outbox_events from augura_app;
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    # Audit hardening is not reverted automatically (no destructive downgrade).
    pass
```

Replace `00NN_audit_append_only` and `<CURRENT_HEAD>` with the real values, then run `uv run alembic heads` again and confirm a single head.

- [ ] **Step 8: Write the runtime integration test (proof under the real role)**

Create `apps/api/tests/integration/test_audit_append_only.py`:

```python
"""Integration: usage_events is append-only under the augura_app role.

Runs in the db-bundle CI job (pytest -m integration). Skipped locally without
AUGURA_DATABASE_URL. NEVER point this at the prod project (conftest guards it).
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from augura_api.core.db import set_tenant_stmt, set_user_stmt, to_asyncpg_url
from augura_api.core.ids import TenantId, UserId

pytestmark = pytest.mark.integration

LUCIS = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
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


async def _scope(session: AsyncSession, tenant: TenantId, user: UserId) -> None:
    await session.execute(text("set local role augura_app"))
    await session.execute(set_user_stmt(user))
    await session.execute(set_tenant_stmt(tenant))


async def test_usage_events_insert_allowed(sm: async_sessionmaker[AsyncSession]) -> None:
    async with sm() as session, session.begin():
        await _scope(session, LUCIS, USER)
        await session.execute(
            text(
                "insert into usage_events (org_id, user_id, event_type) "
                "values (:o, :u, 'login')"
            ).bindparams(o=str(LUCIS), u=str(USER))
        )  # commits cleanly → INSERT is permitted


async def test_usage_events_update_denied(sm: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(DBAPIError):
        async with sm() as session, session.begin():
            await _scope(session, LUCIS, USER)
            await session.execute(
                text("update usage_events set event_type = 'tampered' where org_id = :o").bindparams(
                    o=str(LUCIS)
                )
            )


async def test_usage_events_delete_denied(sm: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(DBAPIError):
        async with sm() as session, session.begin():
            await _scope(session, LUCIS, USER)
            await session.execute(
                text("delete from usage_events where org_id = :o").bindparams(o=str(LUCIS))
            )
```

- [ ] **Step 9: Run the full bundle + integration locally if a throwaway DB is available**

Structural (always): `uv run pytest tests/db -q` → PASS.
Integration (only if you have a disposable Postgres/branch in `AUGURA_DATABASE_URL`): `uv run alembic upgrade head && uv run pytest -m integration -k audit_append_only -q` → 3 PASSED. Otherwise rely on the db-bundle CI job, which runs `alembic upgrade head` then `pytest -m integration`.

- [ ] **Step 10: Verify the whole backend gate is green**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 11: Apply to prod (owner action — do NOT skip; Modal deploy won't)**

Apply the migration body to the live DB via the Supabase MCP `execute_sql` (project `fqmoylmvjoafihiuiiuj`) — paste the `_UPGRADE` SQL — or run `alembic upgrade head` with `AUGURA_DATABASE_URL` pointed at prod through a privileged role. Then confirm: a `select` on `usage_events` still works for the backend, and a manual `update usage_events …` under `augura_app` is denied.

- [ ] **Step 12: Commit**

```bash
git add apps/api/supabase/policies.sql apps/api/alembic/versions/00NN_audit_append_only.py \
        apps/api/tests/db/test_supabase_bundle.py apps/api/tests/integration/test_audit_append_only.py
git commit -m "feat(compliance): make usage_events/outbox_events append-only; drop forgeable authenticated insert"
```

---

## Task 2: Route login events through the backend (Principal-attributed)

Replaces the client-controlled `supabase.from('usage_events').insert(...)` (forgeable `user_id`, no `org_id`) with a backend endpoint that stamps `user_id`/`org_id` from the verified JWT + resolved tenant. Depends on Task 1 (the direct PostgREST insert is now revoked, so the frontend MUST switch or login logging silently stops).

**Files:**
- Create: `apps/api/src/augura_api/modules/analytics/schemas.py` (add `LoginEventIn`) — or add to the existing schemas module
- Modify: `apps/api/src/augura_api/modules/analytics/router.py`
- Create: `apps/api/tests/test_analytics_login_event.py`
- Modify: `apps/web/src/App.jsx:28-39`

- [ ] **Step 1: Inspect the existing analytics schemas module**

Run: `sed -n '1,40p' src/augura_api/modules/analytics/schemas.py`
Confirm it is a Pydantic `BaseModel` module (it backs `AdminStats`/`ActivityEvent`/`ArtifactOut`). You will add one input model.

- [ ] **Step 2: Write the failing endpoint test**

Create `apps/api/tests/test_analytics_login_event.py`:

```python
"""POST /analytics/events/login records an attributed login event.

The endpoint derives user_id + org_id from the authenticated context (never the
client), and best-effort accepts an optional route. We assert it reaches
analytics.log_usage with server-trusted identity by overriding the auth + session
dependencies (no real DB needed)."""

from collections.abc import AsyncIterator
from uuid import UUID

import httpx

from augura_api.core.deps import get_current_tenant, get_session
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.main import create_app
from augura_api.modules.analytics import router as analytics_router_mod

TENANT = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


async def test_login_event_is_attributed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    recorded: dict[str, object] = {}

    async def fake_log_usage(session, *, tenant_id, user_id, event_type, route=None, metadata=None):  # type: ignore[no-untyped-def]
        recorded.update(
            tenant_id=tenant_id, user_id=user_id, event_type=event_type, route=route
        )

    # The router calls analytics.log_usage — patch it on the router module's import.
    monkeypatch.setattr(analytics_router_mod, "log_usage", fake_log_usage, raising=True)

    app = create_app()

    async def _tenant() -> CurrentTenant:
        return CurrentTenant(tenant_id=TENANT, user_id=USER, role="member")

    async def _session() -> AsyncIterator[object]:
        yield object()

    app.dependency_overrides[get_current_tenant] = _tenant
    app.dependency_overrides[get_session] = _session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/analytics/events/login", json={"route": "/studies"})

    assert r.status_code == 204
    assert recorded["event_type"] == "login"
    assert recorded["user_id"] == USER
    assert recorded["tenant_id"] == TENANT
    assert recorded["route"] == "/studies"
```

> Note: `CurrentTenant` is the dataclass returned by `resolve_tenant`; confirm its constructor kwargs with `sed -n '1,60p' src/augura_api/core/tenancy.py` and adjust the `_tenant()` helper if the field names differ.

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/test_analytics_login_event.py -q`
Expected: FAIL (404 — endpoint not defined).

- [ ] **Step 4: Add the input schema**

In `apps/api/src/augura_api/modules/analytics/schemas.py`, add:

```python
class LoginEventIn(BaseModel):
    """Client payload for a login telemetry event. Identity is NEVER taken from
    here — user_id/org_id come from the authenticated context server-side."""

    route: str | None = None
```

(If `BaseModel` is not already imported in that file, add `from pydantic import BaseModel`.)

- [ ] **Step 5: Add the endpoint (server-attributed)**

In `apps/api/src/augura_api/modules/analytics/router.py`, update the imports and add the route. Change the import line to also pull `log_usage` and `status`:

```python
from fastapi import APIRouter, Depends, status

from augura_api.core.deps import CurrentTenantDep, SessionDep, require_role
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.analytics import log_usage, schemas
from augura_api.modules.analytics.service import AnalyticsService
```

Then add, after the `activity` route:

```python
@router.post("/events/login", status_code=status.HTTP_204_NO_CONTENT)
async def login_event(
    body: schemas.LoginEventIn,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> None:
    """Record an attributed login event. user_id/org_id come from the verified
    JWT + resolved tenant (core/deps), not the client — the audit row is
    trustworthy (Part 11 attributability)."""
    await log_usage(
        session,
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
        event_type="login",
        route=body.route,
        metadata={"source": "web"},
    )
```

> `from augura_api.modules.analytics import log_usage` works because `analytics/__init__.py` re-exports it (it is in `__all__`). Importing the package from its own `router` submodule is safe here because `router` is imported last in `__init__.py`. If pyright/lint-imports flags a cycle, instead import the function lazily inside the handler: `from augura_api.modules.analytics import log_usage`.

- [ ] **Step 6: Run the endpoint test to verify it passes**

Run: `uv run pytest tests/test_analytics_login_event.py -q`
Expected: PASS.

- [ ] **Step 7: Rewire the frontend to call the backend**

In `apps/web/src/App.jsx`, add the import near the top (after line 3):

```jsx
import { apiFetch } from './api'
```

Replace the `SIGNED_IN` block (lines 29-36) with:

```jsx
      if (event === 'SIGNED_IN') {
        sessionStorage.clear()
        // Attributed login event via the backend (user_id/org_id stamped from the
        // verified JWT). Best-effort: never block the UI on telemetry.
        apiFetch('/analytics/events/login', {
          method: 'POST',
          body: JSON.stringify({ route: window.location.pathname }),
        }).catch(() => {})
      }
```

- [ ] **Step 8: Verify the frontend builds**

Run from `apps/web`: `npm run lint && npm run build`
Expected: both succeed.

- [ ] **Step 9: Regenerate the API client (contract changed — new endpoint)**

Run from repo root:
```bash
uv run --directory apps/api python scripts/dump_openapi.py > packages/api-client/openapi.json
npm --prefix packages/api-client run generate
```
Expected: `packages/api-client/src/schema.d.ts` now includes `/analytics/events/login`. (The CI `client-drift` job fails if this is skipped.)

- [ ] **Step 10: Run the backend gate**

Run from `apps/api`: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add apps/api/src/augura_api/modules/analytics/router.py \
        apps/api/src/augura_api/modules/analytics/schemas.py \
        apps/api/tests/test_analytics_login_event.py apps/web/src/App.jsx \
        packages/api-client/openapi.json packages/api-client/src/schema.d.ts
git commit -m "feat(compliance): record login events via attributed backend endpoint"
```

---

## Task 3: Stop sending raw dataset cell values to LLMs

Closes the **critical** PHI-egress finding: `build_varcheck_user_message` embeds up to 5 raw cell values per column (`sample: [...]`) in the prompt sent to Anthropic. The classifier already consumes only column statistics — send those, never raw values.

**Files:**
- Modify: `apps/api/src/augura_api/modules/agents/tools.py:389-416`
- Create: `apps/api/tests/test_agents_varcheck_no_pii.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_agents_varcheck_no_pii.py`:

```python
"""The variable-check prompt must NOT contain raw dataset cell values (PHI egress).

Only column statistics (kind/null%/range/n_distinct) may cross the LLM boundary.
"""

from augura_api.modules.agents.tools import build_varcheck_user_message


def test_varcheck_prompt_excludes_raw_cell_samples() -> None:
    sheets = [
        {
            "name": "cohort",
            "headers": ["patient_email", "hba1c_12m"],
            "sample": [["alice@example.com", 7.1], ["bob@example.com", 6.4]],
            "column_stats": [
                {"column": "patient_email", "value_kind": "string", "null_pct": 0.0, "n_distinct": 2},
                {"column": "hba1c_12m", "value_kind": "numeric", "null_pct": 0.0, "min": 6.4, "max": 7.1},
            ],
        }
    ]
    msg = build_varcheck_user_message(product_description="x", sheets=sheets)

    # No raw cell values leak into the prompt.
    assert "alice@example.com" not in msg
    assert "bob@example.com" not in msg
    assert "sample:" not in msg
    # Statistics the classifier needs are still present.
    assert "hba1c_12m" in msg
    assert "kind: numeric" in msg
    assert "range: 6.4" in msg
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agents_varcheck_no_pii.py -q`
Expected: FAIL (`alice@example.com` and `sample:` present in the prompt).

- [ ] **Step 3: Remove the sample block from the prompt builder**

In `apps/api/src/augura_api/modules/agents/tools.py`, replace the body of the per-column loop (lines 405-415) so it no longer reads `headers`/`sample`. The new loop body:

```python
            rng = ""
            if kind == "numeric" and stat.get("min") is not None:
                rng = f" | range: {stat.get('min')}–{stat.get('max')}"
            # PHI minimization: only column statistics cross the LLM boundary —
            # never raw cell values (HIPAA minimum-necessary / GDPR Art 5(1)(c)).
            parts.append(f"  - {col} | kind: {kind} | null%: {null_str}{rng}{distinct}")
```

Also delete the now-unused `sample` extraction at lines 396-397 (`sample: list[list[Any]] = sheet.get("sample", [])`) and the `headers` line if it becomes unused (line 396 `headers: list[str] = sheet.get("headers", [])`). Run pyright/ruff to confirm no unused-variable warnings remain.

- [ ] **Step 4: Run the new test + the existing varcheck tests**

Run: `uv run pytest tests/test_agents_varcheck_no_pii.py tests/test_agents_gap_varcheck.py -q`
Expected: all PASS (the existing `test_classify_variables_happy_path` does not assert on `sample`, so it stays green).

- [ ] **Step 5: Run the backend gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/augura_api/modules/agents/tools.py apps/api/tests/test_agents_varcheck_no_pii.py
git commit -m "fix(compliance): stop sending raw dataset cell values to the LLM (PHI minimization)"
```

---

## Task 4: Remove the false "Pseudonymised ✓" and cosmetic "SECURE" badges

Both badges assert a control that does not exist — a compliance misrepresentation. Until the real de-identification control lands (Phase 1), the honest state is to show no claim. Frontend-only.

**Files:**
- Modify: `apps/web/src/cockpit/StudyTabs.jsx:252`
- Modify: `apps/web/src/AuguraLogin.jsx:58-66`

- [ ] **Step 1: Replace the false de-identification row**

In `apps/web/src/cockpit/StudyTabs.jsx`, replace line 252:

```jsx
          <div className="flex items-center justify-between"><span>De-identification</span><Badge variant="secondary" className="text-primary">Pseudonymised ✓</Badge></div>
```

with an honest, non-asserting status:

```jsx
          <div className="flex items-center justify-between"><span>De-identification</span><Badge variant="outline" className="text-muted-foreground">Not yet enforced</Badge></div>
```

- [ ] **Step 2: Remove the cosmetic "SECURE" badge from the login card**

In `apps/web/src/AuguraLogin.jsx`, replace the header block (lines 59-64) so the unbacked "SECURE" chip is gone:

```jsx
            <div className="mb-[3px] flex items-center gap-2 text-[13px] font-medium text-foreground">
              Augura
            </div>
```

(Removes the `<span>…SECURE…</span>`. Leave the "Clinical Evidence Intelligence" subtitle untouched.)

- [ ] **Step 3: Verify the frontend builds and lints**

Run from `apps/web`: `npm run lint && npm run build`
Expected: both succeed. Confirm no remaining matches: `grep -rn "Pseudonymised\|>SECURE<\|SECURE\b" src/` returns nothing in `StudyTabs.jsx`/`AuguraLogin.jsx`.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/cockpit/StudyTabs.jsx apps/web/src/AuguraLogin.jsx
git commit -m "fix(compliance): remove unbacked 'Pseudonymised'/'SECURE' UI claims"
```

---

## Task 5: Force verified TLS to Postgres + prod boot fail-fast

Closes the **high** finding that asyncpg connects with no enforced, certificate-validated TLS. Adds an SSL context to the engine and a prod boot guard rejecting a non-TLS DB URL — mirroring the existing CORS prod guard.

**Files:**
- Modify: `apps/api/src/augura_api/core/db.py:54-62`
- Modify: `apps/api/src/augura_api/core/config.py` (add a prod validator + a helper)
- Modify: `apps/api/tests/core/test_db.py` and `apps/api/tests/core/test_config.py`

- [ ] **Step 1: Write the failing config test**

Append to `apps/api/tests/core/test_config.py`:

```python
def test_prod_requires_tls_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """In prod a DB URL without sslmode/ssl must fail fast at boot."""
    monkeypatch.setenv("AUGURA_ENV", "prod")
    monkeypatch.setenv("AUGURA_CORS_ORIGINS", "https://app.augura.io")
    monkeypatch.setenv(
        "AUGURA_DATABASE_URL", "postgresql://u:p@db.example.supabase.co:5432/postgres"
    )
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_prod_accepts_tls_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "prod")
    monkeypatch.setenv("AUGURA_CORS_ORIGINS", "https://app.augura.io")
    monkeypatch.setenv(
        "AUGURA_DATABASE_URL",
        "postgresql://u:p@db.example.supabase.co:5432/postgres?sslmode=require",
    )
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.database_url is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/core/test_config.py -k tls -q`
Expected: `test_prod_requires_tls_database_url` FAILS (no validator yet).

- [ ] **Step 3: Add the prod TLS validator to Settings**

In `apps/api/src/augura_api/core/config.py`, add a model validator after `_require_explicit_prod_cors`:

```python
    @model_validator(mode="after")
    def _require_tls_db_in_prod(self) -> "Settings":
        # PHI-bearing SQL must use TLS. asyncpg does NOT negotiate TLS unless told to,
        # so in prod we require an explicit sslmode/ssl in the URL and verify it at
        # connect time (core/db.py). Fail-fast at boot, like the CORS guard above.
        if self.env == "prod" and self.database_url is not None:
            url = self.database_url.lower()
            if "sslmode=" not in url and "ssl=" not in url:
                raise ValueError(
                    "AUGURA_DATABASE_URL must request TLS in prod "
                    "(append ?sslmode=require — connection is then certificate-verified)."
                )
        return self
```

- [ ] **Step 4: Run the config tests to verify they pass**

Run: `uv run pytest tests/core/test_config.py -k tls -q`
Expected: 2 PASSED.

- [ ] **Step 5: Write the failing engine-SSL test**

Append to `apps/api/tests/core/test_db.py`:

```python
import ssl

from augura_api.core import db as db_mod
from augura_api.core.config import Settings


def test_engine_uses_verified_ssl_context(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """get_engine must pass a hostname-checking, CERT_REQUIRED SSL context to asyncpg."""
    captured: dict[str, object] = {}

    def fake_create(url, **kwargs):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["connect_args"] = kwargs.get("connect_args")
        return object()

    monkeypatch.setattr(db_mod, "create_async_engine", fake_create)
    db_mod._engines.clear()
    settings = Settings(  # pyright: ignore[reportCallIssue]
        env="dev",
        database_url="postgresql://u:p@host:5432/db?sslmode=require",
    )
    db_mod.get_engine(settings)
    ctx = (captured["connect_args"] or {}).get("ssl")  # type: ignore[union-attr]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/core/test_db.py -k ssl -q`
Expected: FAIL (no `connect_args`/`ssl`).

- [ ] **Step 7: Build a verified SSL context in `get_engine`**

In `apps/api/src/augura_api/core/db.py`, add `import ssl` at the top and replace the engine-creation branch (lines 58-61):

```python
    engine = _engines.get(url)
    if engine is None:
        ctx = ssl.create_default_context()  # check_hostname=True, verify_mode=CERT_REQUIRED
        engine = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": ctx})
        _engines[url] = engine
    return engine
```

> asyncpg accepts an `ssl.SSLContext` via `connect_args={"ssl": ctx}`. `create_default_context()` loads the system CA bundle and enforces hostname + certificate verification. Supabase presents a publicly-trusted certificate, so no custom CA file is needed.

- [ ] **Step 8: Run the db test to verify it passes**

Run: `uv run pytest tests/core/test_db.py -k ssl -q`
Expected: PASS.

- [ ] **Step 9: Update `.env.example` to model the TLS URL**

In `apps/api/.env.example`, append `?sslmode=require` to the example `AUGURA_DATABASE_URL` so local prod-like setups inherit it.

- [ ] **Step 10: Run the backend gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add apps/api/src/augura_api/core/db.py apps/api/src/augura_api/core/config.py \
        apps/api/tests/core/test_db.py apps/api/tests/core/test_config.py apps/api/.env.example
git commit -m "feat(compliance): enforce verified TLS to Postgres + prod boot guard"
```

> **Owner action after deploy:** ensure the Modal `augura-api` secret's `AUGURA_DATABASE_URL` carries `?sslmode=require` (re-run `bash scripts/deploy_modal.sh` after updating `.env`), or the prod boot guard will (correctly) fail-fast.

---

## Task 6: Forbid the HS256 shared-secret JWT mode in prod

Closes the **medium** finding that `authenticate()` prefers an HS256 shared secret when present — a leaked secret mints valid tokens for any tenant. In prod, only asymmetric JWKS verification should be reachable.

**Files:**
- Modify: `apps/api/src/augura_api/core/config.py` (validator)
- Modify: `apps/api/tests/core/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/core/test_config.py`:

```python
def test_prod_rejects_hs256_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """HS256 (symmetric) JWT verification must be unreachable in prod."""
    monkeypatch.setenv("AUGURA_ENV", "prod")
    monkeypatch.setenv("AUGURA_CORS_ORIGINS", "https://app.augura.io")
    monkeypatch.setenv("AUGURA_SUPABASE_JWT_SECRET", "super-secret")
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_dev_allows_hs256_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "dev")
    monkeypatch.setenv("AUGURA_SUPABASE_JWT_SECRET", "local-secret")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.supabase_jwt_secret == "local-secret"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/core/test_config.py -k hs256 -q`
Expected: `test_prod_rejects_hs256_secret` FAILS.

- [ ] **Step 3: Add the validator**

In `apps/api/src/augura_api/core/config.py`, add after `_require_tls_db_in_prod`:

```python
    @model_validator(mode="after")
    def _forbid_symmetric_jwt_in_prod(self) -> "Settings":
        # HS256 uses one shared secret to sign AND verify: a leak = tenant-wide token
        # forgery. Prod must verify with the asymmetric Supabase JWKS only.
        if self.env == "prod" and self.supabase_jwt_secret is not None:
            raise ValueError(
                "AUGURA_SUPABASE_JWT_SECRET (HS256) must not be set in prod — "
                "use AUGURA_SUPABASE_JWKS_URL (asymmetric) instead."
            )
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/core/test_config.py -k hs256 -q`
Expected: 2 PASSED.

- [ ] **Step 5: Run the backend gate + commit**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest -q` → PASS.

```bash
git add apps/api/src/augura_api/core/config.py apps/api/tests/core/test_config.py
git commit -m "feat(compliance): forbid HS256 JWT secret in prod (JWKS-only)"
```

---

## Task 7: Require the Supabase Storage backend in prod (no silent plaintext-on-disk fallback)

Closes the **low** finding that, if the Storage env vars are unset in prod, dataset/artifact bytes silently land unencrypted on the Modal container disk. Convert the silent degrade into a boot error.

**Files:**
- Modify: `apps/api/src/augura_api/core/config.py` (validator)
- Modify: `apps/api/tests/core/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/core/test_config.py`:

```python
def test_prod_requires_supabase_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "prod")
    monkeypatch.setenv("AUGURA_CORS_ORIGINS", "https://app.augura.io")
    monkeypatch.delenv("AUGURA_SUPABASE_URL", raising=False)
    monkeypatch.delenv("AUGURA_SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # pyright: ignore[reportCallIssue]


def test_prod_with_supabase_storage_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUGURA_ENV", "prod")
    monkeypatch.setenv("AUGURA_CORS_ORIGINS", "https://app.augura.io")
    monkeypatch.setenv("AUGURA_SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("AUGURA_SUPABASE_SERVICE_ROLE_KEY", "svc")
    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.supabase_url is not None and s.supabase_service_role_key is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/core/test_config.py -k supabase_storage -q`
Expected: `test_prod_requires_supabase_storage` FAILS.

- [ ] **Step 3: Add the validator**

In `apps/api/src/augura_api/core/config.py`, add after `_forbid_symmetric_jwt_in_prod`:

```python
    @model_validator(mode="after")
    def _require_object_store_in_prod(self) -> "Settings":
        # The local-disk storage backend writes unencrypted bytes to the (ephemeral,
        # per-container) Modal FS. In prod the object store is mandatory: fail-fast
        # rather than silently degrade to plaintext-on-disk.
        if self.env == "prod" and not (self.supabase_url and self.supabase_service_role_key):
            raise ValueError(
                "AUGURA_SUPABASE_URL and AUGURA_SUPABASE_SERVICE_ROLE_KEY are required "
                "in prod (object store) — the local-disk fallback is dev/test only."
            )
        return self
```

- [ ] **Step 4: Run the tests + gate + commit**

Run: `uv run pytest tests/core/test_config.py -k supabase_storage -q` → 2 PASSED.
Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest -q` → PASS.

```bash
git add apps/api/src/augura_api/core/config.py apps/api/tests/core/test_config.py
git commit -m "feat(compliance): require Supabase Storage backend in prod (no plaintext-disk fallback)"
```

---

## Task 8: Org-aware object reads (defense-in-depth)

Closes the **low** finding that `read_bytes`/`exists` accept any key with no org check (the service_role key bypasses Storage RLS). Add an optional `expected_org` guard asserting the key is under the caller's `org/<org_id>/` prefix, and wire it at both call sites.

**Files:**
- Modify: `apps/api/src/augura_api/core/storage.py`
- Modify: `apps/api/src/augura_api/modules/datasets/service.py` (`_reprofile` + its 3 callers)
- Modify: `apps/api/src/augura_api/modules/dq/service.py:42`
- Modify: `apps/api/tests/core/test_storage.py`

- [ ] **Step 1: Write the failing storage test**

Append to `apps/api/tests/core/test_storage.py`:

```python
async def test_read_bytes_rejects_foreign_org_prefix(tmp_path: object) -> None:
    settings = _disk_settings(tmp_path)
    ref = await storage.save_bytes(settings, org_id="org-1", name="f.csv", data=b"hi")
    # Correct org: allowed.
    assert await storage.read_bytes(settings, ref, expected_org="org-1") == b"hi"
    # Foreign org: refused before any backend access.
    with pytest.raises(FileNotFoundError):
        await storage.read_bytes(settings, ref, expected_org="org-2")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/core/test_storage.py -k foreign_org -q`
Expected: FAIL (`read_bytes` has no `expected_org`).

- [ ] **Step 3: Add the guard helper + optional param**

In `apps/api/src/augura_api/core/storage.py`, add a helper after `build_ref` (line 42):

```python
def _assert_org(storage_path: str, expected_org: str | None) -> None:
    """Defense-in-depth: refuse a key outside the caller's org prefix, independent
    of DB RLS (the service_role key bypasses Storage RLS)."""
    if expected_org is None:
        return
    prefix = f"org/{_safe(expected_org)}/"
    if not storage_path.startswith(prefix):
        raise FileNotFoundError("storage path outside the caller's org")
```

Update the two public readers:

```python
async def read_bytes(settings: Settings, storage_path: str, *, expected_org: str | None = None) -> bytes:
    """Reads an artifact from its relative storage_path. Raises FileNotFoundError if absent
    or (when expected_org is given) outside that org's prefix."""
    _assert_org(storage_path, expected_org)
    if _use_supabase(settings):
        return await _supabase_get(settings, storage_path)
    return await run_sync(_read_disk, _root(settings).resolve(), storage_path)


async def exists(settings: Settings, storage_path: str, *, expected_org: str | None = None) -> bool:
    _assert_org(storage_path, expected_org)
    if _use_supabase(settings):
        return await _supabase_exists(settings, storage_path)
    return await run_sync(_exists_disk, _root(settings).resolve(), storage_path)
```

- [ ] **Step 4: Run the storage test to verify it passes**

Run: `uv run pytest tests/core/test_storage.py -k foreign_org -q`
Expected: PASS.

- [ ] **Step 5: Thread org into the dq read site**

In `apps/api/src/augura_api/modules/dq/service.py`, line 42 is inside a method where `tenant.tenant_id` is in scope (the `dataset` was fetched via `self.datasets.get_dataset(tenant.tenant_id, …)`). Change line 42:

```python
                data = await read_bytes(settings, f.storage_path, expected_org=str(tenant.tenant_id))
```

- [ ] **Step 6: Thread org into datasets `_reprofile`**

In `apps/api/src/augura_api/modules/datasets/service.py`, change the `_reprofile` signature (line 120) to accept the tenant:

```python
    async def _reprofile(
        self, settings: Settings, tenant: CurrentTenant, dataset_id: UUID
    ) -> list[schemas.ColumnOut]:
```

Change the read at line 132:

```python
            data = await read_bytes(settings, f.storage_path, expected_org=str(tenant.tenant_id))
```

Update its three callers (lines 200, 252, 270) to pass `tenant`:

```python
        columns = await self._reprofile(settings, tenant, dataset.id)   # ~line 200
```
```python
        columns = await self._reprofile(settings, tenant, dataset_id)   # ~line 252
```
```python
        columns = await self._reprofile(settings, tenant, dataset_id)   # ~line 270
```

(`CurrentTenant` is already imported in this module — it types the `tenant` params of the public methods. Confirm with `grep -n "CurrentTenant" src/augura_api/modules/datasets/service.py`.)

- [ ] **Step 7: Run the backend gate (catches missed call sites)**

Run: `uv run ruff check . && uv run pyright && uv run pytest -q`
Expected: all PASS. pyright will flag any `_reprofile` call that still passes the old 2-arg form.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/augura_api/core/storage.py apps/api/src/augura_api/modules/dq/service.py \
        apps/api/src/augura_api/modules/datasets/service.py apps/api/tests/core/test_storage.py
git commit -m "feat(compliance): org-prefix guard on object reads (defense in depth)"
```

---

## Task 9: Security-headers middleware (HSTS, nosniff, minimal CSP) — prod-gated

Closes the **medium** finding that the API asserts no transport-security policy. Add a small middleware that sets defensive headers in prod.

**Files:**
- Create: `apps/api/src/augura_api/core/security_headers.py`
- Modify: `apps/api/src/augura_api/main.py`
- Create: `apps/api/tests/test_security_headers.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_security_headers.py`:

```python
import httpx

from augura_api.core.config import Settings
from augura_api.main import create_app


async def test_security_headers_present_in_prod() -> None:
    cfg = Settings(  # pyright: ignore[reportCallIssue]
        env="prod", cors_origins="https://app.augura.io"
    )
    app = create_app(cfg)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz")
    assert r.headers["strict-transport-security"].startswith("max-age=")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers


async def test_no_hsts_in_dev() -> None:
    app = create_app()  # dev
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz")
    assert "strict-transport-security" not in r.headers
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_security_headers.py -q`
Expected: FAIL (headers absent).

- [ ] **Step 3: Implement the middleware**

Create `apps/api/src/augura_api/core/security_headers.py`:

```python
"""Security-response-headers middleware (prod only).

HSTS + nosniff + a minimal CSP. Gated on env==prod so dev/test responses (and the
OpenAPI/docs UIs) are unaffected. Modal terminates TLS at the edge; HSTS defends
against first-request downgrade on a custom domain.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        return response
```

- [ ] **Step 4: Wire it in `create_app` (prod only)**

In `apps/api/src/augura_api/main.py`, add the import:

```python
from augura_api.core.security_headers import SecurityHeadersMiddleware
```

and add, right after the `RequestIdMiddleware` line (line 27):

```python
    if cfg.env == "prod":
        app.add_middleware(SecurityHeadersMiddleware)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_security_headers.py -q`
Expected: 2 PASSED.

- [ ] **Step 6: Run the gate + commit**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q` → PASS.

```bash
git add apps/api/src/augura_api/core/security_headers.py apps/api/src/augura_api/main.py \
        apps/api/tests/test_security_headers.py
git commit -m "feat(compliance): add prod security-headers middleware (HSTS/nosniff/CSP)"
```

---

## Task 10: Stop leaking internal/identifier context in error responses

Closes the **medium** finding: auth errors echo the raw PyJWT exception text and the token `sub` to the client, and any `exc.context` is serialized verbatim. Fix the concrete auth leaks and suppress `context` in the client response outside dev (always logging it server-side).

**Files:**
- Modify: `apps/api/src/augura_api/core/auth.py:57-66`
- Modify: `apps/api/src/augura_api/core/errors.py`
- Modify: `apps/api/src/augura_api/main.py` (pass `cfg` to the handlers)
- Modify: `apps/api/tests/core/test_errors.py`, `apps/api/tests/core/test_auth.py`

- [ ] **Step 1: Stop passing sensitive context at the auth call sites**

In `apps/api/src/augura_api/core/auth.py`, change the two raises (lines 57-58 and 65-66) to not include `reason`/`sub` in the client-visible context, logging server-side instead. Add `import structlog` and `log = structlog.get_logger(__name__)` near the top, then:

```python
    except jwt.PyJWTError as exc:
        log.info("jwt_rejected", reason=str(exc))
        raise UnauthorizedError("invalid jwt") from exc
```
```python
    try:
        user_id = UserId(UUID(sub))
    except ValueError as exc:
        log.info("jwt_sub_not_uuid")
        raise UnauthorizedError("invalid jwt") from exc
```

> Keep `_unverified_kid` / `_signing_key_from_jwks` raises as-is for now (kid is not sensitive); they are tightened in Phase 2.

- [ ] **Step 2: Update the auth test that asserted the leaked reason**

In `apps/api/tests/core/test_auth.py`, find the test(s) asserting `context["reason"]` / `context["sub"]` on the raised `UnauthorizedError` and change them to assert only `exc.detail == "invalid jwt"` and that `"reason" not in exc.context` / `"sub" not in exc.context`. (Run `grep -n "reason\|sub=" tests/core/test_auth.py` to locate them.)

- [ ] **Step 3: Write the failing prod-suppression test**

Append to `apps/api/tests/core/test_errors.py`:

```python
from augura_api.core.config import Settings


async def test_context_suppressed_in_prod() -> None:
    cfg = Settings(env="prod", cors_origins="https://app.augura.io")  # pyright: ignore[reportCallIssue]
    app = create_app(cfg)

    @app.get("/boom-prod")
    async def boom_prod() -> None:
        raise NotFoundError("study not found", study_id="s1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/boom-prod")
    body = r.json()
    assert body["detail"] == "study not found"
    assert "context" not in body  # internal ids never reach the client in prod
```

(The existing `test_app_error_renders_problem_details` runs in dev and still expects `context` — keep it.)

- [ ] **Step 4: Run it to verify it fails**

Run: `uv run pytest tests/core/test_errors.py -k prod -q`
Expected: FAIL (`context` present).

- [ ] **Step 5: Gate context echo on env, always log it**

In `apps/api/src/augura_api/core/errors.py`, change the signature and the AppError handler:

```python
def register_error_handlers(app: FastAPI, settings: "Settings") -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {
            "type": f"https://augura.dev/errors/{exc.code}",
            "title": exc.title,
            "status": exc.http_status,
            "detail": exc.detail,
            "code": exc.code,
        }
        if exc.context:
            # Always available server-side for debugging; only echoed to clients in dev,
            # so identifiers / internal detail never leak in prod responses.
            log.info("app_error", code=exc.code, context=exc.context)
            if settings.env != "prod":
                body["context"] = exc.context
        return JSONResponse(
            status_code=exc.http_status,
            content=body,
            media_type="application/problem+json",
        )
```

Add the import at the top of `errors.py`:

```python
from augura_api.core.config import Settings
```

(If this introduces an import cycle flagged by `lint-imports`, use `from typing import TYPE_CHECKING` + a string annotation — `core.config` has no reverse dependency on `core.errors`, so a direct import is expected to be fine.)

- [ ] **Step 6: Pass `cfg` from `create_app`**

In `apps/api/src/augura_api/main.py`, change line 36:

```python
    register_error_handlers(app, cfg)
```

- [ ] **Step 7: Run the error + auth tests to verify they pass**

Run: `uv run pytest tests/core/test_errors.py tests/core/test_auth.py -q`
Expected: all PASS (dev still shows context; prod suppresses it).

- [ ] **Step 8: Run the gate + commit**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q` → PASS.

```bash
git add apps/api/src/augura_api/core/auth.py apps/api/src/augura_api/core/errors.py \
        apps/api/src/augura_api/main.py apps/api/tests/core/test_errors.py apps/api/tests/core/test_auth.py
git commit -m "fix(compliance): stop leaking auth internals/ids in error responses (prod)"
```

---

## Task 11: Provision the `datasets` bucket private + reproducibly

Closes the **high** finding that bucket privacy is an out-of-band manual step not verifiable from the codebase. Add a guarded provisioning block to the bundle (no-op on bare CI Postgres, which has no `storage` schema) and a structural test; verify the live `public=false` flag via the Supabase MCP.

**Files:**
- Modify: `apps/api/supabase/policies.sql` (append a guarded block)
- Modify: `apps/api/tests/db/test_supabase_bundle.py` (structural guard)

- [ ] **Step 1: Write the failing structural test**

Append to `apps/api/tests/db/test_supabase_bundle.py`:

```python
def test_datasets_bucket_provisioned_private() -> None:
    """The datasets bucket is created private in the bundle (guarded so bare-Postgres
    CI is a no-op)."""
    policies = _read("policies.sql").lower()
    assert "storage.buckets" in policies
    assert "'datasets'" in policies
    assert "public" in policies  # public=false in the insert
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/db/test_supabase_bundle.py -k bucket -q`
Expected: FAIL.

- [ ] **Step 3: Append the guarded provisioning block to `policies.sql`**

At the end of `apps/api/supabase/policies.sql` (before any trailing `commit;` if present — note the file opens with `begin;` at line 13, so add this before the final `commit;`/end), add:

```sql
-- ── Object storage: the datasets bucket must exist and be PRIVATE ─────────
-- Guarded: the `storage` schema only exists on Supabase, not on the bare CI
-- Postgres (pgvector) where the bundle is also applied → no-op there.
do $$
begin
    if exists (select 1 from information_schema.schemata where schema_name = 'storage') then
        insert into storage.buckets (id, name, public)
        values ('datasets', 'datasets', false)
        on conflict (id) do update set public = false;
    end if;
end
$$;
```

- [ ] **Step 4: Run the structural test + the full bundle test**

Run: `uv run pytest tests/db -q`
Expected: PASS (and the db-bundle CI on real Postgres takes the no-op branch).

- [ ] **Step 5: Verify the live bucket privacy (owner action, via Supabase MCP)**

Using the Supabase MCP against project `fqmoylmvjoafihiuiiuj`, run `execute_sql`:
```sql
select id, public from storage.buckets where id = 'datasets';
```
Confirm `public = false`. If it is `true`, the guarded block (re-applied via MCP) flips it. Also run `get_advisors` (type `security`) and confirm no public-bucket finding for `datasets`.

- [ ] **Step 6: Commit**

```bash
git add apps/api/supabase/policies.sql apps/api/tests/db/test_supabase_bundle.py
git commit -m "feat(compliance): provision the datasets storage bucket private + reproducibly"
```

---

## Task 12: CI security job (SCA) + Dependabot

Closes the **SOC 2 CC7.1** finding: no dependency vulnerability scanning. Add a CI job running `pip-audit` (backend) and `npm audit` (frontend) and enable Dependabot.

**Files:**
- Modify: `.github/workflows/ci.yml` (new `security` job)
- Create: `.github/dependabot.yml`

- [ ] **Step 1: Add the `security` job to CI**

In `.github/workflows/ci.yml`, add a new job under `jobs:` (sibling to `api`):

```yaml
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
      - name: pip-audit (backend dependencies)
        working-directory: apps/api
        run: |
          uv sync --dev
          uv run --with pip-audit pip-audit || (echo "::warning::pip-audit found advisories" && exit 1)
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - name: npm audit (frontend dependencies)
        working-directory: apps/web
        run: npm audit --audit-level=high
```

> If existing transitive advisories make the job red on day one, triage them first (upgrade or document an ignore with justification) — do not weaken `--audit-level` silently; per the spec, no silent caps.

- [ ] **Step 2: Add Dependabot config**

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/apps/api"
    schedule:
      interval: "weekly"
  - package-ecosystem: "npm"
    directory: "/apps/web"
    schedule:
      interval: "weekly"
  - package-ecosystem: "npm"
    directory: "/packages/api-client"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

- [ ] **Step 3: Validate the workflow YAML locally**

Run from repo root: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/dependabot.yml')); print('yaml ok')"`
Expected: `yaml ok`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml .github/dependabot.yml
git commit -m "ci(compliance): add dependency SCA (pip-audit/npm audit) + Dependabot"
```

> **Owner action:** in GitHub repo Settings → Code security, enable **secret scanning** and **push protection** (not expressible in-repo).

---

## Task 13: Branch protection + CODEOWNERS

Closes the **SOC 2 CC8.1** finding: no enforced change control on `main`/`Quentin`. Add CODEOWNERS (in-repo) and document the branch-protection commands (GitHub API).

**Files:**
- Create: `.github/CODEOWNERS`

- [ ] **Step 1: Create CODEOWNERS**

Create `.github/CODEOWNERS` (replace `@your-gh-handle` with the actual owner/team):

```
# Default owner for everything — every PR requires their review.
*               @your-gh-handle

# Compliance-critical surfaces require explicit owner review.
/apps/api/supabase/                 @your-gh-handle
/apps/api/src/augura_api/core/      @your-gh-handle
/.github/                           @your-gh-handle
```

- [ ] **Step 2: Verify the file is well-formed**

Run from repo root: `test -f .github/CODEOWNERS && echo "codeowners present"`
Expected: `codeowners present`.

- [ ] **Step 3: Enable branch protection (owner action — requires admin token)**

Run (replace `OWNER/REPO`), once per protected branch (`main`, `Quentin`):

```bash
gh api -X PUT repos/OWNER/REPO/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks[strict]=true \
  -f 'required_status_checks[contexts][]=api' \
  -f 'required_status_checks[contexts][]=db-bundle' \
  -f 'required_status_checks[contexts][]=client-drift' \
  -f 'required_status_checks[contexts][]=web' \
  -f 'required_status_checks[contexts][]=security' \
  -f enforce_admins=true \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'required_pull_request_reviews[require_code_owner_reviews]=true' \
  -f restrictions=
```

Verify: `gh api repos/OWNER/REPO/branches/main/protection | python -c "import json,sys;d=json.load(sys.stdin);print('required reviews:', d['required_pull_request_reviews']['required_approving_review_count'])"` → `1`.

> Note: enforcing PR-only on `Quentin` (the prod deploy source) means future merges go through review + green CI — the core CC8.1 control. Coordinate with the team before flipping, since it changes the day-to-day flow.

- [ ] **Step 4: Commit**

```bash
git add .github/CODEOWNERS
git commit -m "ci(compliance): add CODEOWNERS (branch protection enabled via GitHub settings)"
```

---

## Self-Review

**1. Spec coverage (Phase 0 items → tasks):**
- Append-only audit policies → Task 1 ✓
- Kill forgeable login insert / route via backend → Tasks 1 + 2 ✓
- Stop raw cell → LLM → Task 3 ✓
- Remove false badges → Task 4 ✓
- Verified TLS + prod guard → Task 5 ✓
- Forbid HS256 in prod → Task 6 ✓
- Require object store in prod → Task 7 ✓
- Org-aware storage reads → Task 8 ✓
- Security headers → Task 9 ✓
- Suppress error-context leak → Task 10 ✓
- Private bucket reproducibly → Task 11 ✓
- CI SCA + Dependabot → Task 12 ✓
- Branch protection + CODEOWNERS → Task 13 ✓

**2. Placeholder scan:** The only intentionally environment-specific values are `<CURRENT_HEAD>` / `00NN` (Task 1 migration — resolved by `alembic heads`/`ls`), `@your-gh-handle` and `OWNER/REPO` (Task 13 — the executor substitutes the real handle/repo). All code steps include complete code.

**3. Type/name consistency:** `expected_org` is the single keyword across `storage.read_bytes`/`exists`/`_assert_org` and both call sites. `register_error_handlers(app, settings)` matches the `create_app` call. `LoginEventIn.route` matches the endpoint body usage and the frontend payload (`{ route }`). `log_usage(...)` kwargs match `analytics/__init__.py`.

**Cross-task ordering note:** Task 2 must land with (or immediately after) Task 1 — Task 1 revokes the frontend's direct insert, so login logging only continues via the Task 2 endpoint.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-24-compliance-phase-0.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
