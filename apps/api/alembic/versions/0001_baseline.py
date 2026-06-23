"""baseline — applies the canonical SQL bundle (schema + functions + RLS)

The schema is defined once in apps/api/supabase/*.sql (source of truth, also
exportable as-is to Supabase). This baseline migration runs it so that
`alembic upgrade head` builds the database — the schema is thus "driven by the
Python backend". The seed (seed.sql) is NOT a migration: it is data, applied
separately.

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

# apps/api/supabase (parents: [0]=versions [1]=alembic [2]=apps/api)
_SUPABASE = Path(__file__).resolve().parents[2] / "supabase"
_DDL_FILES = ("schema.sql", "functions.sql", "policies.sql")


def _strip_tx(sql: str) -> str:
    """Strip begin;/commit; (Alembic already manages the transaction)."""
    keep = [ln for ln in sql.splitlines() if ln.strip().lower() not in ("begin;", "commit;")]
    return "\n".join(keep)


def upgrade() -> None:
    conn = op.get_bind()
    for name in _DDL_FILES:
        sql = (_SUPABASE / name).read_text(encoding="utf-8")
        conn.exec_driver_sql(_strip_tx(sql))


def downgrade() -> None:
    # Baseline: clean reset of the public schema.
    op.execute("drop schema public cascade; create schema public;")
