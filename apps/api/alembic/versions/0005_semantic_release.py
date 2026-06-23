"""semantic_releases: version history of the governed semantic layer

Adds the one table the design/bundle needed that was missing from the public
schema (the 14 other taxonomy/ontology tables are already there via schema.sql).
Serves GET /semantic/release (Versions tab). Idempotent (IF NOT EXISTS / ON
CONFLICT): it also lives in the canonical bundle schema.sql + policies.sql
executed by 0001_baseline. RLS backend_read like the other governed catalogs
(read open to any backend session, no write outside a privileged role).

Revision ID: 0005_semantic_release
Revises: 0004_reference_catalogs
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_semantic_release"
down_revision: str | None = "0004_reference_catalogs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MANIFEST = (
    '{"semantic_release_version":"2.2.0","taxonomy_version":"2.0.0",'
    '"causal_ontology_version":"2.0.0","dq_ontology_version":"1.1.0",'
    '"omop_cdm_version":"5.4","source":"Data intake prototype semantic standards."}'
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS semantic_releases (
            semantic_release_version text PRIMARY KEY,
            taxonomy_version         text NOT NULL,
            causal_ontology_version  text NOT NULL,
            dq_ontology_version      text NOT NULL,
            omop_cdm_version         text,
            source                   text,
            manifest                 jsonb NOT NULL,
            imported_at              timestamptz NOT NULL DEFAULT now(),
            is_current               boolean NOT NULL DEFAULT false
        );
        """
    )
    op.execute("ALTER TABLE semantic_releases ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE semantic_releases FORCE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS backend_read ON semantic_releases;")
    op.execute(
        """
        CREATE POLICY backend_read ON semantic_releases
            FOR SELECT
            USING (nullif(current_setting('app.tenant_id', true), '') IS NOT NULL);
        """
    )
    op.execute(
        f"""
        INSERT INTO semantic_releases (
            semantic_release_version, taxonomy_version, causal_ontology_version,
            dq_ontology_version, omop_cdm_version, source, manifest, is_current
        ) VALUES (
            '2.2.0', '2.0.0', '2.0.0', '1.1.0', '5.4',
            'Data intake prototype semantic standards.', '{_MANIFEST}'::jsonb, true
        ) ON CONFLICT (semantic_release_version) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS semantic_releases CASCADE;")
