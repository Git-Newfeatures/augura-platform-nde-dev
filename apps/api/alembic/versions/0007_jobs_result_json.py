"""jobs.result_json: structured job result stored in the database

Long-running tasks (B4 semantic enrichment, bootstrap, dossiers) used to write
their result to the container's local disk (core.storage). On Modal the filesystem
is ephemeral AND specific to each container: the result written by the worker
cannot be read back by the ASGI container that serves GET /semantic/enrich/proposals/{id}
(→ 404). We now store the result IN THE DATABASE (jobs.result_json), immediately
consistent cross-container. Idempotent (ADD COLUMN IF NOT EXISTS): the column also
lives in the canonical bundle schema.sql executed by 0001_baseline.

Revision ID: 0007_jobs_result_json
Revises: 0006_semantic_enrich_function
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_jobs_result_json"
down_revision: str | None = "0006_semantic_enrich_function"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS result_json jsonb;")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS result_json;")
