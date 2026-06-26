"""dataset_columns: proposed/final canonical dimensions (affix decomposition output)

Adds two nullable jsonb columns where the runtime stores the canonical dimensions
decomposed from a column label by the affix archetypes (semantic layer v3 §2.7) —
the join point with grain-derived dimensions (North Star Step 1.3). Tenant-scoped
via the dataset's org (existing dataset_columns RLS covers them). Idempotent (ADD
COLUMN IF NOT EXISTS); the columns also live in the canonical schema.sql.

Revision ID: 0013_dataset_column_dimensions
Revises: 0012_affix_release_function
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_dataset_column_dimensions"
down_revision: str | None = "0012_affix_release_function"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table dataset_columns add column if not exists proposed_dimensions jsonb;")
    op.execute("alter table dataset_columns add column if not exists final_dimensions jsonb;")


def downgrade() -> None:
    op.execute("alter table dataset_columns drop column if exists final_dimensions;")
    op.execute("alter table dataset_columns drop column if exists proposed_dimensions;")
