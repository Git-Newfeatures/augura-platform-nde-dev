"""baseline — applique le bundle SQL canonique (schéma + fonctions + RLS)

Le schéma est défini une seule fois dans apps/api/supabase/*.sql (source de
vérité, aussi exportable tel quel vers Supabase). Cette migration baseline
l'exécute pour que `alembic upgrade head` construise la base — le schéma est
ainsi « trigger par le backend Python ». Le seed (seed.sql) n'est PAS une
migration : c'est de la donnée, appliquée séparément.

Revision ID: 0001_baseline
Revises:
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# apps/api/supabase (parents : [0]=versions [1]=alembic [2]=apps/api)
_SUPABASE = Path(__file__).resolve().parents[2] / "supabase"
_DDL_FILES = ("schema.sql", "functions.sql", "policies.sql")


def _strip_tx(sql: str) -> str:
    """Retire les begin;/commit; (Alembic gère déjà la transaction)."""
    keep = [ln for ln in sql.splitlines() if ln.strip().lower() not in ("begin;", "commit;")]
    return "\n".join(keep)


def upgrade() -> None:
    conn = op.get_bind()
    for name in _DDL_FILES:
        sql = (_SUPABASE / name).read_text(encoding="utf-8")
        conn.exec_driver_sql(_strip_tx(sql))


def downgrade() -> None:
    # Baseline : réinitialisation franche du schéma public.
    op.execute("drop schema public cascade; create schema public;")
