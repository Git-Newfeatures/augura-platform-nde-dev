# Compliance Hardening — HIPAA / GDPR / SOC 2

Date: 2026-06-24
Status: design proposed, awaiting user review (then per-phase planning)
Scope: whole platform (`apps/api`, `apps/web`, DB bundle `apps/api/supabase/*`, CI/infra/deploy, vendor/process docs)

## Goal

Bring the Augura platform — a multi-tenant clinical-study-design SaaS that handles
special-category health data — into demonstrable readiness against **HIPAA**, **GDPR**,
and **SOC 2**. The work closes the *control* gaps (audit trail, access control,
encryption posture, data-subject rights, sub-processor governance, operational
resilience) on the **existing stack**, in safe gated increments, highest
risk-reduction-per-effort first. No language/runtime change.

## How we got here

The user asked: *"convert the whole project to TypeScript for higher data regulation."*
We ran a read-only, evidence-grounded gap assessment first — 8 parallel auditors over
the real code (auth, RLS, audit logging, encryption, data lifecycle, LLM data flows,
records integrity, ops), then a synthesis pass — producing **53 findings** mapped to the
four frameworks.

### The rewrite decision (the original ask) — REJECTED, with evidence

A Python→TypeScript rewrite would **not advance HIPAA/GDPR/SOC 2/Part 11 compliance and
would set it back.** Every material gap found is **architectural, contractual, or
procedural — never language-dependent**:

- Forgeable/mutable audit trail = a Postgres policy + a frontend PostgREST write
  (`apps/web/src/App.jsx:31`, `apps/api/supabase/policies.sql:63,189-219`).
- Missing BAA + no PHI de-identification = a contract plus a prompt-construction change
  (`apps/api/src/augura_api/modules/agents/tools.py:408-415`).
- Impossible GDPR erasure = a missing storage delete primitive + orchestrator
  (`apps/api/src/augura_api/core/storage.py:124-146`).
- Absent e-signatures, append-only audit, MFA, retention, monitoring, backup/DR = features
  and processes a TS codebase would lack just as completely.

Meanwhile the platform's **strongest asset** — defense-in-depth tenant isolation via
*forced* Postgres RLS under a non-BYPASSRLS role, transaction-local GUCs, repo-level org
filtering, and CI that proves cross-tenant denial on a real database — lives in SQL/DB
config a rewrite would not touch but **could easily regress**, with zero compliance
benefit. A rewrite would also consume the exact small-team capacity needed to execute the
roadmap below, reset the (already thin) test/validation evidence, and push months of
unverified change through PHI-handling code that currently has no branch protection.
**Verdict: keep the stack; treat "rewrite for compliance" as a misdiagnosis.**

## Confirmed healthy (do not regress)

- **Tenant isolation is production-grade.** Structurally sound JWT verification with
  algorithm allow-listing (`core/auth.py:48-135`); *forced* RLS on every tenant table run
  under a non-BYPASSRLS `augura_app` role; transaction-local GUCs `app.user_id`/
  `app.tenant_id` that fail **closed** when unset (`core/db.py:75-101`); belt-and-suspenders
  org filtering in repos; CI that exercises real cross-tenant denial on pgvector.
- LLM client transport is fine (HTTPS + cert verification by default; no `verify=False`,
  no custom `base_url`) — the gap is *what* is sent, not *how*.
- No committed secrets (only `.env.example`); strict typing already in place
  (`pyright --strict`, Pydantic runtime validation at the boundary).

These are the assets a rewrite would jeopardize. The hardening attaches new controls at
clean existing seams: centralized auth (`core/auth.py`), a single LLM chokepoint
(`core/llm/*`), and a typed analytics emission API (`modules/analytics/__init__.py`).

## Per-framework readiness (today)

| Framework | Readiness | Headline gaps |
|---|---|---|
| HIPAA | weak | PHI to LLM sub-processors w/ no BAA; no PHI-access logging; no MFA; unverified TLS to Postgres; flat RBAC |
| GDPR | weak | Erasure structurally impossible; no consent/Art 30 register; US transfer w/ no SCCs; no retention/purge; no export |
| SOC 2 | weak | No branch protection; no monitoring/alerting; no backup/DR evidence; no dependency/secret scanning; ad-hoc access mgmt |
| Part 11 | weak | (deferred — see Out of scope) |

## Decisions

- **Scope:** HIPAA + GDPR + SOC 2. **Part 11 / GxP is deferred entirely** to a future
  program (user decision). The append-only audit trail and record-integrity controls
  built here for HIPAA/SOC 2 are forward-compatible with a later Part 11 effort.
