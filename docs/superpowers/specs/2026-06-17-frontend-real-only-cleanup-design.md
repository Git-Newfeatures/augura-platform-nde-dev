# Frontend real-only cleanup — design spec

**Date:** 2026-06-17
**Branch:** `frontend-real-only-cleanup` (off `Quentin`)
**Status:** Approved design — ready for implementation planning

## Goal

`apps/web` must render **only real, backend-sourced data**. Strip every hardcoded
domain catalog, fallback, and demo construct from the frontend. Domain catalogs
move to the backend `reference` module and are fetched at runtime; exposure /
population options are derived from live cohort data. Pure presentation (icons,
colors, the routing graph, formatting helpers) stays in the client because it is
code, not data.

This is a single coherent effort, executed in four phases:

1. Backend reference catalogs (tables + seed + endpoints + tests)
2. Frontend reference client layer (`dataClient` fetchers + `useReference` hook)
3. Wire each view to the new endpoints and delete all hardcoded / fallback data
4. Verify (backend `pytest`, frontend `vite build` + preview smoke)

## Non-goals

- Do **not** disturb in-flight uncommitted work on `Quentin` (the modified
  `AuguraAssistant.jsx`, the RLS migration `0003_literature_per_study_rls.py`,
  the modified `policies.sql` / `schema.sql`, the new `test_corpus_rls.py`).
- No unrelated refactoring. Stay scoped to removing hardcoded/mock data.
- No change to the numeric regulatory constants `POWER_THRESHOLD` /
  `POWER_MARGINAL_FLOOR` (these are constants, not data).

## Decisions locked during brainstorming

- **Scope:** most aggressive — move all domain catalogs to the backend and
  create the endpoints where they don't exist yet.
- **Bucket ④ (debatable items):** move **everything** to the backend —
  `ESTIMATORS`/`ESTIMATOR_FILTER`, `PII_PATTERNS`, and biomarker `RANGES` all
  become backend-sourced.
- **Exposure / population options:** **derive from the cohort** at runtime from
  the data already fetched via `fetchCohort` — no preset catalog.
- **Empty behavior:** reuse the existing loading + EmptyState pattern; catalogs
  are seeded so they should never be empty in practice.

## Architecture

The backend already provides the exact pattern to extend: the `reference`
module (`modules/reference/`) with `router → service → repo → SQLAlchemy model`,
seeded via `supabase/seed.sql`, RLS-readable, JWT + tenant scoped through
`CurrentTenantDep` / `SessionDep`. Existing endpoints:
`/reference/tenant`, `/reference/cesl-sources`, `/reference/study-designs`.

The frontend already provides the consumption pattern: `dataClient.js` with a
`FETCHERS` map, `fetchCollection`, and the `useCollection(name)` hook returning
`{ data, loading }`, with `[]`/empty → EmptyState.

We extend both rather than introduce new patterns.

## Backend changes (`apps/api`)

New seeded reference tables + GET endpoints, each implemented model → repo →
service → schema → router → `seed.sql` row(s) → test, mirroring `cesl_sources`.

| Endpoint | Table | Payload fields |
|---|---|---|
| `GET /reference/outcomes` | `outcome_catalog` | `code, label, unit, primary, description, regulatory_tags[], verdict, verdict_label, sort_order` |
| `GET /reference/study-designs` *(enrich existing)* | `cesl_study_designs` (+ cols) | existing + `description, tags (jsonb), estimands (jsonb)` |
| `GET /reference/estimands` | `estimand_catalog` | `key, name, description, regulatory, recommended, tag, sort_order` |
| `GET /reference/estimators` | `estimator_catalog` | `key, label, short, recommended, bootstrap_pending, interpretability, stability, tooltip, eligible_study_types (jsonb), sort_order` |
| `GET /reference/frameworks` | `framework_catalog` | `code, label, sort_order` |
| `GET /reference/evidence-types` | `evidence_type_catalog` | `code, label, description, sort_order` |
| `GET /reference/domains` | `domain_catalog` | `code, label, sort_order` |
| `GET /reference/jurisdictions` | `jurisdiction_catalog` | `code, label, sort_order` |
| `GET /reference/dq-rules` | `pii_pattern_catalog`, `biomarker_range_catalog` | `{ pii_patterns: [{key,label,pattern}], biomarker_ranges: [{code,min,max,unit}] }` |
| `GET /reference/variable-roles` | `variable_group_catalog`, `variable_role_catalog` | `{ groups: [{code,label,sort_order}], roles: [{code,label,group,sort_order}] }` |

**Migration:** a new Alembic revision (after `0003`) creating the new tables and
the added `cesl_study_designs` columns. Reference rows added to `seed.sql`
(applied before RLS activation, like the existing CESL seed). Source the seed
values verbatim from the current frontend constants so behavior is preserved.

**Schemas:** `*Out` Pydantic models with `ConfigDict(from_attributes=True)`,
following `modules/reference/schemas.py`.

**Tests:**
- Unit: extend `tests/test_reference_service.py` with fake-repo cases for each
  new service method (assert mapping/order).
- Routes: extend `tests/test_app_routes.py` so the new `/reference/*` paths
  appear in the OpenAPI schema and require auth (401 without a token).

**Auth:** all endpoints use `CurrentTenantDep` + `SessionDep` (global reference
data, RLS-readable by any tenant), identical to `cesl_sources`.

## Frontend changes (`apps/web`)

