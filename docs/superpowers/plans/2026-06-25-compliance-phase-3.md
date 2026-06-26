# Compliance Hardening — Phase 3 (Audit Trail + Data-Subject Rights) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Deliver the GDPR/HIPAA backbone — a DB-enforced **append-only `audit_events`** change log (who/what/when + old/new), **PHI read-logging**, **erasure** (`delete_bytes` + `erase_tenant_data`), **subject/tenant export**, and **retention** columns + purge.

**Tech Stack:** Postgres 16 triggers · SQLAlchemy async · FastAPI · pytest. Backend `apps/api`, pyright strict, ruff 100. Baseline GREEN: 302 passed, 40 skipped.

**Spec:** [docs/superpowers/specs/2026-06-24-compliance-hardening-design.md](../specs/2026-06-24-compliance-hardening-design.md)

## DB invariants (do not break)
- A new table goes in BOTH `supabase/schema.sql` AND an idempotent `>=0002` migration (the `test_post_baseline_tables_each_have_a_migration` guard) AND `EXPECTED_TABLES` in `tests/db/test_supabase_bundle.py`.
- Migrations idempotent (`create … if not exists`, `drop … if exists`, `create or replace`). Next migration prefix: **0012**, `down_revision = "0011_audit_append_only"`.
- Prod has NO `alembic_version`; the audit migration is applied to prod via Supabase MCP after it's built + verified (controller does this, with before/after checks).

---

## Task 1: Append-only `audit_events` table + change-capture triggers

A DB trigger records every INSERT/UPDATE/DELETE on regulated clinical-record tables into an append-only `audit_events` table, capturing actor (`app.user_id`), tenant (`app.tenant_id`), and old/new row jsonb.

**Regulated tables to audit:** `studies, study_state, datasets, dataset_columns, dataset_files, cohort_members, cohort_biomarkers, generated_documents, artifacts, dq_bundles, simulation_runs, simulation_results`. (Exclude high-churn/low-value infra: jobs, agent_runs, agent_cache, usage_events, search_sessions/events/queries.)

**Files:**
- Modify: `apps/api/supabase/schema.sql` (add `audit_events` table)
- Modify: `apps/api/supabase/policies.sql` (RLS + grants + trigger fn + triggers)
- Create: `apps/api/alembic/versions/0012_audit_events.py` (idempotent: table + fn + triggers + grants/policies)
- Modify: `apps/api/tests/db/test_supabase_bundle.py` (EXPECTED_TABLES + a structural guard)
- Create: `apps/api/tests/integration/test_audit_events.py`

- [ ] **Step 1: Add the table to `schema.sql`** (near the other audit tables):

```sql
create table if not exists audit_events (
    id uuid primary key default gen_random_uuid(),
    table_name text not null,
    row_pk text,
    op char(1) not null,            -- 'I' | 'U' | 'D'
    actor_user_id uuid,             -- from app.user_id GUC (NULL for privileged/no-context writes)
    org_id uuid,                    -- from app.tenant_id GUC
    old_row jsonb,
    new_row jsonb,
    occurred_at timestamptz not null default now()
);
create index if not exists ix_audit_events_org_occurred on audit_events (org_id, occurred_at desc);
create index if not exists ix_audit_events_table_pk on audit_events (table_name, row_pk);
```

- [ ] **Step 2: Add the trigger fn + triggers + RLS/grants to `policies.sql`** (append, before the final `commit;`). The trigger fn runs as the invoking role (augura_app) inside the tenant transaction:

```sql
-- ── audit_events: append-only change log of regulated records (HIPAA 164.312(b), GDPR) ──
alter table audit_events enable row level security;
alter table audit_events force row level security;
drop policy if exists audit_events_read on audit_events;
drop policy if exists audit_events_insert on audit_events;
create policy audit_events_read on audit_events
    for select using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy audit_events_insert on audit_events
    for insert with check (true);   -- writes come only from the trigger, inside a backend txn
revoke update, delete, truncate on audit_events from augura_app;

create or replace function audit_row_change() returns trigger
language plpgsql as $$
declare
    v_user uuid := nullif(current_setting('app.user_id', true), '')::uuid;
    v_org  uuid := nullif(current_setting('app.tenant_id', true), '')::uuid;
    v_pk   text := to_jsonb(coalesce(NEW, OLD)) ->> 'id';
begin
    insert into audit_events(table_name, row_pk, op, actor_user_id, org_id, old_row, new_row)
    values (
        TG_TABLE_NAME, v_pk, substr(TG_OP, 1, 1), v_user, v_org,
        case when TG_OP in ('UPDATE','DELETE') then to_jsonb(OLD) else null end,
        case when TG_OP in ('INSERT','UPDATE') then to_jsonb(NEW) else null end
    );
    return null;  -- AFTER trigger: return value ignored
end;
$$;

do $$
declare t text;
begin
    foreach t in array array[
        'studies','study_state','datasets','dataset_columns','dataset_files',
        'cohort_members','cohort_biomarkers','generated_documents','artifacts',
        'dq_bundles','simulation_runs','simulation_results'
    ] loop
        execute format('drop trigger if exists audit_change on %I;', t);
        execute format(
            'create trigger audit_change after insert or update or delete on %I '
            'for each row execute function audit_row_change();', t);
    end loop;
end $$;
```