- **LLM sub-processor path:** **de-identify and keep the direct Anthropic/OpenAI APIs**
  (user decision). A de-identification chokepoint guarantees **no PHI** crosses the LLM
  boundary; a plain DPA (not a BAA) then covers the residual non-PHI data. No vendor
  migration to Bedrock/Azure OpenAI.
- **Sequencing:** 0 → 1 → 2 → 3 → 4, by risk-reduction-per-effort (**no external
  deadline** — user decision). Phase 0 quick wins first; each later phase depends on
  primitives from the earlier ones (e.g. Phase 3 erasure needs the Phase 0 storage/policy
  groundwork; audit review needs the append-only store).
- **Commits/deploy:** per `CLAUDE.md`, commit/push/deploy **only on explicit request**.
  No auto-commit, including of this spec.
- **Verification gate:** every phase leaves CI green (`ruff format --check`, `ruff check`,
  `pyright`, `lint-imports`, `pytest`, `db-bundle`); frontend changes additionally run
  `npm run lint` + `npm run build`. New controls ship with tests (RLS denial tests,
  append-only-policy tests, de-id unit tests, prod fail-fast boot tests).
- **Privileged DB ops:** all DDL/policy/grant changes go through the Supabase MCP or SQL
  editor (the local `.env` role is non-privileged; `psql` is not installed). New tables
  added to `schema.sql` must also be applied to the live DB by hand (the alembic-baseline
  footgun) — or shipped as an idempotent `0002+` migration.

## Findings → Phase mapping

Severity in brackets. File refs anchor the implementation plan. Effort per phase noted.

### Phase 0 — Stop the bleeding (effort S; config/policy/one-liners, no data migration)
- [critical] Make the audit store append-only: replace the `FOR ALL` policies on
  `usage_events`/`outbox_events` with INSERT-only policies; revoke UPDATE/DELETE/TRUNCATE
  from `augura_app` (`apps/api/supabase/policies.sql:189-219`).
- [critical] Stop the forgeable audit insert: revoke `grant insert on usage_events to
  authenticated` (`policies.sql:63`) and route the login event through a backend endpoint
  that stamps `user_id`/`org_id` from the verified `Principal` (removes the client-controlled
  write at `apps/web/src/App.jsx:31`). *(Overlaps platform-overhaul Phase 2 — do it here.)*
- [critical] Stop sending raw cohort cell values to LLMs: drop the `sample: [...]` block
  from `modules/agents/tools.py:408-415`; send only `ColumnStat` (value_kind, null_pct,
  n_distinct, ranges) the classifier already consumes (`agents/schemas.py:77-87`).
- [critical] Remove the false **"Pseudonymised ✓"** badge (`apps/web/src/cockpit/StudyTabs.jsx:252`)
  and the cosmetic "SECURE" badge (`AuguraLogin.jsx:61`) — or back them with a real control.
  (Eliminates the misrepresentation immediately; the real control lands in Phase 1.)
- [high] Force verified TLS to Postgres: pass an `ssl.SSLContext` (`check_hostname=True`,
  `CERT_REQUIRED`, Supabase CA) to `create_async_engine` and add a prod boot fail-fast if
  the DB URL lacks TLS, mirroring the CORS guard (`core/db.py:60`, `core/config.py:104`).
- [high] Provision the `datasets` bucket reproducibly + assert private: add
  `insert into storage.buckets(... public=false) on conflict do nothing` + storage RLS to
  the SQL bundle; add a CI/advisor assertion that `public=false` (`core/storage.py:40-57`).
- [medium] Add a security-headers middleware (HSTS, X-Content-Type-Options, minimal CSP),
  gated on `env==prod` (`apps/api/src/augura_api/main.py:27-35`).
- [medium] Stop echoing `exc.context` to clients for auth/4xx (`core/errors.py:73-79`);
  return a constant detail, log `reason`/`sub` server-side only (`core/auth.py:58,66`).
- [medium] Forbid HS256 (`AUGURA_SUPABASE_JWT_SECRET`) when `env==prod` so only asymmetric
  JWKS verification is reachable in prod (`core/config.py:35`, `core/auth.py:106`).
- [low] Add a prod fail-fast requiring Supabase Storage env vars so the unencrypted
  local-disk backend can never silently activate in prod (`core/storage.py:48`).
- [low] Make `read_bytes`/`exists` org-aware: assert `storage_path.startswith("org/{org_id}/")`
  before the Storage request — cheap defense-in-depth independent of RLS (`core/storage.py:78-145`).
- [SOC2-CC8] Enable GitHub branch protection on `main` + `Quentin` (require PR + green CI +
  1 review); add `CODEOWNERS`. Zero code, immediate change-management control.
