"""artifacts.kind: allow 'simulation_run' and 'document'

The orchestration layer (jobs.handlers) emits provenance artifacts of kind
'document' (handle_document) and 'simulation_run' (handle_bootstrap), but the CHECK
artifacts_kind_check did not list them → CheckViolationError on create_artifact, which
made the job's ENTIRE work transaction fail (the dossier never became `ready`, the
bootstrap never finalized its run). We widen the constraint to the kinds actually
produced by the code. Idempotent: DROP CONSTRAINT IF EXISTS then re-add (Postgres has
no ADD CONSTRAINT IF NOT EXISTS). The constraint also lives in the canonical bundle
schema.sql executed by 0001_baseline.

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
