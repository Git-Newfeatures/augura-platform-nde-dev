"""dataset_files: one dataset holds many CSV files (union of columns)

Adds the dataset_files table + its tenant_via_dataset RLS policy (mirrors
dataset_columns), and backfills one file row per existing single-file dataset so
legacy datasets keep working as "a dataset with one file". Idempotent: CREATE …
IF NOT EXISTS, DROP POLICY IF EXISTS, and a NOT EXISTS-guarded backfill. The table
also lives in the canonical bundle schema.sql executed by 0001_baseline.

Revision ID: 0010_dataset_files
Revises: 0009_artifacts_kind_document
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_dataset_files"
down_revision: str | None = "0009_artifacts_kind_document"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists dataset_files (
            id           uuid primary key default gen_random_uuid(),
            dataset_id   uuid not null references datasets(id) on delete cascade,
            filename     text not null,
            storage_path text not null,
            row_count    integer,
            headers      jsonb,
            position     integer not null default 0,
            created_at   timestamptz not null default now()
        );
        """
    )
    op.execute("create index if not exists ix_dataset_files_dataset on dataset_files(dataset_id);")
    op.execute("alter table dataset_files enable row level security;")
    op.execute("alter table dataset_files force row level security;")
    op.execute("drop policy if exists tenant_via_dataset on dataset_files;")
    op.execute(
        """
        create policy tenant_via_dataset on dataset_files
            using (exists (
                select 1 from datasets d
                where d.id = dataset_files.dataset_id
                  and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
            ))
            with check (exists (
                select 1 from datasets d
                where d.id = dataset_files.dataset_id
                  and d.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
            ));
        """
    )
    op.execute(
        """
        insert into dataset_files (dataset_id, filename, storage_path, row_count, position)
        select d.id, d.name, d.storage_path, d.row_count, 0
        from datasets d
        where d.storage_path is not null
          and not exists (select 1 from dataset_files f where f.dataset_id = d.id);
        """
    )


def downgrade() -> None:
    op.execute("drop policy if exists tenant_via_dataset on dataset_files;")
    op.execute("drop table if exists dataset_files;")
