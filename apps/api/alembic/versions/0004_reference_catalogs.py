"""reference catalogs: config tables for the real-only frontend cleanup

Global catalogs (read-only, RLS backend_read) consumed by the frontend in place
of hard-coded constants. Idempotent (IF NOT EXISTS): these objects also live in
the canonical bundle schema.sql + policies.sql executed by 0001_baseline.

Revision ID: 0004_reference_catalogs
Revises: 0003_literature_per_study_rls
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_reference_catalogs"
down_revision: str | None = "0003_literature_per_study_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "outcome_catalog",
    "estimand_catalog",
    "estimator_catalog",
    "framework_catalog",
    "evidence_type_catalog",
    "domain_catalog",
    "jurisdiction_catalog",
    "literature_design_catalog",
    "pii_pattern_catalog",
    "biomarker_range_catalog",
    "variable_group_catalog",
    "variable_role_catalog",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cesl_sources       ADD COLUMN IF NOT EXISTS default_evidence_type text;
        ALTER TABLE cesl_study_designs ADD COLUMN IF NOT EXISTS description text;
        ALTER TABLE cesl_study_designs ADD COLUMN IF NOT EXISTS tags
            jsonb NOT NULL DEFAULT '[]'::jsonb;
        ALTER TABLE cesl_study_designs ADD COLUMN IF NOT EXISTS estimands
            jsonb NOT NULL DEFAULT '[]'::jsonb;

        CREATE TABLE IF NOT EXISTS outcome_catalog (
            code text PRIMARY KEY, short_key text NOT NULL, label text NOT NULL, unit text,
            is_primary boolean NOT NULL DEFAULT false, description text,
            regulatory_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
            verdict text, verdict_label text,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS estimand_catalog (
            key text PRIMARY KEY, name text NOT NULL, description text, regulatory text,
            recommended boolean NOT NULL DEFAULT false, tag text,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS estimator_catalog (
            key text PRIMARY KEY, label text NOT NULL, short text NOT NULL,
            recommended boolean NOT NULL DEFAULT false,
            bootstrap_pending boolean NOT NULL DEFAULT false,
            interpretability int NOT NULL DEFAULT 0,
            stability boolean NOT NULL DEFAULT true, tooltip text,
            eligible_study_types jsonb NOT NULL DEFAULT '[]'::jsonb,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS framework_catalog (
            code text PRIMARY KEY, label text NOT NULL,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS evidence_type_catalog (
            code text PRIMARY KEY, label text NOT NULL, description text,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS domain_catalog (
            code text PRIMARY KEY, label text NOT NULL,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS jurisdiction_catalog (
            code text PRIMARY KEY, label text NOT NULL,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS literature_design_catalog (
            code text PRIMARY KEY, label text NOT NULL,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS pii_pattern_catalog (
            key text PRIMARY KEY, label text NOT NULL, pattern text NOT NULL,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS biomarker_range_catalog (
            code text PRIMARY KEY, pattern text NOT NULL,
            value_min numeric, value_max numeric, unit text,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS variable_group_catalog (
            code text PRIMARY KEY, label text, description text, alias_of text,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS variable_role_catalog (
            code text PRIMARY KEY, label text NOT NULL, group_code text,
            selectable boolean NOT NULL DEFAULT true,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        """
    )
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS backend_read ON {table};")
        op.execute(
            f"""
            CREATE POLICY backend_read ON {table}
                FOR SELECT
                USING (nullif(current_setting('app.tenant_id', true), '') IS NOT NULL);
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
    op.execute("ALTER TABLE cesl_study_designs DROP COLUMN IF EXISTS estimands;")
    op.execute("ALTER TABLE cesl_study_designs DROP COLUMN IF EXISTS tags;")
    op.execute("ALTER TABLE cesl_study_designs DROP COLUMN IF EXISTS description;")
    op.execute("ALTER TABLE cesl_sources DROP COLUMN IF EXISTS default_evidence_type;")
