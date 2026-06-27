"""semantic schema (Part B / B1) — reproducible `semantic` schema for dev/CI

Applies supabase/semantic_schema.sql: creates the `semantic` schema, mirrors the
governed catalogs from public (LIKE … INCLUDING ALL), reproduces the read-only
RLS + grants, exposes semantic.releases as the semantic.semantic_releases view,
and installs semantic.upsert_semantic_release (the B2 write path).

Also a MERGE: it unifies the two pre-existing heads (the affix chain
0013_dataset_column_dimensions and the audit chain 0013_dataset_retention), so
`alembic upgrade head` resolves to a single head again.

All statements are idempotent (CREATE … IF NOT EXISTS / CREATE OR REPLACE /
DROP … IF EXISTS), so this is safe to re-run on an already-migrated DB (incl.
prod, where the `semantic` schema and its tables already exist).

Revision ID: 0014_semantic_schema
Revises: 0013_dataset_column_dimensions, 0013_dataset_retention
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0014_semantic_schema"
down_revision: tuple[str, ...] | str | None = (
    "0013_dataset_column_dimensions",
    "0013_dataset_retention",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# apps/api/supabase (parents: [0]=versions [1]=alembic [2]=apps/api)
_SCHEMA_FILE = Path(__file__).resolve().parents[2] / "supabase" / "semantic_schema.sql"


def upgrade() -> None:
    conn = op.get_bind()
    sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    # exec_driver_sql routes through the DBAPI paramstyle (pyformat): a literal `%`
    # (the format('… %I …') calls in the DDL loops) would be read as a parameter
    # marker. Double it for the driver; psycopg/asyncpg collapses it back to `%`.
    conn.exec_driver_sql(sql.replace("%", "%%"))


def downgrade() -> None:
    op.execute("drop schema if exists semantic cascade;")
