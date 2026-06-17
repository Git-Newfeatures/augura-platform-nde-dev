# Subsystem A3 — Data-Quality engine (core) — Design

**Date:** 2026-06-17
**Status:** Proposed (awaiting review)
**Part of:** Subsystem **A**, slice **A3**. Depends on A1 (taxonomy / `dq_constraints`) + A2 (uploaded+parsed datasets). Scope (confirmed): **A3 core** — engine + data-only checks now; concept-coupled checks fold in with A4.

## Context

Port the MVP `src/dq/*` pipeline to Python: re-parse a stored dataset, compute a full DQ profile, run a planned set of checks, score the result across quality dimensions, and persist a **DQ bundle** (auditable, provenance-tracked). Runs as a background **job** (reusing the merged in-process job engine). The MVP runs client-side over in-memory rows; we run server-side over the file stored in A2.

## Scope decision & sub-decomposition

A3-core is large, so it builds as two internal sub-slices (each its own plan + build + validation):

- **A3a — DQ pipeline skeleton (first build):** `dq_bundles` table + RLS; full DQ **profiler** (quartiles/IQR, sentinels, numeric vectors); a **check framework** (planner + registry + finding/provenance + scorer + config + bundle-sealer + engine); a **starter set of data-only checks** — `DQ_FILE_002` (fingerprint), `DQ_MISS_001` (missing rate), `DQ_MISS_003` (mostly-missing), `DQ_RANGE_002` (IQR outliers); the **job** (`dq_profile` kind) + **endpoints** (`POST /datasets/{id}/dq`, `GET /datasets/{id}/dq`). Produces a real scored bundle end-to-end.
- **A3b — remaining data-only checks:** `DQ_FILE_001/003`, `DQ_TYPE_002`, `DQ_MISS_002/004/005/007`. Slot into the registry built in A3a.

**Concept-coupled checks** (`DQ_TYPE_001/003`, `DQ_UNIT_*`, `DQ_RANGE_001`, `DQ_MEAN_*`, `DQ_COH_*`, `DQ_CONS_001/007+`, `DQ_MISS_006`, full grain inference) and **grain inference** are deferred to A4 / a later A-phase — they need column→concept mappings + units/valid-values.

This spec covers the full A3-core architecture; the plan that follows implements **A3a** first.

## Architecture

New module `apps/api/src/augura_api/modules/dq/` (vertical slice). Files:
- `models.py` — `DqBundle` ORM.
- `schemas.py` — `Finding`, `DqBundleOut`, `DqRunResult`, dimension/summary models.
- `profiler.py` — full column profiler (port of MVP `profiler.js`): type flags, `missing_rate`, `sentinel_count`, `numeric_values`, `num_summary{min,max,mean,median,q1,q3,iqr,std_dev}`, `unique_values/count`, `sample_values`, `heuristic_role`.
- `config.py` — `WEIGHT_PROFILES`, `DIMENSION_CATEGORIES`, `THRESHOLDS`, `SEVERITY_DEDUCTIONS` (exact values from MVP `dq-config.js`).
- `provenance.py` — `make_finding(...)` producing the exact finding shape (id, check_id, category, scope, table, column, severity, message, evidence, affected_count/proportion, handling_status, policy_version).
- `scorer.py` — `compute_dq_score(findings, profile)` → `{overall, dimensions{score,weight,finding_counts}}` (exact formula: per-dimension start 1.0, subtract `SEVERITY_DEDUCTIONS`, clamp ≥0; overall = Σ score×weight).
- `checks/` — one module per scope; each check = `{id, category, severity, scope, trigger(ctx), run(ctx)->list[Finding]}` registered in a `REGISTRY`. A3a ships the 4 starter checks; A3b adds the rest.
- `planner.py` — `build_check_plan(constraints, profile)` from `dq_constraints` (A1), gating by **data-only** `applies_when` only (concept-dependent conditions skip when no concept). Plan item shape per MVP.
- `registry.py` — dispatch (`evaluate_check`) with execution audit (evaluations/triggered/findings/errors).
- `engine.py` — `run_dq(sheets, columns, constraints, weight_profile) -> bundle`: file→column→(cross-column/table/dataset) scopes, assemble bundle (meta/summary/check_plan/tables/cross_table_findings/provenance), score, seal.
- `service.py` — `DqService`: load dataset (A2) → `core.storage.read_bytes` → `parse_upload` → profile → `run_dq` → persist `DqBundle` (+ optional `artifacts` provenance row) → return.
- `repo.py` — `create_bundle`, `latest_for_dataset`, `get_bundle`.
- `router.py` — endpoints below.

### DB — `dq_bundles` (added to `schema.sql`, tenant-scoped)
```sql
create table if not exists dq_bundles (
    id           uuid primary key default gen_random_uuid(),
    org_id       uuid not null references orgs(id) on delete cascade,
    dataset_id   uuid not null references datasets(id) on delete cascade,
    score_profile text not null default 'exploratory',
    overall_score numeric,
    status       text not null default 'draft' check (status in ('draft','sealed')),
    requires_resolution boolean not null default false,
    bundle       jsonb not null,           -- full bundle (findings, check_plan, tables…)
    created_at   timestamptz not null default now()
);
```
RLS: tenant-scoped (the standard `tenant_isolation` policy via `org_id`) — add `dq_bundles` to the policies loop + to `EXPECTED_TABLES`/`RLS_REQUIRED` in the bundle test.