- [SOC2-CC7] Add a CI security job: `pip-audit` / `npm audit`; enable Dependabot +
  GitHub secret scanning / push protection.

### Phase 1 — Sub-processor governance + PHI de-identification (effort M)
- [critical] Add a **de-identification / minimization layer at the single `core/llm`
  chokepoint** — never transmit raw cohort rows; only headers + column statistics, with
  identifier/free-text columns dropped or hashed. (`core/llm/runtime.py`, `core/llm/embeddings.py`,
  call sites `modules/agents/tools.py`, `modules/causal/prompt.py`.) This is the technical
  control that makes the chosen "de-identify + keep direct APIs" path lawful.
- [high] Execute and version a **DPA** with Anthropic and OpenAI; pin clients to
  zero-retention / no-training settings via `default_headers`/project config; add Settings
  (`llm_zero_retention`, allowed providers). Because no PHI is sent, a BAA is not required —
  but document the de-id boundary as the basis for that conclusion.
- [high] Per-org egress policy (`external_llm_enabled`, `allowed_subprocessors`) resolved
  alongside tenancy and checked **before** client construction; gate `/agents/*` and
  `/causal/*` on it (`modules/agents/router.py:63-91`).
- [high] Server-side PII gate at ingestion: enforce the existing `pii_pattern_catalog`
  (`seed.sql:1853`) in `datasets.service` on upload/add_files (scan headers + sample cell
  values; reject/quarantine direct identifiers). Frontend scan becomes UX-only
  (`apps/web/src/views/DatasetVerification.jsx:11-23`).
- [medium] No-PHI-in-logs: structlog redaction processor + error-context allowlist; never
  log raw DB error strings for data errors (`core/errors.py:91`, `core/logging.py`).
- [GDPR-Art30/Art44] Publish `SUBPROCESSORS.md` + a static Art 30 records-of-processing
  register (Anthropic, OpenAI, NCBI, Supabase, Modal, Vercel + the CT.gov relay); record
  SCCs/DPF reliance + a TIA for EU tenants; add region/transfer config.

### Phase 2 — Access control hardening (effort M)
- [high] RBAC matrix: a write-gating dependency on **all** mutating endpoints; make
  `viewer` truly read-only; require `owner` for destructive cohort/dataset ops. Today
  `require_role` covers only 2 of 13 modules (`core/deps.py:73-86`,
  `modules/analytics/router.py`, `modules/semantic/router.py`).
- [high] Enable Supabase TOTP **MFA** and enforce `aal2` on PHI routes in `core/auth.py`
  (backend currently never checks `aal`/`amr`).
- [high] Complete the planned **P7 PostgREST lockdown**: revoke `authenticated` SELECT on
  public tables once cockpit views move to the backend; add an integration test asserting
  **0 rows** as `authenticated` with no `SET LOCAL` (`policies.sql:58-69`).
- [medium] Idle/absolute session timeout + automatic logoff; consider httpOnly-cookie token
  storage; a `sessions_revoked_at` watermark for forced logout (`apps/web/src/supabase.js`,
  `apps/web/src/App.jsx:25-40`).
- [medium] Cache JWKS with TTL + refresh-on-unknown-kid; reject tokens with no `kid` in JWKS
  mode; don't silently use the first key (`core/auth.py:86-128`).
- [medium] App-layer rate limiting on auth-adjacent + write endpoints; alert on repeated
  `Unauthorized`/`Forbidden` per user/IP (`main.py`).
- [SOC2-CC6] Membership provisioning/deprovisioning workflow + admin audit trail; quarterly
  access reviews (currently ad-hoc privileged SQL).

### Phase 3 — Audit trail + data-subject rights (effort L; the GDPR/HIPAA backbone)
- [critical] DB-enforced **append-only `audit_events`** table (`table`, `row_id`, `op`,
  `actor_user_id`, `org_id`, `old_row` jsonb, `new_row` jsonb, `request_id`, `ts`) via AFTER
  triggers reading `app.user_id`; revoke UPDATE/DELETE from `augura_app`; expose an
  owner-gated review/export endpoint. Replaces the sparse opt-in `event_type=` emission
  (only 10 event types across 33 mutating endpoints; deletes unlogged;
  `modules/studies/service.py:63` records field *names* only, never old values).
- [high] PHI **read/export/delete** logging via a decorator on PHI routers so new endpoints
  fail closed (no read-access logging exists today).
