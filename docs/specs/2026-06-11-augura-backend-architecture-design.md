# Augura Platform — Backend architecture

**Date**: 2026-06-11
**Status**: validated (brainstorm Quentin × Claude)
**Scope**: architecture of Augura's new production backend and of the monorepo that hosts it. This document is the reference for the implementation plan.

---

## 1. Context and motivation

Augura (current repo `lucis-dashboard`) is a clinical-study design support platform: a multi-phase workflow (E1 profiling → risks → outcome → causal DAG → design → simulation → results), LLM agents backed by an evidence corpus (PubMed, MAUDE, FDA Guidance, ClinicalTrials.gov) indexed in pgvector.

The current architecture is an unacknowledged JS/Python split:

- 11 Vercel serverless functions in JS (`api/*.js`): agents (E1 trace in SSE, dag, gap-detection, variable-check), Anthropic/OpenAI proxies, vector search;
- offline Python scripts (`simulation/run_bootstrap.py`: bootstrap N=1000, numpy/scipy/statsmodels) with no link to the API;
- limits reached: Vercel 300 s timeout on `trace.js`, no mechanism for long-running jobs or cron, RLS disabled (bug T1), workflow state in browser sessionStorage, demo mode intertwined with production code, manual mock fixtures per route.

Decision: rebuild the backend as a **Python/FastAPI modular monolith**, in a **new monorepo**, deployed on **Modal**, with **Supabase** (new instance) as the database and auth. **Big bang** migration tooled by characterization tests. The current repo `lucis-dashboard` becomes a **pure frontend demo** (mocks), with no link to the production backend.

## 2. Settled decisions

| # | Topic | Decision |
|---|-------|----------|
| 1 | Scope | Fully replace Augura's backend (Vercel functions + Python scripts) |
| 2 | Strategy | Big bang in a new project; parity proven before cutover |
| 3 | Demo | No demo mode in the backend; the demo = standalone frontend (frozen lucis-dashboard) |
| 4 | New capabilities | On-demand simulation · self-service corpus · document generation · multi-study & collaboration |
| 5 | Production frontend | Migrated into the monorepo (`apps/web`), stripped of mocks |
| 6 | Database | New dedicated prod Supabase instance + separate dev environment, versioned migrations from day 1 |
| 7 | Data access | Everything goes through FastAPI (single door); RLS kept as defense in depth |
| 8 | Auth | Supabase Auth on the frontend; FastAPI verifies the JWT (JWKS); server-side tenant scoping |
| 9 | Internal structure | Modular monolith in vertical slices; boundaries verified by import-linter |
| 10 | Data layer | SQLAlchemy 2.0 async (asyncpg) + Alembic |
| 11 | Agents runtime | Async Anthropic SDK + in-house typed runtime (port of `agents/runtime/anthropic.js`); neither pydantic-ai nor LangGraph |

## 3. Why Python (vs Node.js / Go)

1. **The business core is already in Python and it is not transportable**: ATE/ATT/LME/IPW estimators, parametric bootstrap, power analysis = scipy/statsmodels/sklearn. No credible equivalent in JS; gonum (Go) is embryonic. Any other choice imposes two runtimes for life.
2. **The AI ecosystem is first-class**: Anthropic SDK, Pydantic validation of agents' structured outputs, LangSmith, embedding pipelines.
3. **The type contract**: Pydantic v2 → OpenAPI → generated TypeScript client. Runtime validation + documentation + generation in a single move.
4. **Python's "slowness" is irrelevant here**: I/O-bound backend (latency dominated by the LLMs and the DB) → asyncio is more than enough; compute-bound vectorized numpy (C under the hood). Go would only win on massive CPU-light HTTP throughput, which is not Augura's profile (B2B, low volume).
5. **Modal is Python-native**: ASGI API in one decorator, long-running jobs without Celery/Redis, integrated cron, accessible GPU.

Acknowledged concessions: Node would have given type sharing without generation and shorter cold starts; Go a static binary and minimal RAM. None of them offsets point 1.

## 4. Monorepo

```
augura-platform/
├── apps/
│   ├── api/                          # FastAPI monolith
│   │   ├── src/augura_api/
│   │   │   ├── core/                 # technical foundation, zero business logic
│   │   │   │   ├── config.py         # pydantic-settings, fail-fast at boot
│   │   │   │   ├── db.py             # async engine, session/request, SET LOCAL tenant
│   │   │   │   ├── auth.py           # Supabase JWT verification (JWKS)
│   │   │   │   ├── tenancy.py        # CurrentTenant dependency
│   │   │   │   ├── errors.py         # AppError hierarchy + RFC 9457 handlers
│   │   │   │   ├── logging.py        # structlog JSON + request_id
│   │   │   │   ├── llm/              # Anthropic/OpenAI client, agents runtime, SSE
│   │   │   │   └── events.py         # domain events → outbox
│   │   │   ├── modules/
│   │   │   │   ├── studies/  datasets/  corpus/  agents/
│   │   │   │   ├── simulation/  documents/  analytics/
│   │   │   │   └── (each module: __init__.py · router.py · service.py
│   │   │   │        · schemas.py · repo.py · models.py)
│   │   │   ├── jobs/                 # Modal Functions entrypoints (thin adapters)
│   │   │   └── main.py               # composition root
│   │   ├── alembic/                  # versioned migrations (schema + RLS policies)
│   │   ├── tests/
│   │   ├── modal_app.py              # ASGI app + Functions + Cron
│   │   └── pyproject.toml            # uv ; strict pyright ; ruff
│   └── web/                          # migrated React 19 + Vite frontend, without mock layer
├── packages/
│   └── api-client/                   # TS generated from OpenAPI — never hand-edited
└── .github/workflows/                # CI: lint, typecheck, tests, drift check, deploy
```

