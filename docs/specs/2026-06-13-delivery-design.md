# Augura Platform — Delivery design (complete backend)

**Date**: 2026-06-13
**Status**: validated (go Quentin)
**Scope**: turn the validated architecture spec (`2026-06-11-augura-backend-architecture-design.md`) into an executable implementation program, phase by phase, up to the complete production backend + migrated frontend + exportable Supabase database.
**Reference**: this document complements the spec; it does not replace it. The spec describes the end state; this document describes *how we get there* and freezes the concrete schema + the data contract.

---

## 1. Scoping decisions (2026-06-13)

| # | Topic | Decision |
|---|-------|----------|
| D1 | Delivery scope | **Everything**, LLM agents included (the 7 modules + the 4 agents) |
| D2 | Database target | **SQL/Alembic artifacts only** — no existing database touched, no local Docker/Postgres started on the dev machine |
| D3 | Frontend | **Migration `lucis-dashboard` → `apps/web`** without a mock layer; `lucis-dashboard` stays frozen as a pure demo |
| D4 | Auth | **Supabase Auth + JWKS verification + RLS** end-to-end |

Consequence of D1 + D2: the backend is delivered as **code + tests**. Verification relies on strict pyright + ruff + import-linter + pytest (logic/contract/LLM-agents mocked locally; repos+RLS wired in the GitHub Actions CI with a `postgres` service, not run locally). No live end-to-end run until the user has created their Supabase instance and provided the LLM keys.

## 2. Phase breakdown (spec §12 mapped onto D1)

| Phase | Content | End deliverable |
|---|---|---|
| **P1 — Scaffold** | `apps/api` (uv, src layout), CI (ruff/strict pyright/import-linter/pytest), `core/` (fail-fast config, structlog logging, RFC 9457 errors), `modal_app.py` | green `pytest`, green quality gates, servable healthcheck |
| **P2 — Data foundation + auth + studies + web boot** | `core/db` (async engine, `SET LOCAL app.tenant_id`), `core/auth` (JWKS), `core/tenancy`, **Alembic = complete schema + RLS**, `studies` module (CRUD + versioned `study_state`), generated TS client, `lucis-dashboard`→`apps/web` migration without mocks, **Supabase SQL bundle** | migrated frontend boots (Supabase login, study list via API); `supabase/*.sql` exported |
| **P3 — datasets + corpus** | `datasets` (upload, column profiling, mapping), cohort tables + seed, `corpus` (documents/chunks, feed, coverage, sources, `match_chunks` pgvector) | frontend data endpoints served on seeded Postgres |
| **P4 — agents** | typed async Anthropic runtime; `dag`, `gap-detection`, `variable-check` (forced-tool, Pydantic + repair retry, `agent_cache`, `agent_runs`); `trace` E1 multi-turn SSE/NDJSON last | green characterization golden tests against the JS handlers |
| **P5 — simulation + jobs** | `jobs` infra (idempotency), on-demand bootstrap (port of `run_bootstrap.py`), analytic power calibrated per outcome (fix T4) | on-demand simulation + result reads |
| **P6 — documents + analytics** | protocol/report generation (WeasyPrint/python-docx), `usage_events`, `outbox` audit, `admin-stats`, token-cost views | exportable dossiers; admin populated |
| **P7 — parity + cutover** | green golden + Playwright e2e, RLS isolation tests, `lucis-dashboard` frozen as a pure demo | cutover criterion met |

