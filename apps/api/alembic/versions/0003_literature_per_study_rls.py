"""literature snapshots : visibilité par-étude (Tier 3, gate 9)

0002 a posé une RLS d'isolation tenant simple (org_id) sur literature_snapshots.
Cette migration la remplace par un accès gaté PAR ÉTUDE :

  - study_id NON NULL ⇒ visible aux MEMBRES de l'étude (study_members), pas à tout
    le tenant. Point critique (gate 9) : on gate par study_members, JAMAIS par
    study_id seul — sinon un snapshot fuiterait entre études du même tenant. Un
    non-membre échoue fermé (l'EXISTS est faux ⇒ ligne invisible).
  - study_id NULL ⇒ snapshot standalone, visible de son seul créateur (created_by).

WITH CHECK : écriture pour le tenant courant uniquement, en tant que créateur, et —
si rattaché à une étude — seulement si on en est membre. app.user_id non posé ⇒
tout échoue fermé.

search_sessions / literature_events / literature_queries gardent l'isolation tenant
de 0002 (inchangées ici).

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
    # Remplace la policy d'isolation tenant simple de 0002 par le gating par-étude.
    # Idempotent : on retire AUSSI une éventuelle policy déjà posée par le bundle
    # canonique (0001_baseline → policies.sql) pour ne JAMAIS laisser deux policies
    # permissives sur literature_snapshots (sinon l'isolation tenant seule élargirait
    # l'accès et casserait gate 9). État final garanti : une seule policy par-étude.
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