> Note: `audit_events` must be granted INSERT+SELECT to `augura_app`. The bundle's blanket
> `grant select, insert, update, delete on all tables … to augura_app` (top of policies.sql)
> runs BEFORE this block on a fresh apply, so the subsequent `revoke update, delete, truncate`
> leaves exactly INSERT+SELECT. The migration (Step 3) grants explicitly for already-migrated DBs.

- [ ] **Step 3: Migration `0012_audit_events.py`** — idempotent: `create table if not exists audit_events (...)` + indexes, `create or replace function audit_row_change()`, the `do $$ … create trigger …` loop (with `drop trigger if exists`), and `grant select, insert on audit_events to augura_app; revoke update, delete, truncate on audit_events from augura_app;` + the RLS enable/force/policies (drop-if-exists then create). `revision="0012_audit_events"`, `down_revision="0011_audit_append_only"`. `downgrade()` = no-op.

- [ ] **Step 4: Bundle structural test** — add `"audit_events"` to `EXPECTED_TABLES` in `tests/db/test_supabase_bundle.py` (NOT to `RLS_REQUIRED`/`TENANT_DATA_TABLES`; add to `POST_BASELINE_TABLES`). Add a `test_audit_events_append_only` asserting policies.sql contains `create policy audit_events_insert`, `audit_row_change`, and `revoke … on audit_events from augura_app`.

- [ ] **Step 5: Integration test** (`tests/integration/test_audit_events.py`, runs in db-bundle CI) — under `set local role augura_app` + app.user_id/app.tenant_id set: insert a `studies` row, assert exactly one `audit_events` row appears with `op='I'`, matching `org_id`, `actor_user_id`, and `new_row->>'id'`; update it → an `op='U'` row with `old_row`+`new_row`; assert `update audit_events …` / `delete from audit_events …` raise `DBAPIError` (append-only). Mirror `tests/integration/test_audit_append_only.py` harness.

- [ ] **Step 6: Gate + commit** (`feat(compliance): append-only audit_events change log via DB triggers`).

---

## Task 2: Storage `delete_bytes` + `erase_tenant_data` + subject/tenant export

**Files:** `core/storage.py` (add `delete_bytes`), a new `modules/datasets` (or `core`) erasure orchestrator, an export endpoint, tests.

- [ ] **Step 1 (delete_bytes):** add `async def delete_bytes(settings, storage_path, *, expected_org=None) -> None` to `core/storage.py` — Supabase: `DELETE /storage/v1/object/{bucket}/{ref}` with the service-role key (treat 404 as success/idempotent); disk: `unlink` under artifacts_dir with the existing path-traversal guard; honor the `_assert_org` guard from Phase 0. Unit-test both backends (fake httpx like the existing storage tests; disk roundtrip then delete).

- [ ] **Step 2 (erasure orchestrator):** add `erase_dataset(tenant, settings, dataset_id)` in `datasets/service.py` that gathers every `dataset_files.storage_path`, deletes the DB rows (cascade handles columns), then `delete_bytes` each object (failure re-raises, not silently orphaned). Add a `DELETE /datasets/{dataset_id}` endpoint gated `WriteTenantDep` (owner-only is even better — use `require_role('owner')`). Wire `delete_bytes` into the existing `remove_file` so single-file deletes also remove the object (closes the Phase 0 orphan finding). Document (code comment) that whole-study/org erasure across generated_documents/artifacts/chunks/literature_snapshots/agent_cache is the broader `erase_tenant_data` follow-up.

- [ ] **Step 3 (export):** add `GET /datasets/{dataset_id}/export` (any member) returning a JSON bundle of the dataset + its columns + files metadata (NOT raw bytes) for Art 15/20; emit a `usage_events` `dataset.exported` event (via `log_usage`). Unit/integration test the shape.

- [ ] **Step 4: Gate + commit** (`feat(compliance): storage delete_bytes + dataset erasure + export (GDPR Art 17/15/20)`).

---

## Task 3: Retention columns + purge function

- [ ] Add a nullable `retention_until timestamptz` column to `datasets` (schema.sql + idempotent migration 0013 + bundle test tolerance). Add a `purge_expired()` service function (+ a `POST /admin/purge` owner-gated endpoint OR a documented Modal-cron entry) that deletes datasets whose `retention_until < now()` via the erasure orchestrator. Do NOT schedule cron here (document it as an ops step). Tests for the column + the purge selection logic.
- [ ] Commit (`feat(compliance): dataset retention_until + purge primitive`).

---

## Task 4: PHI read-logging

- [ ] Add a small dependency/helper that emits a `usage_events` read event (actor, target type+id, route) for PHI-bearing reads — apply to cohort member/biomarker reads + dataset file reads. Keep it best-effort but present (so new PHI endpoints can adopt it). Tests asserting a read emits an event.
- [ ] Commit (`feat(compliance): PHI read-access logging on cohort/dataset reads`).

---

## Self-Review
- Task 1 (audit triggers) is the centerpiece and the prod-applied change — build + integration-test it FIRST, apply to prod with before/after verification (controller).
- Tasks 2-4 are pure code/migrations. Retention cron + whole-org erasure cascade across all derived stores are documented as follow-ups (scoped to keep this shippable).

## Execution
Subagent-driven, sequential (Tasks 1-3 touch schema/policies/migrations + datasets service), then merge to `Quentin`; apply migration 0012 (+0013) to prod via MCP after verification.