### Boundary rules (what makes the monolith "modular")

- A module imports only `core` and the public interface (`__init__.py`) of other modules — never their internals. `import-linter` breaks CI on violation.
- `core` imports no module.
- `router.py` and `jobs/*` are thin adapters (HTTP / Modal); the logic lives in `service.py`.
- `repo.py` is the module's sole DB access point; each method requires a `TenantId`.
- SQLAlchemy models never leave a module; boundaries exchange Pydantic schemas.
- A module that has grown too large is extractable into a separate service without rewriting: its public contract already exists.

## 5. Modules and responsibilities

| Module | Responsibility | Notes |
|--------|----------------|-------|
| `studies` | Study lifecycle, persisted and versioned workflow state, members/roles per study | Replaces sessionStorage; unlocks multi-device and collaboration |
| `datasets` | Cohort upload (Supabase Storage), pandas parsing/validation off the event loop, column profile, variable mapping | |
| `corpus` | Self-service ingestion (PDF → extraction → chunking → embeddings → pgvector), direct SQL retrieval, shared global corpus + private per-tenant corpus | `match_chunks` becomes a SQLAlchemy/pgvector query |
| `agents` | E1 profiling (multi-turn SSE), DAG, gap-detection, variable-check on a common runtime | Pydantic-validated outputs + 1 "repair" retry; NDJSON protocol identical to the current one |
| `simulation` | On-demand bootstrap (Modal job), synchronous analytic approximation calibrated **per outcome** (fix T4), result reads | Port of `run_bootstrap.py` |
| `documents` | Protocol/report generation: study state → LLM + template → PDF (WeasyPrint) / Word (python-docx) → Storage → signed URL | Asynchronous (job) |
| `analytics` | Authenticated usage events, audit trail via outbox, admin stats, token costs per agent run | Replaces the soft-auth |

## 6. Data model (main tables)

- **Tenancy**: `orgs`, `memberships` (user ↔ org, owner/member/viewer role)
- **Studies**: `studies`, `study_members`, `study_state` (versioned workflow, JSONB)
- **Data**: `datasets`, `dataset_columns`
- **Corpus**: `documents`, `chunks` (pgvector embedding, HNSW index; nullable `tenant_id` → global corpus)
- **Jobs**: `jobs` (type, status queued/running/succeeded/failed, progress, payload, result_ref, error, `idempotency_key`, `modal_call_id`)
- **Simulation**: `simulation_runs` (JSONB params, job link, results)
- **Generated documents**: `generated_documents` (type, storage_path, status)
- **Business observability**: `usage_events`, `outbox_events`, `agent_runs` (duration, tokens, cost)

Every tenant-scoped table carries an RLS policy based on `current_setting('app.tenant_id')`.

### Migrating the existing data

- Corpus (`documents` + `chunks` + embeddings): dump/restore to the new instance — **no re-embedding**.
- Cohorts and validation data: re-upload via the existing scripts, adapted.
- Precomputed `simulation_results`: not migrated (replaced by on-demand simulation); the demo keeps its own as fixtures.

## 7. Auth and tenancy

1. The frontend uses Supabase Auth (login, session, refresh) and sends the JWT as `Authorization: Bearer`.
2. `core/auth.py` verifies signature (Supabase JWKS, cache), expiration, audience → `UserId`.
3. `core/tenancy.py` resolves the membership (`memberships`) → `CurrentTenant` injected into the routes.
4. `core/db.py` runs `SET LOCAL app.tenant_id = :tid` when opening each transaction; the RLS policies hang off it. The API connects with a dedicated Postgres role **not exempt from RLS** (not service_role).
5. Result: scoping is applied twice (repos + RLS). Forgetting a filter in a service cannot leak cross-tenant data.

## 8. Key flows

**Standard request** — generated client → JWT → tenant → service → repo → Pydantic response. p95 budget < 300 ms excluding LLM.