### Job
Register a `dq_profile` job kind in the job engine (`jobs/handlers.py`): payload `{dataset_id}` → `DqService.run(...)` → writes a `DqBundle`, sets job result_ref to the bundle id. `POST /datasets/{id}/dq` enqueues it (idempotent per dataset+file fingerprint). For A3a, the run may execute **synchronously** within the endpoint if the job engine's async path isn't wired for this kind yet — decide at plan time based on the merged `jobs/runner.py` capabilities (prefer the job path for consistency with simulation/documents).

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/datasets/{dataset_id}/dq` | Run DQ on the dataset's stored file → bundle (via job or sync); returns `DqRunResult{bundle_id, status, overall_score}` |
| `GET`  | `/datasets/{dataset_id}/dq` | Latest `DqBundleOut` for the dataset (404 if none) |

## Data shapes (exact, from MVP)
- **Finding:** `id, check_id, category, scope, table, column, columns?, concept_id?, severity('info'|'soft'|'hard'), message, evidence(dict), affected_count?, affected_proportion?, handling_status('open'), policy_version('1.0.0')`.
- **Bundle:** `meta{bundle_id, created_at, policy_version, dataset_fingerprint, score_profile, status}`, `summary{overall_score, dimensions{completeness,validity,consistency,coherence,labelling →{score,weight,finding_counts}}, hard_findings_total, requires_resolution}`, `check_plan{generated_at,total_planned,total_skipped,by_scope,items[],execution{...}}`, `tables[{table_label,grain,columns[{column,type,missing_rate,outlier_count,findings[]}],cross_column_findings[],table_findings[]}]`, `cross_table_findings[]`, `provenance[]`.
- **Config:** weights `exploratory{completeness .25,validity .25,consistency .20,coherence .15,labelling .15}` / `regulatory{.20,.35,.30,.10,.05}`; `DIMENSION_CATEGORIES{completeness:[missing], validity:[type,unit,range], consistency:[consistency], coherence:[coherence], labelling:[labelling]}`; `THRESHOLDS{mostly_missing .70, outlier_iqr_factor 3.0, max_evidence_rows 10}`; `SEVERITY_DEDUCTIONS{hard .10, soft .03, info 0}`.

## Starter checks (A3a) — all data-only
- **DQ_FILE_002** (file, info): dataset fingerprint (SHA-256 of raw bytes) → evidence `{sha256}`.
- **DQ_MISS_001** (column, info/soft/hard): missing rate; severity `>0.50 hard, >0.05 soft, else info`.
- **DQ_MISS_003** (column, hard): `missing_rate > 0.70`.
- **DQ_RANGE_002** (column, soft): IQR outliers, fences `q1 - 3·iqr` / `q3 + 3·iqr`; evidence with fences + samples; `affected_count/proportion`.

## Error handling
- 404 if dataset not found / no stored file; 401 unauth; bundle run errors → job `failed` (or 500 with problem+json if sync). Re-parse failures surface as A2's 4xx.

## Testing
- **Unit:** profiler (quartiles/IQR, sentinels, numeric vectors); scorer (per-dimension deduction + weighted overall, exact numbers); each starter check (trigger + finding); planner (data-only gating skips concept conditions); registry (audit increments, error capture).
- **Route:** `POST/GET /datasets/{id}/dq` in OpenAPI + 401.
- **Integration (DB):** upload (A2) → run DQ → `dq_bundles` row persisted, `overall_score` in [0,1], findings present, tenant-scoped (RLS write/read).
- **DB bundle test:** `dq_bundles` in `EXPECTED_TABLES` + RLS asserted.
- **api-client** regenerated (clean worktree).
- **Real-DB validation:** pgvector — apply bundle, upload a CSV, run DQ, assert a scored bundle persisted.

## Acceptance criteria (A3a)
1. `dq_bundles` table + RLS in the bundle; `EXPECTED_TABLES` updated.
2. `POST /datasets/{id}/dq` produces a scored, persisted bundle with the 4 starter checks; `GET` returns it.
3. Profiler + scorer + planner + registry + engine unit-tested; exact MVP formulas.
4. api-client regenerated; drift-check green.
5. Real-DB validation green (upload → DQ run → bundle persisted under RLS).

## Risks / open items
- **Job vs sync:** prefer the merged job engine; fall back to sync run if the `dq_profile` kind isn't trivially wireable — decide at plan time from `jobs/runner.py`/`handlers.py`.
- **Re-parsing cost:** DQ re-parses the stored file each run; fine for A2's size cap. Large-file streaming is a later concern.
- **Grain inference deferred:** `tables[].grain` is `null`/minimal in A3-core (full grain needs concepts+archetypes → A4).
- **Profiler duplication:** A3's full profiler vs A2's lean persisted profiler — kept separate (A2 persists `dataset_columns` stats; A3's profiler is transient DQ computation). Could converge later; not now.
