"""Add retention_until column to datasets table (idempotent).

Adds a nullable timestamptz column that marks when a dataset's data
should be purged (GDPR Art 5(1)(e) storage limitation principle).
The purge itself is triggered by DatasetService.purge_expired(), which
must be scheduled as an ops step (e.g. Modal cron / pg_cron).
"""

from alembic import op

revision = "0013_dataset_retention"
down_revision = "0012_audit_events"
branch_labels = None
depends_on = None

_UPGRADE = """
alter table datasets add column if not exists retention_until timestamptz;
create index if not exists ix_datasets_retention_until
    on datasets (retention_until)
    where retention_until is not null;
"""


def upgrade() -> None:
    op.execute(_UPGRADE)


def downgrade() -> None:
    # Intentionally left as no-op; dropping a column on a live DB
    # requires a coordinated migration — prefer forward-only deployments.
    pass
