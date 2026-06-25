# Compliance Hardening — Phase 2 (Access Control) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Enforce least-privilege/authority at the API: make `viewer` truly read-only (RBAC write-gating), add flag-gated MFA (`aal2`) enforcement on PHI routes, and harden JWKS verification.

**Tech Stack:** FastAPI · SQLAlchemy async · Pydantic v2 · PyJWT · pytest. Backend in `apps/api`, pyright strict, ruff line 100.

**Spec:** [docs/superpowers/specs/2026-06-24-compliance-hardening-design.md](../specs/2026-06-24-compliance-hardening-design.md)

## Scope

**In this plan:** RBAC write-gating (Task 1), flag-gated MFA/aal2 enforcement (Task 2), JWKS hardening (Task 3).

**Deferred (documented — would break prod or need external setup):**
- **P7 PostgREST SELECT lockdown** — revoking `authenticated` SELECT breaks the *currently-deployed* frontend's direct cockpit reads until those are migrated to the backend. Gate behind a future frontend-migration task; do NOT flip live.
- **Idle/absolute session timeout** — frontend change (`apps/web`); separate FE task.
- **MFA enrollment** — Supabase dashboard + frontend enrollment UI; Task 2 ships the *backend enforcement* flag-gated so it's ready to switch on after enrollment exists.

## Conventions
Run backend cmds from `apps/api`; `export AUGURA_ENV=dev` before alembic. Gate: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports && uv run pytest -q`. Baseline GREEN: 291 passed, 40 skipped. Commit locally only, no AI-attribution trailer.

---

## Task 1: RBAC write-gating (`viewer` becomes read-only)

`require_role` exists but gates only 2 modules; `viewer` can create/update/delete everything. Add a write-gating dependency and apply it to every endpoint that **persists or mutates tenant data** (or triggers a job/LLM run). Pure read endpoints (GET) and pure-compute reads stay open to all members.

**Files:**
- Modify: `apps/api/src/augura_api/core/deps.py` (add `WriteTenantDep`)
- Modify the mutating routers (swap `CurrentTenantDep` → `WriteTenantDep` on the listed endpoints)
- Create: `apps/api/tests/integration/test_rbac_viewer_readonly.py` (DB-backed) + a unit test for the dependency

- [ ] **Step 1: Add the write-gating dependency**

In `apps/api/src/augura_api/core/deps.py`, after `require_role`, add:

```python
# Write-gating: only owner/member may mutate tenant data; viewer is read-only.
WriteTenantDep = Annotated[CurrentTenant, Depends(require_role("owner", "member"))]
```

- [ ] **Step 2: Write the failing unit test for the dependency**

Create `apps/api/tests/core/test_rbac.py`:

```python
"""require_role('owner','member') rejects a viewer (RBAC write-gating)."""

import pytest

from augura_api.core.deps import require_role
from augura_api.core.errors import ForbiddenError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from uuid import uuid4


def _tenant(role: str) -> CurrentTenant:
    return CurrentTenant(tenant_id=TenantId(uuid4()), user_id=UserId(uuid4()), role=role)


async def test_viewer_blocked_from_write() -> None:
    dep = require_role("owner", "member")
    with pytest.raises(ForbiddenError):
        await dep(_tenant("viewer"))


async def test_member_allowed_write() -> None:
    dep = require_role("owner", "member")
    out = await dep(_tenant("member"))
    assert out.role == "member"
