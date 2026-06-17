"""literature live-search : snapshots gelés, sessions, events, cache de requêtes

Nouvelles tables du verbe retrieve-and-freeze (distinct de l'ingestion existante) :
  - literature_snapshots : artefact gelé (résultats + provenance + content_hash),
    porte `study_id` (NULL ⇒ standalone) pour l'accès par-étude délégué à la RLS.
  - search_sessions      : sessions de recherche (active/list/by-id).
  - literature_events    : journal d'événements append-only par session.
  - literature_queries   : cache (org, source, query_string) → résultat.

Refs externes (org_id, study_id, created_by) = UUID nus, comme `documents.org_id`
(les orgs/users vivent côté Supabase auth ; pas de FK cross-schema). Seul
events.session_id est une vraie FK intra-tables.

RLS de base ici : isolation par tenant (org_id = app.tenant_id). La visibilité
par-étude (study_members) et le gating standalone arrivent en Tier 3.

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
    op.execute(
        """
        CREATE TABLE literature_snapshots (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        uuid NOT NULL,
            study_id      uuid,
            created_by    uuid NOT NULL,
            -- payload = l'artefact canonique EXACT qui a été haché (autorité du hash) :
            -- {query, sources, model_version, prompt_version, study_id, created_by,
            --  created_at, results:[…]}. Les colonnes ci-dessus le dénormalisent pour
            -- la RLS / l'indexation / le tri ; le hash ne fait foi que sur payload.
            payload       jsonb NOT NULL,
            content_hash  text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_literature_snapshots_org_id ON literature_snapshots (org_id);
        CREATE INDEX ix_literature_snapshots_study_id ON literature_snapshots (study_id);
        CREATE INDEX ix_literature_snapshots_created_by ON literature_snapshots (created_by);

        CREATE TABLE search_sessions (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      uuid NOT NULL,
            study_id    uuid,
            query       text,
            status      text NOT NULL DEFAULT 'active',
            created_by  uuid NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_search_sessions_org_id_status ON search_sessions (org_id, status);
        CREATE INDEX ix_search_sessions_created_by ON search_sessions (created_by);

        CREATE TABLE literature_events (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id  uuid NOT NULL REFERENCES search_sessions (id) ON DELETE CASCADE,
            org_id      uuid NOT NULL,
            event_type  text NOT NULL,
            payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_by  uuid NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_literature_events_session_id ON literature_events (session_id);

        CREATE TABLE literature_queries (
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

    # RLS : isolation tenant. Le rôle applicatif n'est pas exempt de RLS ; il pose
    # app.tenant_id par transaction (cf. core.db.set_tenant_stmt).
    for table in ("literature_snapshots", "search_sessions", "literature_events",
                  "literature_queries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (org_id = current_setting('app.tenant_id', true)::uuid)
                WITH CHECK (org_id = current_setting('app.tenant_id', true)::uuid);
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
