# Subsystem D — Config / Reference endpoints — Design

**Date:** 2026-06-16
**Status:** Proposed (awaiting review)
**Part of:** MVP→platform port roadmap (4 sub-projects, order **D → A → B → C**). This is **D**, the foundation slice.

## Context

The platform frontend (`apps/web/src/LucisApp.jsx`) already calls three config endpoints that **this backend does not serve** — they were Vercel serverless routes in the `Augura-Health/augura` MVP and were never ported:

- `GET /api/tenant?projectId=<slug>` → tenant CESL profile (clinical domains, evidence types)
- `GET /api/study-designs` → study-design label catalog
- `GET /api/cesl-sources` → evidence-source catalog

Today those three `fetch()` calls hit dead relative paths (no base URL, no auth header), so tenant config, study-design labels and source labels silently fail in the platform. Subsystem D ports them idiomatically into the FastAPI backend, adds the backing reference tables, and rewires the frontend onto the generated api-client. It is sequenced first because A and B depend on the same reference catalogs (`cesl_*`).

## Goals

1. Serve tenant CESL profile + the two reference catalogs from the FastAPI backend, idiomatically (vertical-slice module, RLS, api-client).
2. Add the two reference tables to the schema bundle and seed them with real catalog data.
3. Rewire the three frontend calls onto the api-client; remove the dead `/api/*` fetches.
4. Fix the latent bug where the frontend passes the **study id** as `projectId`.

## Non-goals

- Editing/CRUD of the catalogs (read-only; writes happen via seed / privileged role).
- Porting the MVP's `/api/meta` multiplexer or `corpus-sources` resource (the platform already serves `/corpus/sources` + `/corpus/coverage`).
- Any A/B/C subsystem work.

## Architecture

New backend module `reference`, following the platform's vertical-slice convention (`__init__.py` exports `router`; `router.py` / `service.py` / `repo.py` / `models.py` / `schemas.py`). Mounted in `main.py` via `app.include_router(reference_router)`.

### Endpoints

All require auth (`CurrentTenantDep`) and run under the RLS-scoped `SessionDep`, matching every other module.

| Method | Path | Response | Source |
|--------|------|----------|--------|
| `GET` | `/reference/tenant` | `TenantProfileOut { id, name, slug, cesl_profile }` | `orgs` row for the JWT-resolved tenant |
| `GET` | `/reference/cesl-sources` | `list[CeslSourceOut]` | `cesl_sources` where `active`, ordered by `sort_order` |
| `GET` | `/reference/study-designs` | `list[StudyDesignOut]` | `cesl_study_designs` where `active`, ordered by `sort_order` |

**Tenant resolution (decided):** `/reference/tenant` returns the **current** org from the JWT (`tenant.tenant_id`) — no `projectId`/slug parameter. Rationale: removes the slug-injection surface, prevents cross-tenant reads, and `orgs.cesl_profile` already exists for exactly this. Side benefit: fixes the latent bug where `LucisApp` passed `params.id` (a *study* id) as `projectId`.

### Schemas (Pydantic, `schemas.py`)

```
TenantProfileOut:  id: UUID; name: str; slug: str; cesl_profile: dict[str, Any]
CeslSourceOut:     code: str; label: str; doc_type: str | None; description: str | None;
                   base_url: str | None; sort_order: int; result_unit: str | None
StudyDesignOut:    code: str; label: str; group_name: str | None; sort_order: int
```

`cesl_profile` is passed through as an opaque object (frontend reads `cesl_profile.clinical_domain` / `cesl_profile.evidence_type`, both arrays).

### Repo (`repo.py`)

- `get_org(tenant_id) -> Org | None` — `select(Org).where(Org.id == tenant_id)`. RLS `tenant_self` already guarantees only the own row is visible; the explicit filter is defense-in-depth (matches the studies repo pattern).
- `list_cesl_sources() -> list[CeslSource]` — `where(active).order_by(sort_order)`. Global; no tenant filter.
- `list_study_designs() -> list[CeslStudyDesign]` — same shape.

### Service (`service.py`)

