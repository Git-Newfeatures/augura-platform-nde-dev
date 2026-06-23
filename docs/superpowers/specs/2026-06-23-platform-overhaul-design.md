# Platform Overhaul — Modular, Reliable, Sustainable

Date: 2026-06-23
Status: approved (roadmap + sequencing), ready for per-phase planning
Scope: whole monorepo (`apps/api`, `apps/web`, DB bundle, CI/infra/deploy)

## Goal

A full audit-driven hardening of the Augura platform along three axes — **modular**
(clear boundaries, no god-files), **reliable** (no event-loop stalls, no silently
swallowed errors, no schema/deploy drift), **sustainable** (tests, CI coverage,
single sources of truth, no dead/mock code). Executed in safe, gated increments,
safety net first.

## How we got here

Four parallel read-only audits (backend, frontend, DB, CI/infra). Key meta-result:
backend, DB, and backend-CI are in good shape; risk is concentrated in the frontend
(no tests / not in CI / god-components), the deploy path (fragile, unpinned, no
migration step), and a handful of reliability bugs. **No RLS isolation hole and no
committed secret were found.**

### Confirmed healthy (do not touch)
- RLS isolation: all 56 tables `force row level security`; GUCs fail *closed* when
  unset; gate-9 per-study policy correct; cross-tenant isolation proven in CI on real
  pgvector.
- No schema/model drift today; no committed secrets (only `.env.example`).
- Backend CI strong: ruff + pyright strict + import-linter + pytest + `db-bundle`.
  The OpenAPI **drift-check exists and is robust** (regenerates + `git diff --exit-code`
  + `tsc --noEmit`).
- `core/` never imports modules/jobs; all routes auth-gated; no SQL-injection vector;
  integration tests hard-fail if pointed at the prod project ref.

## Decisions

- **Sequencing**: 0 → 1 → 2 → 3 → 4 (safety net before risky refactors).
- **Phase 4 depth**: high-value slices only. **YAGNI / out of scope**: full TypeScript
  migration of the frontend, and full consolidation onto one UI system
  (`theme.js` + `src/ui/*` deletion). These are explicitly deferred — we do the
  high-value slice (type the API boundary; opportunistic `views/*` migration) instead
  of a big-bang rewrite.
- **Commits**: per `CLAUDE.md`, commit/push/deploy only on explicit request. Each phase
  produces atomic commits *when the user asks*; no auto-commit.
- **Verification gate**: each phase must leave CI green (`ruff format --check`,
  `ruff check`, `pyright`, `lint-imports`, `pytest`, `db-bundle`) before moving on.
  Frontend changes additionally run `npm run lint` + `npm run build` (and, once Phase 1
  lands, the new web CI job).

## Findings → Phase mapping

Severity in brackets. File refs are the anchor for the implementation plan.

### Phase 0 — Quick wins (very low risk, all S)
- [security] Remove `console.log` of URL/hash/href in `apps/web/src/ResetPassword.jsx:8-10`
  (Supabase recovery token lives in the URL fragment).
- [no-mock rule] Replace hardcoded fake clinical rows (`PRIVACY_ROWS`, `VALIDATION_ROWS`,
  `LINEAGE_STEPS`, `LINEAGE_USES`) in `apps/web/src/workspace/DatasetsPage.jsx:131-153`
  with an explicit "coming soon"/empty state for the beta tabs.
- [dead code] Delete orphaned `apps/web/src/workspace/DatasetUpload.jsx` (no import sites).
- [hygiene] Strip non-existent ignore globs + dead `api/agents/tools/test/e2e` group from
  `apps/web/eslint.config.js`; add `no-console` (allow warn/error).