- [critical] Add `delete_bytes` to `core/storage.py` and an `erase_tenant_data()` orchestrator
  covering `dataset_files` + bucket objects, `datasets`, `generated_documents.content`,
  `artifacts.storage_ref`, `chunks`/embeddings, `literature_snapshots`, `literature_queries`,
  `agent_cache`. Today deleting a dataset file orphans the CSV bytes forever
  (`modules/datasets/service.py:262-278`; `core/storage.py` has no delete). Document
  crypto-erasure / legal-hold for immutable artifacts and the (now PHI-free) LLM boundary.
- [high] Owner-gated subject/tenant **export** (cohort + dataset + processing metadata as
  zip JSON/CSV) for Art 15/20; reuse tenant-scoped repos so RLS bounds the dump; log each
  export.
- [high] **Consent / lawful-basis** + `retention_until` columns and a **scheduled purge**
  (Supabase `pg_cron` or Modal cron) that hard-deletes expired rows + their Storage objects;
  written retention schedule per data class; legal-hold flag. (Special-category biomarkers
  ingested with no recorded basis today — `schema.sql:159-188`.)
- [medium] `usage_events.org_id` is `ON DELETE SET NULL` — copy org context into the audit
  row so it survives org deletion (`schema.sql:355`).

### Phase 4 — Operational resilience + monitoring (effort M; SOC 2 CC7/A1)
- [high] Wire **Sentry** (FastAPI + jobs worker), capturing failed jobs as the existing spec
  intended but never implemented (`docs/.../design.md:155`); ship a log drain with retention
  + alerting on 500-rate / auth-failures / job-failures; uptime monitor on `/healthz`.
- [high] Document and verify Supabase **PITR/backup** retention for the prod project; define
  RPO/RTO; schedule + log quarterly restore drills (incl. Storage bytes).
- [medium] Move deployment into CI (deployed commit == verified commit) with recorded
  deployer/timestamp; couple `alembic upgrade head` to deploy to kill schema drift; document
  rollback. (`apps/api/scripts/deploy_modal.sh`. Overlaps platform-overhaul Phase 3.)
- [medium] Incident-response + DR runbooks, including the HIPAA 164.308(a)(6) breach steps
  and the GDPR Art 33/34 72-hour notification flow.

## Out of scope (explicitly deferred)

- **The TypeScript rewrite** — rejected above; no compliance value, high regression risk.
- **21 CFR Part 11 / GxP** — entire program deferred (e-signatures, record versioning /
  immutability triggers, state-machine sequencing, CSV/GAMP5 validation package: VMP, URS/FS/DS,
  IQ/OQ/PQ, traceability matrix). The Phase 3 append-only audit + Phase 2 authority checks are
  built to be forward-compatible when this is picked up.
- Migrating LLM calls to AWS Bedrock / Azure OpenAI (the de-id path makes a BAA unnecessary).
- HNSW/index tuning and other non-compliance performance work (belongs to platform-overhaul).

## Relationship to the platform-overhaul program

This is a **parallel, compliance-driven** track to
`docs/superpowers/specs/2026-06-23-platform-overhaul-design.md`. Overlaps are deliberate and
deduplicated here:
- "Route `usage_events` through a backend endpoint" (overhaul Phase 2) = this Phase 0
  forgeable-audit fix — owned here.
- Branch-gating `Quentin` + web CI job (overhaul Phase 1, reported done) underpins this
  Phase 0 change-management control.
- Deploy hardening / migrate-then-deploy (overhaul Phase 3) = this Phase 4 deploy-from-CI.
Where an item exists in both, the compliance program is the source of truth for its
acceptance criteria.

## Risks & mitigations

- **Regressing RLS during change** → every phase adds/keeps RLS denial tests; the Phase 2
  PostgREST lockdown ships with a "0 rows as authenticated" integration test before grants
  are revoked.
- **De-id leakage** (Phase 1) → unit tests asserting no raw cell value ever reaches the LLM
  payload; the chokepoint is the single egress point so coverage is enforceable.
- **Erasure that misses derived stores** (Phase 3) → the cascade is mapped to every
  content-addressed store; an integration test seeds + erases + asserts zero residue.
- **Touching deploy/secrets** (Phase 4) → reviewed; migrate step fails closed; no deploy run
  without explicit request.
- **Idempotency footgun** → any new table goes into both `schema.sql` and an idempotent
  `0002+` migration (or is applied to the live DB via MCP), per the existing DB invariant.

## Execution model

Each phase is its own plan → implement → verify (CI green) → (commit on request) cycle.
After this spec is approved, we write the implementation plan for **Phase 0** first
(smallest, highest risk-reduction, mostly one-line SQL/middleware/config), then proceed
phase by phase.
