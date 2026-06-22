"""artifacts.kind : autorise 'simulation_run' et 'document'

La couche d'orchestration (jobs.handlers) émet des artefacts de provenance de kind
'document' (handle_document) et 'simulation_run' (handle_bootstrap), mais le CHECK
artifacts_kind_check ne les listait pas → CheckViolationError sur create_artifact, qui
faisait échouer TOUTE la transaction de travail du job (le dossier ne devenait jamais
`ready`, le bootstrap ne finalisait jamais son run). On élargit la contrainte aux kinds
réellement produits par le code. Idempotent : DROP CONSTRAINT IF EXISTS puis ré-ajout
(Postgres n'a pas d'ADD CONSTRAINT IF NOT EXISTS). La contrainte vit aussi dans le
bundle canonique schema.sql exécuté par 0001_baseline.

Revision ID: 0009_artifacts_kind_document
Revises: 0008_documents_content
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_artifacts_kind_document"
down_revision: str | None = "0008_documents_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_NEW = (
    "'dataset_snapshot', 'qc_report', 'mapping', 'dag', "
    "'sap', 'run_manifest', 'simulation_run', 'document'"
)
_KINDS_OLD = "'dataset_snapshot', 'qc_report', 'mapping', 'dag', 'sap', 'run_manifest'"


def upgrade() -> None:
    op.execute("ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_kind_check;")
    op.execute(
        f"ALTER TABLE artifacts ADD CONSTRAINT artifacts_kind_check CHECK (kind IN ({_KINDS_NEW}));"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_kind_check;")
    op.execute(
        f"ALTER TABLE artifacts ADD CONSTRAINT artifacts_kind_check CHECK (kind IN ({_KINDS_OLD}));"
    )