- [reliability] Narrow `apps/api/.../jobs/runner.py:130-135` Modal probe from
  `except Exception` to `except ImportError` so real misconfig doesn't silently fall back
  to BackgroundTasks (which Modal doesn't run → stuck job).
- [reliability] Route the local-disk branch of `apps/api/.../core/storage.py:90-111`
  through `anyio.to_thread.run_sync`; make `storage.exists()` use HEAD, not full GET
  (`storage.py:114-120`).
- [convention] Translate remaining French docstrings/comments to English
  (e.g. `modules/datasets/service.py:1`, `pyproject.toml:3`, scattered).

### Phase 1 — Safety net (low risk)
- [CI] Add a `web` job to `.github/workflows/ci.yml`: `npm ci && npm run lint &&
  npm run build`, triggered on `apps/web/**`.
- [CI] Gate branch `Quentin` (prod deploy source): add to `push:` branches or require
  PRs. Today CI gates only `main` + PRs, so prod code is unverified.
- [CI] Add `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`;
  enable `setup-uv` cache + `setup-node` npm cache.
- [CI] Add a server-side grep step rejecting AI-attribution trailers (enforces the
  `.githooks/commit-msg` rule regardless of local opt-in).
- [DB] Add guard tests (extend `apps/api/tests/db/`):
  - idempotency invariant: every migration ≥0002 uses `IF [NOT] EXISTS` (or allowlisted).
  - seed hygiene: `seed.sql` contains no `insert into <tenant-table>`.
  - schema↔migration: every `create table` in `schema.sql` is produced by some migration
    (or baseline-allowlisted) — converts the "schema.sql bypasses alembic" footgun into a
    CI failure.
  - model↔DB drift: reflect the post-`alembic upgrade head` DB in `db-bundle` and diff
    columns/types against `Base.metadata` (allowlist the intentional partial
    `TaxonomyConcept` mapping).

### Phase 2 — Reliability (medium)
- [High] Move DQ off the event loop: promote `run_dq` to a proper job (consistent with
  simulation) or, as the minimal fix, wrap `parse_upload`+`run_dq` in `run_in_thread`
  (`apps/api/.../modules/dq/service.py:21-54`, router `:23`).
- [Med] Frontend: extend `useCollection`/`useReference` to return `{ data, loading, error }`
  and render a distinct error state with retry (`apps/web/src/workspace/dataClient.js`);
  add a top-level `ErrorBoundary` around `<Routes>` in `App.jsx`; centralize 401 /
  expired-token handling in `apiFetch`.
- [Low] Route `usage_events` telemetry through a backend endpoint instead of direct
  `supabase.from(...).insert(...)` in `apps/web/src/App.jsx:31-35`.
- [Med] Add bounded retry-with-backoff on transient 429/5xx for Anthropic
  (`core/llm/runtime.py`) and NCBI/CT.gov GETs (`modules/corpus/pubmed.py`, `ctgov.py`).
- [Med] Add missing FK/RLS-subquery indexes as idempotent migration `0011` **and** in
  `schema.sql`: `study_members(study_id)`, `chunks(document_id)`, `datasets(study_id)`,
  `generated_documents(study_id)`, `usage_events(org_id)`.

### Phase 3 — Deploy hardening (medium)
- [High] Add an enforced migrate-then-deploy step (privileged one-shot or documented
  `make deploy` that runs `alembic upgrade head` then `modal deploy`, failing the deploy
  on migration error). `apps/api/scripts/deploy_modal.sh`.
- [Med] Build the Modal image from `uv.lock` (e.g. `uv export --frozen` → requirements)
  instead of unpinned `pyproject.toml` ranges (`apps/api/modal_app.py:19`).
- [Med] Move prod secret out of one dev's local `.env`: deploy script *validates* required
  keys; canonical secrets live in a team store. (`deploy_modal.sh:22,45-51`).
- [Med] Add automated post-deploy `/healthz` smoke (fail loudly on non-200) and a
  documented one-line rollback to the prior revision.

### Phase 4 — Modularity, high-value slices (higher risk — per-item sign-off)
- Backend: align documents/simulation/analytics to `XService(XRepo(session))` DI.
- Backend: publish a `datasets.__init__` read interface; route dq/mapping imports through
  it (stop reaching into private repo/models).
- Backend: split `semantic/enrichment.py` (927) → `normalize.py`/`graph.py`/`merge.py`;
  split prompts out of `enrich_propose.py` (879) mirroring `causal/prompt.py`.
- Frontend: extract `LucisApp.jsx` (617, ~25 useState) into `useStudyWorkflowState`,
  `useWorkflowSync`, `useStudyReferences` hooks; hoist `ErrorBoundary`; move
  `buildSystemPrompt`/`buildSuggestions` to a `lib/`.
- Frontend: split `DatasetsPage.jsx` (1056) into its already-clean sub-components; extract
  `ScatterChart` + chat from `SimulationEngine.jsx` (1078).
- Frontend: type the API-boundary modules (`dataClient`/`intakeApi`/`cohortData`) against
  the generated `@augura/api-client` and add a `tsc --noEmit`/`checkJs` step
  (the high-value slice of the deferred TS migration).

## Out of scope (YAGNI, explicitly deferred)
- Full TypeScript migration of all `.jsx` components.
- Full UI-system consolidation / deletion of `theme.js` + `src/ui/*` + `views/*` rewrite.
- HNSW index tuning (revisit when the corpus grows).
- Generating `schema.sql` from `Base.metadata` (long-term; the Phase-1 drift test covers
  the risk for now).

## Risks & mitigations
- Refactors without tests are dangerous → Phase 1 (safety net) lands before Phase 4.
- Touching the deploy path can break prod → Phase 3 changes are reviewed and the migrate
  step fails closed; no deploy is run without explicit request.
- DB migration `0011` must stay idempotent and be mirrored into both `schema.sql` and a
  migration (per the Phase-1 schema↔migration rule) to avoid the prod-divergence footgun.

## Execution model
Each phase is its own plan → implement → verify (CI green) → (commit on request) cycle.
We start by writing the implementation plan for **Phase 0 + Phase 1** (smallest, safest,
and Phase 1 protects everything after).
