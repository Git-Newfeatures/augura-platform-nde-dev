"""jobs.result_json : résultat structuré des jobs stocké en base

Les traitements longs (enrichissement sémantique B4, bootstrap, dossiers) écrivaient
leur résultat sur le disque local du conteneur (core.storage). Sur Modal le système de
fichiers est éphémère ET propre à chaque conteneur : le résultat écrit par le worker
n'est pas relisible par le conteneur ASGI qui sert GET /semantic/enrich/proposals/{id}
(→ 404). On stocke désormais le résultat EN BASE (jobs.result_json), immédiatement
cohérent cross-conteneur. Idempotent (ADD COLUMN IF NOT EXISTS) : la colonne vit aussi
dans le bundle canonique schema.sql exécuté par 0001_baseline.

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
