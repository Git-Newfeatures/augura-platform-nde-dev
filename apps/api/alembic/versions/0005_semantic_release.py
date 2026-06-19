"""semantic_releases : historique de version de la couche sémantique gouvernée

Ajoute la seule table que le design /bundle nécessitait et qui manquait au schéma
public (les 14 autres tables taxonomie/ontologie sont déjà là via schema.sql). Sert
GET /semantic/release (onglet Versions). Idempotent (IF NOT EXISTS / ON CONFLICT) :
elle vit aussi dans le bundle canonique schema.sql + policies.sql exécuté par
0001_baseline. RLS backend_read comme les autres catalogues gouvernés (lecture
ouverte à toute session backend, aucune écriture hors rôle privilégié).

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
