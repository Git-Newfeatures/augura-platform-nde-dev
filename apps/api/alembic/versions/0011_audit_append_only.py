"""audit append-only: usage_events + outbox_events (idempotent).

Converges DBs already migrated past the 0001 baseline (which applied the old
FOR ALL policies + the authenticated insert grant). Safe to re-run.
"""

from alembic import op

# revision identifiers — set down_revision to the current head from `alembic heads`.
revision = "0011_audit_append_only"
down_revision = "0010_dataset_files"
branch_labels = None
depends_on = None

_UPGRADE = """
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke insert on usage_events from authenticated;
    end if;
end
$$;

drop policy if exists tenant_or_system on usage_events;
drop policy if exists usage_events_read on usage_events;
drop policy if exists usage_events_insert on usage_events;
create policy usage_events_read on usage_events
    for select using (
        org_id is null or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
create policy usage_events_insert on usage_events
    for insert with check (
        org_id is null or org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
revoke update, delete, truncate on usage_events from augura_app;

drop policy if exists backend_session on outbox_events;
drop policy if exists outbox_events_read on outbox_events;
drop policy if exists outbox_events_insert on outbox_events;
create policy outbox_events_read on outbox_events
    for select using (nullif(current_setting('app.tenant_id', true), '') is not null);
create policy outbox_events_insert on outbox_events
    for insert with check (nullif(current_setting('app.tenant_id', true), '') is not null);
-- outbox_events.processed_at updates are reserved for a privileged worker (BYPASSRLS).
revoke update, delete, truncate on outbox_events from augura_app;
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    # Audit hardening is not reverted automatically (no destructive downgrade).
    pass
