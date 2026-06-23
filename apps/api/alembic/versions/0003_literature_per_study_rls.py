"""literature snapshots: per-study visibility (Tier 3, gate 9)

0002 set a simple tenant-isolation RLS (org_id) on literature_snapshots.
This migration replaces it with PER-STUDY gated access:

  - study_id NOT NULL ⇒ visible to the study's MEMBERS (study_members), not the
    whole tenant. Critical point (gate 9): we gate by study_members, NEVER by
    study_id alone — otherwise a snapshot would leak between studies of the same
    tenant. A non-member fails closed (the EXISTS is false ⇒ row invisible).
  - study_id NULL ⇒ standalone snapshot, visible only to its creator (created_by).

WITH CHECK: write for the current tenant only, as the creator, and — if attached
to a study — only if one is a member of it. app.user_id not set ⇒ everything fails
closed.

search_sessions / literature_events / literature_queries keep the tenant isolation
from 0002 (unchanged here).

Revision ID: 0003_literature_per_study_rls
Revises: 0002_literature_live_search
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_literature_per_study_rls"
down_revision: str | None = "0002_literature_live_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"
_USER = "nullif(current_setting('app.user_id', true), '')::uuid"


def upgrade() -> None:
    # Replaces 0002's simple tenant-isolation policy with per-study gating.
    # Idempotent: we ALSO drop any policy that may have been set by the canonical
    # bundle (0001_baseline → policies.sql) so we NEVER leave two permissive policies
    # on literature_snapshots (otherwise tenant isolation alone would widen access
    # and break gate 9). Guaranteed final state: a single per-study policy.
    op.execute(
        "DROP POLICY IF EXISTS literature_snapshots_tenant_isolation ON literature_snapshots;"
    )
    op.execute("DROP POLICY IF EXISTS snapshot_tenant_study_access ON literature_snapshots;")
    op.execute(
        f"""
        CREATE POLICY snapshot_tenant_study_access ON literature_snapshots
            USING (
                org_id = {_TENANT}
                AND (
                    (study_id IS NULL AND created_by = {_USER})
                    OR (study_id IS NOT NULL AND EXISTS (
                        SELECT 1 FROM study_members m
                        WHERE m.study_id = literature_snapshots.study_id
                          AND m.user_id = {_USER}
                    ))
                )
            )
            WITH CHECK (
                org_id = {_TENANT}
                AND created_by = {_USER}
                AND (
                    study_id IS NULL
                    OR EXISTS (
                        SELECT 1 FROM study_members m
                        WHERE m.study_id = literature_snapshots.study_id
                          AND m.user_id = {_USER}
                    )
                )
            );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS snapshot_tenant_study_access ON literature_snapshots;")
    op.execute(
        f"""
        CREATE POLICY literature_snapshots_tenant_isolation ON literature_snapshots
            USING (org_id = {_TENANT})
            WITH CHECK (org_id = {_TENANT});
        """
    )