```

> `require_role` returns a dependency callable that takes the tenant; here we call it directly. Confirm its signature in `deps.py` (it wraps `_require(tenant)`); if it expects to be resolved via DI, adapt the test to call the inner function. Verify `CurrentTenant` field names.

- [ ] **Step 3: Run it to verify it fails / passes appropriately**

Run: `uv run pytest tests/core/test_rbac.py -q` (FAIL only if the dependency or import is wrong; this mostly pins behavior).

- [ ] **Step 4: Apply `WriteTenantDep` to mutating endpoints**

Replace `tenant: CurrentTenantDep` with `tenant: WriteTenantDep` on these **persisting/mutating** endpoints (import `WriteTenantDep` from `core.deps` in each router):

- `studies/router.py`: `POST ""` (create), `PATCH /{study_id}`, `PUT /{study_id}/state`
- `datasets/router.py`: `POST ""`, `POST /upload`, `PUT /{dataset_id}/columns`, the add-files `POST`, `DELETE /{dataset_id}/files/{file_id}`, `POST /{dataset_id}/data-dictionary`
- `dq/router.py`: the run `POST`
- `mapping/router.py`: the run `POST`
- `documents/router.py`: the generate `POST`
- `simulation/router.py`: `POST ""` (creates a run). LEAVE `POST /power` open (pure compute, no persistence).
- `semantic/router.py`: `POST /enrich/apply` already requires owner — leave; apply `WriteTenantDep` to `POST /enrich/propose` (the other POST).
- `causal/router.py`: `POST /dag` (persists). LEAVE `POST /parse-question` open if it's pure parse (confirm it doesn't persist; if it does, gate it).
- `corpus/router.py`: `POST /literature/ingest`, `POST /literature/snapshots`, `POST /literature/sessions`, `DELETE /literature/sessions`, `DELETE /literature/sessions/{session_id}`, `POST /literature/sessions/{session_id}/events`. LEAVE `POST /search`, `POST /literature`, `POST /literature/retrieve` open (read-only search/compute).
- `agents/router.py`: LEAVE all open (LLM compute, not tenant-data writes) in v1.

For each, confirm by reading the endpoint whether it persists; when in doubt, gate it (fail-safe toward least-privilege). pyright will catch a missed import.

- [ ] **Step 5: Write the DB-backed RBAC integration test**

Create `apps/api/tests/integration/test_rbac_viewer_readonly.py` that, with a real DB + a viewer membership, asserts a representative write (e.g. `POST /datasets`) returns 403 and a read (`GET /datasets`) returns 200. Use the `tests/integration` harness pattern (skip without `AUGURA_DATABASE_URL`); seed/insert a viewer membership for a test user via the privileged role, then drive the app with an overridden principal. If standing up a full HTTP client with auth is heavy, instead unit-test that the listed routers declare `WriteTenantDep` (introspect `router.routes` dependencies). Pick whichever is reliable; document the choice.

- [ ] **Step 6: Gate + commit**

Run the full gate. Commit:
```bash
git commit -m "feat(compliance): RBAC write-gating — viewer is read-only on mutating endpoints"
```

---

## Task 2: Flag-gated MFA (`aal2`) enforcement on PHI routes

Add backend enforcement that PHI routes require an `aal2` (MFA-satisfied) token, controlled by a config flag (default OFF so it can't lock users out before enrollment exists).

**Files:**
- Modify: `apps/api/src/augura_api/core/config.py` (add `require_mfa: bool = False`)
- Modify: `apps/api/src/augura_api/core/auth.py` (verify `aal` claim when enabled)
- Modify: `apps/api/tests/core/test_auth.py`

- [ ] **Step 1: Add the config flag**

In `config.py` Settings: `require_mfa: bool = False  # enforce aal2 on PHI routes once MFA enrollment is live`.

- [ ] **Step 2: Write failing tests**

Append to `tests/core/test_auth.py`: with `require_mfa=True`, a token whose claims lack `aal=="aal2"` raises `UnauthorizedError`; with `aal2` it passes; with `require_mfa=False` (default) `aal` is ignored. Build `Settings(env="dev", supabase_jwt_secret="s", require_mfa=True)` and craft HS256 tokens with/without the `aal` claim (mirror the existing `test_auth.py` token-building helpers).

- [ ] **Step 3: Enforce in `authenticate`/`verify_token`**

After a token is decoded into `Principal`, if `settings.require_mfa` is true, require `claims.get("aal") == "aal2"` (and/or a non-empty `amr`), else raise `UnauthorizedError("mfa required")`. Implement it where `settings` is in scope (`authenticate`), so `verify_token` stays pure — or pass a flag through. Keep the message non-leaky (no claim values).

- [ ] **Step 4: Gate + commit**

```bash
git commit -m "feat(compliance): flag-gated MFA (aal2) enforcement on authenticated routes"
```

---

## Task 3: JWKS verification hardening

Cache the JWKS with a TTL + refresh-on-unknown-kid, and reject a token whose header omits `kid` in JWKS mode (don't silently use the first key).

**Files:**
- Modify: `apps/api/src/augura_api/core/auth.py`
- Modify: `apps/api/tests/core/test_auth.py`

- [ ] **Step 1: Failing tests**
A token with no `kid` (JWKS mode) → `UnauthorizedError` (not silent first-key). A second `authenticate` call reuses the cached JWKS (fetcher called once) within TTL; an unknown `kid` triggers exactly one refetch before failing.

- [ ] **Step 2: Implement**
In `_signing_key_from_jwks`, when `kid is None` raise `UnauthorizedError("jwt missing kid")` instead of returning the first key. Add a small in-process TTL cache around the JWKS fetch keyed by URL (e.g. a module-level dict of `{url: (fetched_at, jwks)}`); on unknown kid, refetch once (bust cache) before raising. Keep the injected-fetcher seam for tests.

- [ ] **Step 3: Gate + commit**

```bash
git commit -m "feat(compliance): JWKS hardening — require kid, cache with TTL + refresh-on-miss"
```

---

## Self-Review
- Coverage: RBAC (Task 1), MFA enforcement (Task 2), JWKS hardening (Task 3) = the access-control core of the spec's Phase 2. P7 lockdown, session timeout, MFA enrollment deferred with rationale.
- The RBAC matrix errs toward gating when an endpoint's persistence is ambiguous (fail-safe least-privilege).

## Execution
Subagent-driven, sequential (Tasks share `auth.py`/`deps.py`), then merge to `Quentin`.
