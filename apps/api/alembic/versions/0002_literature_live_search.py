"""literature live-search: frozen snapshots, sessions, events, query cache

New tables for the retrieve-and-freeze verb (distinct from the existing ingestion):
  - literature_snapshots: frozen artifact (results + provenance + content_hash),
    carries `study_id` (NULL ⇒ standalone) for per-study access delegated to RLS.
  - search_sessions      : search sessions (active/list/by-id).
  - literature_events    : append-only event log per session.
  - literature_queries   : cache (org, source, query_string) → result.

External refs (org_id, study_id, created_by) = bare UUIDs, like `documents.org_id`
(orgs/users live on the Supabase auth side; no cross-schema FK). Only
events.session_id is a true intra-table FK.

Baseline RLS here: per-tenant isolation (org_id = app.tenant_id). Per-study
visibility (study_members) and standalone gating arrive in Tier 3.

Revision ID: 0002_literature_live_search
Revises: 0001_baseline
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_literature_live_search"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "literature_events",
    "literature_snapshots",
    "search_sessions",
    "literature_queries",
)


def upgrade() -> None:
    # Idempotent (IF NOT EXISTS / DROP-then-CREATE): these objects ALSO live in the
    # canonical bundle supabase/schema.sql + policies.sql (source of truth, executed
    # by 0001_baseline). This migration must therefore be able to stack without error
    # on top of a database already created by the baseline — as on top of a bare one.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS literature_snapshots (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        uuid NOT NULL,
            study_id      uuid,
            created_by    uuid NOT NULL,
            -- payload = the EXACT canonical artifact that was hashed (hash authority):
            -- {query, sources, model_version, prompt_version, study_id, created_by,
            --  created_at, results:[…]}. The columns above denormalize it for
            -- RLS / indexing / sorting; the hash is authoritative only over payload.
            payload       jsonb NOT NULL,
            content_hash  text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_literature_snapshots_org_id
            ON literature_snapshots (org_id);
        CREATE INDEX IF NOT EXISTS ix_literature_snapshots_study_id
            ON literature_snapshots (study_id);
        CREATE INDEX IF NOT EXISTS ix_literature_snapshots_created_by
            ON literature_snapshots (created_by);

        CREATE TABLE IF NOT EXISTS search_sessions (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      uuid NOT NULL,
            study_id    uuid,
            query       text,
            status      text NOT NULL DEFAULT 'active',
            created_by  uuid NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_search_sessions_org_id_status
            ON search_sessions (org_id, status);
        CREATE INDEX IF NOT EXISTS ix_search_sessions_created_by
            ON search_sessions (created_by);

        CREATE TABLE IF NOT EXISTS literature_events (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id  uuid NOT NULL REFERENCES search_sessions (id) ON DELETE CASCADE,
            org_id      uuid NOT NULL,
            event_type  text NOT NULL,
            payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_by  uuid NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_literature_events_session_id
            ON literature_events (session_id);

        CREATE TABLE IF NOT EXISTS literature_queries (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        uuid NOT NULL,
            source        text NOT NULL,
            query_string  text NOT NULL,
            result        jsonb NOT NULL,
            retrieved_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_literature_queries_org_source_query
                UNIQUE (org_id, source, query_string)
        );
        """
    )

    # RLS: tenant isolation. The application role is not exempt from RLS; it sets
    # app.tenant_id per transaction (see core.db.set_tenant_stmt).
    for table in (
        "literature_snapshots",
        "search_sessions",
        "literature_events",
        "literature_queries",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

    # search_sessions / events / queries: policy `tenant_isolation` (name aligned with
    # the policies.sql bundle and the remote database). DROP-then-CREATE ⇒ re-stackable.
    for table in ("search_sessions", "literature_events", "literature_queries"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
            """
        )

    # literature_snapshots: baseline policy (tenant isolation only). 0003 replaces it
    # with per-study gating. Historical name kept so 0003 knows how to drop it.
    op.execute(
        "DROP POLICY IF EXISTS literature_snapshots_tenant_isolation ON literature_snapshots;"
    )
    op.execute(
        """
        CREATE POLICY literature_snapshots_tenant_isolation ON literature_snapshots
            USING (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (org_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
        """
    )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