### Reference client layer
- Add a reference fetcher set to `dataClient.js` (one async fetcher per
  endpoint, normalizing snake_case → the shape each view already renders).
- Add `useReference(name)` — a session-cached hook (reference data is static for
  the session) returning `{ data, loading }`. Cache keyed by name to avoid
  refetching the same catalog across views.

### Wire + strip per view

- **`views/OutcomeSelection.jsx`**
  - Fetch `/reference/outcomes`.
  - **Delete:** `OUTCOME_CATALOG`, `FALLBACK_OUTCOMES`, `ENDPOINT_METADATA`,
    `buildOutcomesFromEndpoints`, `ELEMENT_RATIONALE`, `D1_OUTCOME_MAP`.
  - Derive the D1 ("change at 12 months") label from the catalog label + the
    study's follow-up window.
  - Derive `EXPOSURE_OPTIONS` / `POPULATION_OPTIONS` at runtime from the cohort
    data returned by `fetchCohort` (real engagement column + real country/age
    values), not a preset list.
  - Element rationale: source from real agent output if available, else omit the
    rationale line (no hardcoded prose).

- **`views/StudyType.jsx`**
  - Fetch enriched `/reference/study-designs` + `/reference/estimands`.
  - **Delete:** `getStudyDesigns`, `ESTIMAND_OPTS`.
  - Keep `DESIGN_ICON` and a client-side `designId → color` map (presentation).

- **`workspace/NewStudyPage.jsx`**
  - Fetch `/reference/frameworks`; **delete** `FRAMEWORKS`.

- **`config.js`**
  - **Delete:** `ESTIMATORS`, `ESTIMATOR_FILTER`. Consumers (`CausalModel` in
    `LucisApp`, `SimulationEngine`) fetch `/reference/estimators` and filter by
    `eligible_study_types`.
  - **Keep:** `POWER_THRESHOLD`, `POWER_MARGINAL_FLOOR`.

- **`CorpusPanelEmbed.jsx`**
  - Fetch `/reference/evidence-types`, `/domains`, `/jurisdictions`, and source
    labels (`/reference/cesl-sources`, already exists).
  - **Delete:** `ET_LABELS`, `ET_DESCRIPTIONS`, `DOMAIN_LABELS`, `JUR_LABELS`,
    `SOURCE_LABEL_FALLBACK`, `SOURCE_ET_DEFAULTS`.
  - **Keep:** `ET_COLORS`, `COVERAGE_COLS`/`COL_LABELS` ordering (presentation).

- **`views/ProfilingAssistant.jsx`**
  - Source design/doc-type labels from reference endpoints; **delete**
    `STUDY_DESIGN_FALLBACK`, `DOC_TYPE_FALLBACK`.
  - Source biomarker `RANGES` + `ID_COLS` from `/reference/dq-rules`.

- **`views/DatasetVerification.jsx`**
  - Fetch `/reference/dq-rules`; **delete** `PII_PATTERNS`.
  - Move the variable-classification taxonomy to reference: the `GROUPS` and
    `ROLES` **codes + labels** become a `GET /reference/variable-roles`
    (returning `{ groups:[{code,label}], roles:[{code,label,group}] }`) and the
    legacy `GROUP_REMAP` aliasing moves into the seed. **Keep** `ROLE_TAG`
    (role → tag color/style) client-side as presentation.

- **`data/projectDefaults.ts`**
  - **Delete:** `FALLBACK_PROJECT_ID = 'lucis'`. Require a real study id from the
    URL/route; render an explicit empty/"select a study" state when absent
    rather than defaulting to a tenant slug.
  - `BLANK_DEFAULTS` already holds only empty values; keep as the neutral scaffold
    (no hardcoded partner content) but confirm no fake strings remain.

### Loading / empty states
Use the existing loading indicator + EmptyState pattern while catalogs fetch.
Cohort-derived options render empty when the cohort is empty.

## Stays client-side (justified)

- React icon maps (`DESIGN_ICON`, `SOURCE_META` icon names)
- Color palettes (`COVERAGE_PALETTE`, `ET_COLORS`, `TONE`, design colors)
- Routing graph: `lib/nav.js` (`VIEW_ORDER`, `WORKFLOW`, `VIEW_LABEL`),
  `shell/sections.js` (`WORKSPACE_SECTIONS`)
- `SOURCE_BADGES` markdown regex, `relTime` / `humanize` formatting helpers

These are code/presentation tied to the React component tree; serializing them to
the backend would break the app or be over-engineering.

## Rollout

- Branch `frontend-real-only-cleanup` off `Quentin`. Do not stage the unrelated
  in-flight files.
- Backend verify: `pytest` (unit + route tests pass).
- Frontend verify: `vite build` succeeds; preview smoke — open the affected
  views, confirm catalogs render from the API (network shows `/reference/*`
  calls) and no console errors; confirm no view crashes when a catalog/cohort is
  empty.

## Risks

- A catalog field used by a view but not seeded → view renders blank. Mitigation:
  seed values are copied verbatim from the current frontend constants.
- Consumers of `config.js` `ESTIMATORS` outside the two named files. Mitigation:
  grep for `ESTIMATORS` / `ESTIMATOR_FILTER` imports before deletion.
- `fetchCohort` shape may not expose the columns needed to derive exposure /
  population options. Mitigation: inspect `cohortData.js` in phase 3; fall back
  to an empty picker (not a hardcoded list) if a value is unavailable.