**E1 agent (SSE)** — `POST /agents/profiling/stream` → tool-use loop (the retrieval tool calls `corpus`'s public interface) → streamed NDJSON events (heartbeats; always ending with `done` or `error`) → result persisted into `study_state`. No more 300 s ceiling. First token < 2 s.

**Job (simulation, ingestion, export)** — `POST /simulations` → insert `jobs` + `Function.spawn(job_id)` → `202 {job_id}` → the worker updates `progress` → tracked by polling `GET /jobs/{id}` (SSE possible later). Mandatory idempotency key on job POSTs: a double-click does not launch two bootstraps.

## 9. Robustness rules

### Typing
- pyright **strict** in CI; ruff (lint + format).
- Pydantic v2 at every boundary: requests, responses, settings, job payloads, agent outputs.
- `NewType` for `TenantId`, `StudyId`, `UserId`, `JobId`.
- `Any` and `type: ignore` forbidden except with a justifying comment.
- TS client generated from OpenAPI (`openapi-typescript`); CI fails if the committed client has drifted from the contract (drift check). The frontend never hand-writes a call.

### Execution
- Async end-to-end (httpx, async Anthropic SDK, asyncpg). The event loop only does I/O.
- Any computation > ~100 ms leaves the API: thread (`anyio.to_thread`) for Excel parsing, Modal job for the bootstrap and ingestion.
- Caching of deterministic agent responses (same inputs → response served from the cache table; fix U2).
- Keyset pagination; pgvector HNSW index.

### Errors
- `AppError(code, http_status, message, details)` hierarchy → global handler → uniform **Problem Details (RFC 9457)** responses.
- LLM: SDK retries + per-call timeout; upstream unavailability → explicit 503, never an infinite wait.
- Invalid structured outputs: 1 "repair" retry with the validation error injected, then a clean failure.
- Jobs: `failed` status + detailed error + Sentry alert; manual relaunch.

## 10. Deployment (Modal) and observability

- `modal_app.py`: the API in `@modal.asgi_app()` (lightweight uv image); the jobs in `modal.Function` with a separate scientific image (numpy/scipy/statsmodels — the API image stays thin); `modal.Cron` for the recurring work (e.g. public corpus refresh).
- Modal `dev` / `prod` environments: separate secrets (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `SUPABASE_JWT_*`), separate Supabase instances.
- Prod: `min_containers=1` (no user-facing cold start); dev: scale-to-zero.
- GitHub Actions CI: ruff + pyright + pytest + import-linter + drift check → `modal deploy` on `main`. Frontend: Vercel (static), `VITE_API_URL` → custom Modal domain.
- Observability: structlog JSON + request_id, Sentry (errors), LangSmith (agent traces), `agent_runs` (costs/latencies in the DB).

## 11. Test strategy — the big-bang safety net

1. **Characterization**: the current fixtures (`src/mocks/apiFixtures.js`) become golden files; FastAPI must return the same thing as the JS routes, up to the schema. The gaps are listed and accepted, never accidental.
2. **Repos + RLS**: pytest + ephemeral Postgres; the RLS policies are tested explicitly (one tenant never reads another).
3. **Contract**: the generated TS client compiles against `apps/web`; drift check in CI.
4. **New business logic in TDD**: per-outcome calibration, analytic power, job idempotency.
5. **E2E**: the existing Playwright rewired onto the new backend.
6. **Cutover criterion**: golden tests + e2e green, RLS verified. Until it is green, the old backend stays in service.

## 12. Sequencing

1. Scaffold monorepo + CI + Modal hello world (plumbing first)
2. `core` + auth + tenancy + minimal `studies` + generated client → the migrated frontend boots (login, study list)
3. `datasets` + `corpus` + transfer of the existing corpus
4. `agents` (characterization first; E1 SSE last of the four)
5. `simulation` + jobs infra
6. `documents` + `analytics`
7. Parity proven → cutover of the prod frontend → `lucis-dashboard` frozen as a pure demo

## 13. Out of scope (non-goals)

- No microservices, no message broker, no Kubernetes: the modular monolith + Modal Functions cover the needs; extracting a module will remain possible thanks to the boundaries.
- No demo mode, soft-auth or fixtures in the backend.
- No rewrite of the frontend design system (already done on `quentin-workspace`).
- No SSE on job tracking in v1 (polling is enough; the upgrade is local to the module).
- The iOS/Apple Health app is not in this scope; if it arrives, it will consume the same API (the OpenAPI contract is already the single door).

## 14. Risks and mitigations

| Risk | Mitigation |
|--------|------------|
| Big bang that drags on | Sequencing by deliverable modules; the old backend stays in service until the cutover criterion |
| SSE protocol drift (the current frontend depends on the existing NDJSON) | Characterize the `trace.js` flow event by event before the port |
| Modal cold starts / latency | `min_containers=1` in prod; minimal API image (uv, without scientific deps) |
| Invisible LLM costs | `agent_runs` traces tokens and cost per run; admin view in `analytics` |
| Misconfigured RLS | Policies written into the Alembic migrations + dedicated isolation tests; non-exempt connection role |
| Re-paying for embeddings | Corpus dump/restore, never re-embedding |
