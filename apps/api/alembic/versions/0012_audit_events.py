"""audit_events: append-only change-capture table + triggers (idempotent).

Creates the audit_events table (if not exists), its indexes, the
audit_row_change() trigger function, the per-table AFTER triggers on
regulated clinical-record tables, and the RLS/grants that make the table
append-only for augura_app.

Safe to re-run on already-migrated databases.
"""

from alembic import op

revision = "0012_audit_events"
down_revision = "0011_audit_append_only"
branch_labels = None
depends_on = None

_UPGRADE = """
-- ── Table ──────────────────────────────────────────────────────────────────
create table if not exists audit_events (
    id uuid primary key default gen_random_uuid(),
    table_name text not null,
    row_pk text,
    op char(1) not null,
    actor_user_id uuid,
    org_id uuid,
    old_row jsonb,
    new_row jsonb,
    occurred_at timestamptz not null default now()
);
create index if not exists ix_audit_events_org_occurred
    on audit_events (org_id, occurred_at desc);
create index if not exists ix_audit_events_table_pk
    on audit_events (table_name, row_pk);

-- ── Grants (explicit for already-migrated DBs) ─────────────────────────────
grant select, insert on audit_events to augura_app;
revoke update, delete, truncate on audit_events from augura_app;

-- ── RLS ────────────────────────────────────────────────────────────────────
alter table audit_events enable row level security;
alter table audit_events force row level security;
drop policy if exists audit_events_read on audit_events;
drop policy if exists audit_events_insert on audit_events;
create policy audit_events_read on audit_events
    for select using (
        org_id is null
        or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy audit_events_insert on audit_events
    for insert with check (true);

-- ── Trigger function ───────────────────────────────────────────────────────
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

-- ── Per-table triggers ─────────────────────────────────────────────────────
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
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    # Audit hardening is not reverted automatically (append-only guarantee).
    pass
