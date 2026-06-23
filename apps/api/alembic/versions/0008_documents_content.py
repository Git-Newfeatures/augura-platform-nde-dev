"""generated_documents.content: bytes of the generated dossier stored in the database

Same bug as 0007_jobs_result_json, on the dossiers side: `handle_document` wrote the
HTML to the container's local disk (core.storage). On Modal the `run_job` worker and
the ASGI container that serves GET /documents/{id}/download are distinct and the FS is
ephemeral ⇒ intermittent FileNotFoundError/404. We now store the bytes IN THE DATABASE
(generated_documents.content), immediately consistent cross-container. Idempotent
(ADD COLUMN IF NOT EXISTS): the column also lives in the canonical bundle schema.sql
executed by 0001_baseline.

Revision ID: 0008_documents_content
Revises: 0007_jobs_result_json
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_documents_content"
down_revision: str | None = "0007_jobs_result_json"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE generated_documents ADD COLUMN IF NOT EXISTS content bytea;")


def downgrade() -> None:
    op.execute("ALTER TABLE generated_documents DROP COLUMN IF EXISTS content;")