`ReferenceService(repo)` with `tenant_profile(tenant)`, `cesl_sources()`, `study_designs()`. `tenant_profile` raises `NotFoundError` if the org row is missing (shouldn't happen — a resolved tenant always has an org). Maps ORM → schema.

### Models (`models.py`)

- `Org` — minimal ORM mapping of the existing `orgs` table (`id, name, slug, cesl_profile`). (No `orgs` model exists yet; this module introduces it.)
- `CeslSource` → `cesl_sources`.
- `CeslStudyDesign` → `cesl_study_designs`.

## Data model (DB)

Add to `apps/api/supabase/schema.sql` (global reference tables, not tenant-scoped):

```sql
create table if not exists cesl_sources (
    code        text primary key,
    label       text not null,
    doc_type    text,
    description text,
    base_url    text,
    result_unit text,
    sort_order  int  not null default 0,
    active      boolean not null default true
);

create table if not exists cesl_study_designs (
    code       text primary key,
    label      text not null,
    group_name text,
    sort_order int not null default 0,
    active     boolean not null default true
);
```

### RLS (`apps/api/supabase/policies.sql`)

Both tables are global catalogs. Follow the existing **backend-session gate** pattern (as used for `agent_cache` / `outbox_events`): RLS enabled + forced; read allowed whenever a backend session context is set (`app.tenant_id is not null`), which denies direct anon/PostgREST access while allowing any authenticated tenant session to read. Writes restricted to the seed / privileged role (no `with check` for tenant sessions → tenant sessions cannot write).

```sql
foreach t in ['cesl_sources','cesl_study_designs']:
    enable + force RLS;
    create policy backend_read on t
        using (nullif(current_setting('app.tenant_id', true), '') is not null);
```

### Seed (`apps/api/supabase/seed.sql`)

Decided: seed the catalogs **in the bundle** (reference config, not demo data — consistent with the real-only rule). `seed.sql` runs after `functions.sql` and before `policies.sql`, i.e. before RLS, so inserts are unrestricted.

**Seed content source:** the authoritative rows live in the MVP's Supabase project, which is not reachable from this environment (platform `.env` has only `AUGURA_DATABASE_URL`, pointing at the clean platform DB). The seed is therefore **reconstructed** from the MVP's own constants — and is functionally complete for the frontend:

- `cesl_sources` (the four source_ids the platform's E1 agent already uses — `apps/api/.../modules/agents` + MVP `ProfilingRun.jsx`):
  `pubmed` (PubMed, doc_type=study), `clinicaltrials` (ClinicalTrials.gov, doc_type=trial), `maude` (MAUDE, doc_type=adverse_event), `guidance` (FDA Guidance, doc_type=guidance) — with `base_url`, `result_unit`, `sort_order`.
- `cesl_study_designs` (MVP `StudyType.jsx` / `StudyDesign.jsx`):
  `retro_cohort` (Retrospective cohort), `pre_post` (Pre/post), `external_matched` (External matched control), `mediation` (Causal mediation), `prospective` (Prospective) — grouped via `group_name`, ordered.

> **Follow-up (flagged, not blocking):** if the user provides MVP Supabase access, replace the reconstructed rows with the authoritative catalog via a one-shot extract. The table contract does not change.

The default `orgs` seed stays empty (real orgs are created by the app); `cesl_profile` defaults to `'{}'`, so `/reference/tenant` returns an empty profile until an org is configured — the frontend already tolerates empty `clinical_domain` / `evidence_type` arrays.

## Frontend changes (`apps/web`)

In `LucisApp.jsx`, replace the three raw `fetch('/api/...')` calls with api-client calls via the existing `apiJson` helper (`apps/web/src/api.js`, which injects `VITE_API_URL` + Bearer token):

- `fetch('/api/tenant?projectId=…')` → `apiJson('/reference/tenant')` (drop the param; server resolves tenant from JWT). Update the effect's dependency array accordingly.
- `fetch('/api/study-designs')` → `apiJson('/reference/study-designs')`, then reshape to the existing `{ code: label }` map.
- `fetch('/api/cesl-sources')` → `apiJson('/reference/cesl-sources')`.

Regenerate `packages/api-client` from the updated OpenAPI so the CI drift-check passes (`openapi.json` + generated types).

## Error handling

- Missing/invalid Bearer → `401` (existing `CurrentTenantDep`).
- Missing org row → `NotFoundError` → `404` (existing error handler). Not expected for a resolved tenant.
- Empty catalogs → `200 []` (honest empty, not an error).
- No new upstream/LLM calls → no `5xx` paths beyond the standard DB/auth ones.

## Testing

Mirror the existing module test layout (`apps/api/tests/`):

- **Unit (service/repo):** `cesl_sources()` / `study_designs()` return active rows ordered by `sort_order`; inactive rows excluded; `tenant_profile` maps the org row; missing org → `NotFoundError`.
- **Integration (router, httpx AsyncClient):** the three endpoints return `200` with the documented shapes for an authenticated tenant; `401` without a token; `/reference/tenant` returns the caller's own org only (RLS), never another tenant's.
- **DB bundle:** extend the existing `tests/db/test_supabase_bundle.py` to assert `cesl_sources` / `cesl_study_designs` exist, are seeded (count > 0), have RLS enabled, and are readable under a backend session but not by anon.
- **api-client drift:** the generated client matches the new OpenAPI (existing CI check).

## Acceptance criteria

1. `GET /reference/{tenant,cesl-sources,study-designs}` return the documented shapes for an authenticated user; `401` unauthenticated.
2. `cesl_sources` + `cesl_study_designs` exist in the schema bundle, are seeded, RLS-protected (backend-readable, anon-denied, tenant-unwritable).
3. `LucisApp.jsx` loads tenant profile, study designs, and CESL sources via the api-client; no remaining `/api/tenant|study-designs|cesl-sources` fetches; the study-id-as-projectId bug is gone.
4. api-client regenerated; drift-check green.
5. Backend + DB-bundle tests pass.

## Risks / open items

- **Seed authenticity:** reconstructed rows, not the live MVP catalog (flagged above). Functionally complete; swap in authoritative data later if desired.
- **`orgs` model introduction:** D adds the first ORM mapping of `orgs`. Keep it minimal and reuse it in later subsystems rather than re-declaring.
- **Frontend `cesl_profile` shape:** confirmed the frontend only reads `clinical_domain` / `evidence_type` arrays; passing `cesl_profile` through opaquely is safe.
