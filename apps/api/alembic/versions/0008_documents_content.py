"""generated_documents.content : octets du dossier généré stockés en base

Même bug que 0007_jobs_result_json, côté dossiers : `handle_document` écrivait le HTML
sur le disque local du conteneur (core.storage). Sur Modal le worker `run_job` et le
conteneur ASGI qui sert GET /documents/{id}/download sont distincts et le FS est
éphémère ⇒ FileNotFoundError/404 intermittent. On stocke désormais les octets EN BASE
(generated_documents.content), immédiatement cohérent cross-conteneur. Idempotent
(ADD COLUMN IF NOT EXISTS) : la colonne vit aussi dans le bundle canonique schema.sql
exécuté par 0001_baseline.

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