Each phase gets its own written plan (`writing-plans` skill) just before execution, then is executed in TDD with atomic commits (no co-author trailer, Quentin's preference). Report at every phase boundary.

## 3. Complete data schema (19 tables)

Every tenant-scoped table carries an RLS policy based on `current_setting('app.tenant_id')`. `documents`/`chunks` have a **nullable** `org_id` ⇒ global corpus readable by all tenants.

### Tenancy
- **orgs** — `id, name, slug, cesl_profile jsonb, created_at`. Serves `/api/tenant`.
- **memberships** — `id, org_id→orgs, user_id (auth.users), role(owner|member|viewer), created_at`.

### Studies
- **studies** — `id, org_id, name, slug, tagline, category, framework, n_subjects, lead, status, created_by, created_at, updated_at`. Replaces `cockpitData` + `augura_new_studies`.
- **study_members** — `id, study_id, user_id, role`.
- **study_state** — `id, study_id, version, state jsonb, created_by, created_at`. Replaces the `sessionStorage augura_session_v3_*` (profileReady, e1Profile, studyType, selectedEstimators, lockedEstimator, selectedOutcome, simResults, uploadedData, variableMappings, variableCheckResult, dagCache, cqExposure, cqPopulation…).

### Datasets
- **datasets** — `id, org_id, study_id?, name, storage_path, row_count, status, created_at`.
- **dataset_columns** — `id, dataset_id, sheet, name, value_kind, n_total, n_non_null, null_pct, n_distinct, min, max, top_values jsonb, proposed_role, proposed_group, proposed_canonical_id, confidence, rationale, user_decision(pending|confirmed|rejected), final_role, final_canonical_id`.
- **cohort_members** (= `validation_members`) — `id, org_id, dataset_id, cohort_name, member_id, age, sex, bmi, engagement_group, country`.
- **cohort_biomarkers** (= `validation_biomarkers`) — `id, org_id, dataset_id, cohort_name, member_id, timepoint_months, hba1c_pct, ldl_mgdl, hs_crp_mgl, adherence_pct`.

### Corpus
- **documents** — `id, org_id?, source_id, evidence_type, jurisdiction, lifecycle, title, summary, url, published_at, ingested_at, priority_score, is_new`. Serves `pulse-feed`, `coverage-map`, `corpus-sources`.
- **chunks** — `id, document_id, org_id?, content, embedding vector(1536), token_count`. **HNSW** index on `embedding`. Serves `match_chunks`.

### Agents
- **agent_runs** — `id, org_id, study_id?, agent_type, model, status, duration_ms, input_tokens, output_tokens, cost_usd, created_at`.
- **agent_cache** — `id, agent_type, input_hash unique, response jsonb, created_at` (fix U2: deterministic agents served from cache).

### Simulation
- **simulation_runs** — `id, org_id, study_id, params jsonb, job_id?, status, results jsonb, created_at`. On-demand bootstrap.
- **simulation_results** — `id, org_id, cohort_name, scenario, estimator, effect_size, ci_lower, ci_upper, power, p_value`. Seeded read-model for the frontend's VALIDATED mode (3 scenarios × 4 estimators = 12 rows).

### Jobs
- **jobs** — `id, org_id, type, status(queued|running|succeeded|failed), progress, payload jsonb, result_ref, error, idempotency_key unique, modal_call_id, created_at, updated_at`.

### Generated documents
- **generated_documents** — `id, org_id, study_id, type(protocol|report), storage_path, status, created_at`.

### Analytics / observability
- **usage_events** — `id, user_id?, org_id?, event_type, route, metadata jsonb, created_at`. Serves `admin-stats`.
- **outbox_events** — `id, aggregate_type, aggregate_id, event_type, payload jsonb, created_at, processed_at`. Audit trail.

### Functions / views
- `match_chunks(query_embedding vector(1536), match_count int, filter jsonb)` — pgvector search.
- `coverage_map` — view/aggregate (jurisdiction × evidence_type → doc_count, gap_score, gap_severity), including zero cells.

## 4. Frontend → backend → table contract

| Frontend (current mock) | FastAPI endpoint | Table(s) |
|---|---|---|
| `GET /api/tenant?projectId=` | `GET /orgs/{slug}` | `orgs.cesl_profile` |
| `GET /api/pulse-feed` | `GET /corpus/feed` (keyset) | `documents` |
| `GET /api/coverage-map` · `/api/corpus-sources` | `GET /corpus/coverage` · `/corpus/sources` | `documents` (aggregated) |
| `GET /api/study-designs` · `/api/cesl-sources` | `GET /catalogs/*` | static catalogs |
| `POST /api/dag` · `/gap-detection` · `/variable-check` | `POST /agents/{dag,gaps,variable-check}` | `agent_runs`, `agent_cache`, `study_state` |
| `POST /api/trace` (SSE) | `POST /agents/profiling/stream` (SSE NDJSON) | `agent_runs`, `study_state` |
| `POST /api/supabase` (match_chunks) | `POST /corpus/search` | `chunks` |
| `POST /api/anthropic` · `/api/openai` | internalized (no more generic proxy exposed to the browser) | — |
| Supabase REST `validation_members/biomarkers` | `GET /datasets/{id}/cohort` | `cohort_*` |
| `simulation_results` (VALIDATED) | `GET /simulations/results` | `simulation_results` |
| `POST /simulations` (on-demand) | `POST /simulations` → `202 {job_id}` | `simulation_runs`, `jobs` |
| `sessionStorage augura_session_v3` | `GET/PUT /studies/{id}/state` | `study_state` |
| `GET /api/admin-stats` | `GET /analytics/admin` | `usage_events` |

## 5. Supabase deliverable (D2)

Alembic = source of truth. A derived bundle, ready to paste into a new Supabase project, is generated under `apps/api/supabase/`:
- `schema.sql` — extensions (`pgvector`, `pgcrypto`), tables, HNSW index.
- `policies.sql` — RLS policies + non-exempt connection role.
- `functions.sql` — `match_chunks`, `coverage_map` view.
- `seed.sql` — corpus + cohort + `simulation_results`, derived from the existing local data.

No existing database is touched. No Docker is started on the dev machine.

## 6. Verification strategy (under the D1+D2 constraints)

- **Local**: strict pyright, ruff, import-linter, pytest (business logic, Pydantic validation, agents with mocked LLM, DDL parsing).
- **CI (GitHub Actions)**: `postgres` 16 + pgvector service → dedicated repo tests + RLS isolation (one tenant never reads another); applying the `supabase/*.sql` bundle to this Postgres to prove it is valid.
- **Characterization**: `src/mocks/apiFixtures.js` → golden files; FastAPI must return the same thing as the JS routes (gaps listed and accepted).
- **Agents**: `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` keys required for a live run; absent from the current `.env.local` ⇒ validated structurally until provided.

## 7. Out of scope for this delivery

Unchanged from spec §13. In addition: no live Modal deployment until the user has authenticated Modal (the `modal_app.py` is delivered and ready).
