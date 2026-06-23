# Frontend Real-Only Cleanup — Backend Catalogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add backend reference/catalog endpoints under `/reference/*` so the frontend can fetch every domain catalog it currently hardcodes (outcomes, estimands, estimators, study designs, frameworks, corpus classification labels, DQ rules, variable roles), seeded verbatim from the current frontend constants.

**Architecture:** Extend the existing `modules/reference` module (`router → service → repo → SQLAlchemy model`), seeded via `supabase/seed.sql`, with `backend_read` RLS (read-only, any authenticated tenant) exactly like `cesl_sources`. New tables are created idempotently in a new Alembic revision **and** mirrored in the canonical `supabase/schema.sql` + `supabase/policies.sql` bundle (the baseline source of truth). All endpoints are global read-only reference data behind `CurrentTenantDep` + `SessionDep`.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async, `Mapped[]`), Pydantic v2, Alembic, PostgreSQL (asyncpg), pytest (`asyncio_mode=auto`), ruff, pyright.

**Companion plan:** `2026-06-17-frontend-real-only-cleanup-frontend.md` (Phase B — consumes these endpoints and strips the frontend constants). Do that plan **after** this one.

**Spec:** `docs/superpowers/specs/2026-06-17-frontend-real-only-cleanup-design.md`

---

## Endpoint & table inventory

| Endpoint | Table(s) | Source constant (frontend) |
|---|---|---|
| `GET /reference/outcomes` | `outcome_catalog` | `OUTCOME_CATALOG` (OutcomeSelection.jsx:15) |
| `GET /reference/study-designs` *(enrich existing)* | `cesl_study_designs` (+cols) | `getStudyDesigns()` (StudyType.jsx:16) |
| `GET /reference/estimands` | `estimand_catalog` | `ESTIMAND_OPTS` (StudyType.jsx:57) |
| `GET /reference/estimators` | `estimator_catalog` | `ESTIMATORS`+`ESTIMATOR_FILTER` (config.js:20) |
| `GET /reference/frameworks` | `framework_catalog` | `FRAMEWORKS` (NewStudyPage.jsx:9) |
| `GET /reference/evidence-types` | `evidence_type_catalog` | `ET_LABELS`+`ET_DESCRIPTIONS` (CorpusPanelEmbed.jsx:12) |
| `GET /reference/domains` | `domain_catalog` | `DOMAIN_LABELS` (CorpusPanelEmbed.jsx:56) |
| `GET /reference/jurisdictions` | `jurisdiction_catalog` | `JUR_LABELS` (CorpusPanelEmbed.jsx:76) |
| `GET /reference/literature-study-designs` | `literature_design_catalog` | `STUDY_DESIGN_FALLBACK` (ProfilingAssistant.jsx:11) |
| `GET /reference/dq-rules` | `pii_pattern_catalog`, `biomarker_range_catalog` | `PII_PATTERNS` (DatasetVerification.jsx:9), `RANGES`+`ID_COLS` (ProfilingAssistant.jsx:72/87) |
| `GET /reference/variable-roles` | `variable_group_catalog`, `variable_role_catalog` | `GROUPS`/`GROUP_REMAP`/`ROLES`/`ROLE_LABEL` (DatasetVerification.jsx:35-64) |

Also: add `default_evidence_type` column to existing `cesl_sources` (replaces `SOURCE_ET_DEFAULTS`, CorpusPanelEmbed.jsx:130).

All commands below run from `apps/api/` unless noted.

---

## Task 1: SQLAlchemy models

**Files:**
- Modify: `apps/api/src/augura_api/modules/reference/models.py`

- [ ] **Step 1: Add new model classes + columns**

Append these model classes to `models.py` (keep the existing `Org`, `CeslSource`, `CeslStudyDesign`). Add the new columns to `CeslSource` and `CeslStudyDesign` in place.

In `CeslSource`, add after `result_unit`:
```python
    default_evidence_type: Mapped[str | None] = mapped_column(Text)
```

In `CeslStudyDesign`, add after `group_name`:
```python
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    estimands: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
```

Append the new models:
```python
class OutcomeCatalog(Base):
    __tablename__ = "outcome_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    short_key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text)
    regulatory_tags: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    verdict: Mapped[str | None] = mapped_column(Text)
    verdict_label: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class EstimandCatalog(Base):
    __tablename__ = "estimand_catalog"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    regulatory: Mapped[str | None] = mapped_column(Text)
    recommended: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    tag: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class EstimatorCatalog(Base):
    __tablename__ = "estimator_catalog"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    short: Mapped[str] = mapped_column(Text)
    recommended: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    bootstrap_pending: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    interpretability: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    stability: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    tooltip: Mapped[str | None] = mapped_column(Text)
    eligible_study_types: Mapped[Any] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class FrameworkCatalog(Base):
    __tablename__ = "framework_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class EvidenceTypeCatalog(Base):
    __tablename__ = "evidence_type_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class DomainCatalog(Base):
    __tablename__ = "domain_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class JurisdictionCatalog(Base):
    __tablename__ = "jurisdiction_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class LiteratureDesignCatalog(Base):
    __tablename__ = "literature_design_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class PiiPatternCatalog(Base):
    __tablename__ = "pii_pattern_catalog"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    pattern: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class BiomarkerRangeCatalog(Base):
    __tablename__ = "biomarker_range_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    pattern: Mapped[str] = mapped_column(Text)
    value_min: Mapped[float | None] = mapped_column(Numeric)
    value_max: Mapped[float | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class VariableGroupCatalog(Base):
    __tablename__ = "variable_group_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    alias_of: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class VariableRoleCatalog(Base):
    __tablename__ = "variable_role_catalog"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    group_code: Mapped[str | None] = mapped_column(Text)
    selectable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
```

- [ ] **Step 2: Update the imports at the top of `models.py`**

Ensure the SQLAlchemy import line includes `Numeric` (used by `BiomarkerRangeCatalog` to match the `numeric` DDL):
```python
from sqlalchemy import Boolean, Integer, Numeric, Text, text
```

- [ ] **Step 3: Verify the module imports cleanly**

Run: `python -c "import augura_api.modules.reference.models as m; print(sorted(t for t in dir(m) if t.endswith('Catalog')))"`
Expected: prints the 11 new `*Catalog` class names (no ImportError).

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/augura_api/modules/reference/models.py
git commit -m "feat(reference): SQLAlchemy models for catalog tables"
```

---

## Task 2: DDL, RLS, and Alembic migration

**Files:**
- Modify: `apps/api/supabase/schema.sql` (after the `cesl_study_designs` block, ~line 400)
- Modify: `apps/api/supabase/policies.sql` (after the `cesl_study_designs` policy, ~line 222)
- Create: `apps/api/alembic/versions/0004_reference_catalogs.py`

- [ ] **Step 1: Add canonical DDL to `schema.sql`**

After the `cesl_study_designs` table definition (line 400), add the new columns and tables:
```sql
-- Reference catalogs (config — frontend real-only cleanup). All global,
-- read-only for tenant sessions (RLS backend_read in policies.sql).
alter table cesl_sources       add column if not exists default_evidence_type text;
alter table cesl_study_designs add column if not exists description text;
alter table cesl_study_designs add column if not exists tags       jsonb not null default '[]'::jsonb;
alter table cesl_study_designs add column if not exists estimands  jsonb not null default '[]'::jsonb;

create table if not exists outcome_catalog (
    code            text primary key,
    short_key       text not null,
    label           text not null,
    unit            text,
    is_primary      boolean not null default false,
    description     text,
    regulatory_tags jsonb   not null default '[]'::jsonb,
    verdict         text,
    verdict_label   text,
    sort_order      int     not null default 0,
    active          boolean not null default true
);

create table if not exists estimand_catalog (
    key         text primary key,
    name        text not null,
    description text,
    regulatory  text,
    recommended boolean not null default false,
    tag         text,
    sort_order  int     not null default 0,
    active      boolean not null default true
);

create table if not exists estimator_catalog (
    key                  text primary key,
    label                text not null,
    short                text not null,
    recommended          boolean not null default false,
    bootstrap_pending    boolean not null default false,
    interpretability     int     not null default 0,
    stability            boolean not null default true,
    tooltip              text,
    eligible_study_types jsonb   not null default '[]'::jsonb,
    sort_order           int     not null default 0,
    active               boolean not null default true
);

create table if not exists framework_catalog (
    code text primary key, label text not null,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists evidence_type_catalog (
    code text primary key, label text not null, description text,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists domain_catalog (
    code text primary key, label text not null,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists jurisdiction_catalog (
    code text primary key, label text not null,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists literature_design_catalog (
    code text primary key, label text not null,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists pii_pattern_catalog (
    key text primary key, label text not null, pattern text not null,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists biomarker_range_catalog (
    code text primary key, pattern text not null,
    value_min numeric, value_max numeric, unit text,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists variable_group_catalog (
    code text primary key, label text, description text, alias_of text,
    sort_order int not null default 0, active boolean not null default true
);

create table if not exists variable_role_catalog (
    code text primary key, label text not null, group_code text,
    selectable boolean not null default true,
    sort_order int not null default 0, active boolean not null default true
);
```

- [ ] **Step 2: Add RLS `backend_read` policies to `policies.sql`**

After the `cesl_study_designs` policy block (line 222), add:
```sql
-- ── Reference catalogs (frontend real-only cleanup): global, read-only ──
do $$
declare t text;
begin
  foreach t in array array[
    'outcome_catalog','estimand_catalog','estimator_catalog','framework_catalog',
    'evidence_type_catalog','domain_catalog','jurisdiction_catalog',
    'literature_design_catalog','pii_pattern_catalog','biomarker_range_catalog',
    'variable_group_catalog','variable_role_catalog'
  ] loop
    execute format('alter table %I enable row level security;', t);
    execute format('alter table %I force row level security;', t);
    execute format('drop policy if exists backend_read on %I;', t);
    execute format($f$create policy backend_read on %I for select
        using (nullif(current_setting('app.tenant_id', true), '') is not null);$f$, t);
  end loop;
end $$;
```

- [ ] **Step 3: Create the Alembic migration**

Create `apps/api/alembic/versions/0004_reference_catalogs.py`. Mirror the idempotent style of `0002`. Copy the **exact** `create table` statements from schema.sql Step 1 into the `op.execute(""" … """)` block (CREATE TABLE IF NOT EXISTS + the three `alter table … add column if not exists`), then the RLS loop from Step 2.

```python
"""reference catalogs: config tables for the frontend real-only cleanup

Global catalogs (read-only, RLS backend_read) consumed by the frontend in place
of the hardcoded constants. Idempotent (IF NOT EXISTS): these objects also live
in the canonical schema.sql + policies.sql bundle executed by 0001_baseline.

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
    "outcome_catalog", "estimand_catalog", "estimator_catalog", "framework_catalog",
    "evidence_type_catalog", "domain_catalog", "jurisdiction_catalog",
    "literature_design_catalog", "pii_pattern_catalog", "biomarker_range_catalog",
    "variable_group_catalog", "variable_role_catalog",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cesl_sources       ADD COLUMN IF NOT EXISTS default_evidence_type text;
        ALTER TABLE cesl_study_designs ADD COLUMN IF NOT EXISTS description text;
        ALTER TABLE cesl_study_designs ADD COLUMN IF NOT EXISTS tags       jsonb NOT NULL DEFAULT '[]'::jsonb;
        ALTER TABLE cesl_study_designs ADD COLUMN IF NOT EXISTS estimands  jsonb NOT NULL DEFAULT '[]'::jsonb;

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
            recommended boolean NOT NULL DEFAULT false, bootstrap_pending boolean NOT NULL DEFAULT false,
            interpretability int NOT NULL DEFAULT 0, stability boolean NOT NULL DEFAULT true, tooltip text,
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
            code text PRIMARY KEY, pattern text NOT NULL, value_min numeric, value_max numeric, unit text,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS variable_group_catalog (
            code text PRIMARY KEY, label text, description text, alias_of text,
            sort_order int NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true);
        CREATE TABLE IF NOT EXISTS variable_role_catalog (
            code text PRIMARY KEY, label text NOT NULL, group_code text, selectable boolean NOT NULL DEFAULT true,
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
```

- [ ] **Step 4: Verify the migration imports and the revision chain is intact**

Run: `python -c "import importlib.util,glob; [importlib.util.spec_from_file_location('m',f) for f in glob.glob('alembic/versions/0004_*.py')]; print('ok')"`
Then: `python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print(s.get_current_head())"`
Expected: prints `0004_reference_catalogs` (the new head; no "multiple heads" / KeyError).

- [ ] **Step 5: Commit**

```bash
git add apps/api/supabase/schema.sql apps/api/supabase/policies.sql apps/api/alembic/versions/0004_reference_catalogs.py
git commit -m "feat(reference): DDL + RLS + migration for catalog tables"
```

---

## Task 3: Seed data

**Files:**
- Modify: `apps/api/supabase/seed.sql` (after the `cesl_study_designs` insert block, line 28)

> All string values below are transcribed verbatim from the frontend constants
> cited in the inventory table. Preserve punctuation, em-dashes, and unicode
> (e.g. `kg/m²`, `🇺🇸`) exactly.

- [ ] **Step 1: Enrich `cesl_study_designs` rows (UPDATE) and append all catalog INSERTs**

Append to `seed.sql`:
```sql
-- ── Reference catalogs (frontend real-only cleanup) ───────────────────────
-- Enrich the StudyType selector designs. {partner} is interpolated client-side.
update cesl_study_designs set
  description = 'Stratify existing users by engagement level (HIGH vs REST). Measure biomarker change between groups. Fast, no new data required.',
  tags = '[["g","{partner} data available"],["b","DiGA / HAS eligible"],["a","Observational — confounding risk"]]'::jsonb,
  estimands = '["ATE","ATT"]'::jsonb
  where code = 'retro_cohort';
update cesl_study_designs set
  description = 'Compare each user''s biomarkers before and after joining {partner}. No separate control group — uses within-person change.',
  tags = '[["g","Simple"],["b","No external data"],["a","No control group — regression to mean risk"]]'::jsonb,
  estimands = '["ATE"]'::jsonb
  where code = 'pre_post';
update cesl_study_designs set
  description = 'Match {partner} users to external non-users (e.g. Constances cohort). Stronger causal interpretation than internal comparison.',
  tags = '[["b","Stronger causal claim"],["a","Requires external dataset"],["a","Matching complexity"]]'::jsonb,
  estimands = '["ATE","ATT"]'::jsonb
  where code = 'external_matched';
update cesl_study_designs set
  description = 'Decompose total effect into direct (platform → HbA1c) and indirect (via behaviour change). Different causal question — cannot be combined with total-effect estimators.',
  tags = '[["b","Mechanism analysis"],["b","Scientific differentiator"],["a","Stronger assumptions required"]]'::jsonb,
  estimands = '["MEDIATION"]'::jsonb
  where code = 'mediation';

-- Default evidence type per corpus source (was SOURCE_ET_DEFAULTS).
update cesl_sources set default_evidence_type = 'trial_record'   where code = 'clinicaltrials';
update cesl_sources set default_evidence_type = 'adverse_events' where code = 'maude';
update cesl_sources set default_evidence_type = 'guidance'       where code = 'guidance';
update cesl_sources set default_evidence_type = 'rwe_study'      where code = 'pubmed';

insert into outcome_catalog (code, short_key, label, unit, is_primary, description, regulatory_tags, verdict, verdict_label, sort_order, active) values
  ('hba1c_pct',   'hba1c',   'HbA1c change',            '%',     true,  'Gold-standard cardiometabolic endpoint. Widely accepted by DiGA, NICE DSP, and HAS for digital health interventions.',                 '[["g","DiGA · NICE · HAS"]]'::jsonb,        'g', '★ Recommended',        10, true),
  ('ldl_mgdl',    'ldl',     'LDL-C change',            'mg/dL', true,  'Standard lipid endpoint. Note: medication changes are an uncontrolled confounder — sensitivity analysis required.',                  '[["a","Medication confounder"]]'::jsonb,    'b', 'Good option',          20, true),
  ('hs_crp_mgl',  'crp',     'hs-CRP change',           'mg/L',  true,  'Inflammatory marker. High within-person variability limits precision as a primary endpoint — better as secondary.',                  '[["a","High variability"]]'::jsonb,         'a', 'Secondary preferred',  30, true),
  ('glucose_mmol','glucose', 'Fasting glucose change',  'mmol/L',true,  'Direct diabetes risk marker. Accepted by HAS and DiGA as a primary or co-primary endpoint.',                                        '[["b","HAS · DiGA"]]'::jsonb,               'b', 'Good option',          40, true),
  ('bmi',         'bmi',     'BMI change',              'kg/m²', false, 'Anthropometric endpoint. Widely used as secondary in lifestyle intervention studies.',                                              '[["b","Secondary / co-primary"]]'::jsonb,   'a', 'Secondary preferred',  50, true),
  ('weight_kg',   'weight',  'Body weight change',      'kg',    false, 'Common secondary endpoint in lifestyle and digital health studies.',                                                                 '[["b","Secondary"]]'::jsonb,                'a', 'Secondary preferred',  60, true),
  ('sbp_mmhg',    'sbp',     'Systolic BP change',      'mmHg',  false, 'Cardiovascular endpoint. Suitable as co-primary for hypertension-adjacent populations.',                                            '[["b","Cardiovascular"]]'::jsonb,           'a', 'Possible',             70, true),
  ('tg_mgdl',     'tg',      'Triglycerides change',    'mg/dL', false, 'Lipid panel component. Typically secondary alongside LDL-C.',                                                                        '[["b","Secondary"]]'::jsonb,                'a', 'Secondary preferred',  80, true)
on conflict (code) do nothing;

insert into estimand_catalog (key, name, description, regulatory, recommended, tag, sort_order, active) values
  ('ATE',       'ATE — Average Treatment Effect',                               'What would the effect of the intervention be if applied to the entire eligible population? Population-level causal effect — the default starting point for most causal questions.',                                                            'Conservative, broadly accepted across payer submissions (HAS, NICE DSP, DiGA).',                                            true,  NULL,                      10, true),
  ('ATT',       'ATT — Average Treatment effect on the Treated',                'What is the effect of the intervention specifically for users who actually received or engaged with it? Answers: ''did it work for the people who used it?''',                                                                                  'Preferred when treated and untreated populations differ structurally — common in real-world evidence.',                     false, NULL,                      20, true),
  ('CATE',      'CATE — Conditional ATE',                                       'The causal effect as a function of individual or subgroup covariates — ''which users benefit most?'' Enables personalised evidence claims. Requires larger N and careful regularisation.',                                                     'Heterogeneous effects — supports subgroup and personalised claims; estimated with Causal Forest / GRF, BART, or meta-learners.', false, 'Heterogeneous effects', 30, true),
  ('MEDIATION', 'Mediation Analysis — Direct, Indirect, Total Effects',         'Decomposes the total effect into the direct effect (intervention → outcome bypassing the mediator) and the indirect effect (intervention → mediator → outcome). Use when the mechanism of action matters, not just the headline effect.',      'Mechanism evidence — supports HTA narratives but typically paired with ATE/ATT as the primary estimand.',                   false, NULL,                      40, true)
on conflict (key) do nothing;

insert into estimator_catalog (key, label, short, recommended, bootstrap_pending, interpretability, stability, tooltip, eligible_study_types, sort_order, active) values
  ('lme',       'Mixed-effects (LME)',       'LME',       true,  false, 4, true,  'Best fit for longitudinal data with repeated measurements per user. Accounts for individual variation over time. Recommended for Lucis because biomarkers are measured every 3–6 months.',                                                  '["retro","prosp"]'::jsonb, 10, true),
  ('ols',       'Linear regression (OLS)',   'OLS',       false, false, 5, true,  'Simple benchmark model. Easier to interpret but assumes one measurement per user. Useful to compare against LME — if results diverge, the repeated-measures structure matters.',                                                            '["retro","prosp"]'::jsonb, 20, true),
  ('ipw',       'Propensity weighting (IPW)','IPW',       false, false, 3, false, 'Reweights users so the HIGH and REST groups look comparable on observed characteristics (age, BMI, baseline HbA1c). Useful when the groups differ at baseline. Higher variance than LME.',                                                  '["retro"]'::jsonb,         30, true),
  ('mediation', 'Causal mediation',          'Mediation', true,  false, 3, true,  'Splits the total effect into direct (platform → HbA1c) and indirect (platform → behaviour change → HbA1c). Quantifies how much of the benefit is driven by recommendation adherence.',                                                     '["retro","prosp"]'::jsonb, 40, true),
  ('tmle',      'TMLE (Doubly robust)',      'TMLE',      false, true,  2, true,  'Advanced method that combines outcome and propensity models. Remains valid even if one of the two models is misspecified. Most robust to confounding but requires larger samples.',                                                        '["retro","prosp"]'::jsonb, 50, true),
  ('did',       'Difference-in-differences', 'DID',       false, true,  4, false, 'Compares how much each group changed over time, rather than absolute levels. Controls for baseline differences that are stable over time. Requires that both groups would have evolved similarly without the intervention (parallel trends assumption).', '["retro"]'::jsonb, 60, true)
on conflict (key) do nothing;

insert into framework_catalog (code, label, sort_order, active) values
  ('diga',       'DiGA',       10, true),
  ('consort_ai', 'CONSORT-AI', 20, true),
  ('eu_mdr',     'EU MDR',     30, true),
  ('nice_dsp',   'NICE DSP',   40, true),
  ('eunethta',   'EUnetHTA',   50, true),
  ('fda_samd',   'FDA SaMD',   60, true)
on conflict (code) do nothing;

insert into evidence_type_catalog (code, label, description, sort_order, active) values
  ('guidance',       'Guidance',       'Regulatory guidance documents (FDA, EMA, HAS, etc.) describing how a device or therapy should be evaluated, classified, or submitted.', 10, true),
  ('rwe_study',      'RWE study',      'Real-world evidence studies — observational research using routinely collected data (claims, EHR, registries, digital cohorts), not protocolised trials.', 20, true),
  ('rct',            'RCT',            'Randomised controlled trials — protocolised interventional studies with random assignment to treatment groups.', 30, true),
  ('preprint',       'Preprint',       'Pre-publication manuscripts (e.g. medRxiv, bioRxiv) — not yet peer-reviewed.', 40, true),
  ('trial_record',   'Trial record',   'ClinicalTrials.gov or similar registry entries describing trial protocols, recruitment status, and primary endpoints.', 50, true),
  ('meta_analysis',  'Meta-analysis',  'Systematic reviews and meta-analyses aggregating evidence across multiple primary studies.', 60, true),
  ('adverse_events', 'Adverse events', 'Post-market safety reports submitted to regulators (e.g. MAUDE) describing device-related incidents or failures.', 70, true),
  ('other',          'Other',          'Documents not classified into a primary evidence type.', 80, true)
on conflict (code) do nothing;

insert into domain_catalog (code, label, sort_order, active) values
  ('cardiometabolic','Cardiometabolic',10,true), ('womens_health','Women''s health',20,true),
  ('preventive_health','Preventive health',30,true), ('patient_monitoring','Patient monitoring',40,true),
  ('oncology_dx','Oncology DX',50,true), ('neurology','Neurology',60,true),
  ('respiratory','Respiratory',70,true), ('infectious_disease','Infectious disease',80,true),
  ('ophthalmology','Ophthalmology',90,true), ('radiology_ai','Radiology AI',100,true),
  ('mental_health','Mental health',110,true), ('gastroenterology','Gastroenterology',120,true),
  ('samd_general','SaMD general',130,true), ('samd_biomarker','SaMD biomarker',140,true),
  ('regulatory_general','Regulatory general',150,true), ('adverse_events','Adverse events',160,true),
  ('other','Other',170,true)
on conflict (code) do nothing;

insert into jurisdiction_catalog (code, label, sort_order, active) values
  ('fda','FDA 🇺🇸',10,true), ('ema','EMA 🇪🇺',20,true), ('mhra','MHRA 🇬🇧',30,true),
  ('health_ca','Health CA 🇨🇦',40,true), ('tga','TGA 🇦🇺',50,true),
  ('imdrf','IMDRF 🌐',60,true), ('global','Global 🌐',70,true)
on conflict (code) do nothing;

insert into literature_design_catalog (code, label, sort_order, active) values
  ('rct_parallel','Parallel-group RCT',10,true), ('rct_crossover','Crossover RCT',20,true),
  ('single_arm','Single-arm trial',30,true), ('prospective_cohort','Prospective cohort',40,true),
  ('retrospective_cohort','Retrospective cohort',50,true), ('registry','Registry study',60,true),
  ('case_control','Case-control',70,true), ('pre_post','Pre-post analysis',80,true),
  ('difference_in_diff','Difference-in-differences',90,true),
  ('propensity_matched','Propensity score matching',100,true),
  ('interrupted_ts','Interrupted time series',110,true),
  ('regression_discontinuity','Regression discontinuity',120,true),
  ('parametric_bootstrap','Parametric bootstrap',130,true)
on conflict (code) do nothing;

-- PII column-name patterns (was PII_PATTERNS). `pattern` is the JS regex SOURCE
-- (no slashes/flags); the client rebuilds `new RegExp(pattern, "i")`.
insert into pii_pattern_catalog (key, label, pattern, sort_order, active) values
  ('name',     'name field',     '\b(first_?name|last_?name|full_?name|given_?name|family_?name)\b', 10, true),
  ('email',    'email',          '\bemail|e_mail|e-mail\b',                                          20, true),
  ('phone',    'phone',          '\bphone|mobile|telephone\b',                                       30, true),
  ('address',  'postal address', '\baddress|street|postal|zip_?code|postcode\b',                     40, true),
  ('dob',      'date of birth',  '\b(dob|date_?of_?birth|birth_?date|birthday)\b',                   50, true),
  ('govid',    'government ID',  '\b(ssn|social_?security|national_?id|nhs_?number|nin)\b',          60, true),
  ('passport', 'passport',       '\bpassport\b',                                                     70, true),
  ('ip',       'IP address',     '\bip_?address\b',                                                  80, true),
  ('device',   'device ID',      '\bdevice_?id\b',                                                   90, true)
on conflict (key) do nothing;

-- Biomarker plausibility ranges (was RANGES). `pattern` is the JS regex source.
insert into biomarker_range_catalog (code, pattern, value_min, value_max, unit, sort_order, active) values
  ('hba1c', 'hba1c',           4,  15,  '%',     10, true),
  ('ldl',   '^ldl',            30, 400, 'mg/dL', 20, true),
  ('crp',   'hs_crp|hs-crp|crp',0, 100, 'mg/L',  30, true),
  ('bmi',   '^bmi$',           10, 70,  'kg/m²', 40, true),
  ('age',   '^age$',           18, 100, 'years', 50, true)
on conflict (code) do nothing;

-- Variable classification groups + aliases (was GROUPS + GROUP_REMAP).
insert into variable_group_catalog (code, label, description, alias_of, sort_order, active) values
  ('outcomes',      'Outcomes',                 'Dependent variables measured at follow-up', NULL, 10, true),
  ('exposure',      'Exposure / intervention',  'Primary treatment or intervention variable', NULL, 20, true),
  ('engagement',    'Engagement & environment', 'App usage, adherence, login, recommendation completion; geography, socioeconomic context, and healthcare system variables', NULL, 30, true),
  ('administrative','Administrative',           'Patient / member IDs, record keys, visit dates, timepoints, and columns not relevant to this study', NULL, 40, true),
  ('other',         'Other / unclassified',     'Cannot be confidently classified', NULL, 50, true),
  ('environment',    NULL, NULL, 'engagement',     100, true),
  ('user_variables', NULL, NULL, 'other',          110, true),
  ('mediators',      NULL, NULL, 'other',          120, true),
  ('measured_confounder',   NULL, NULL, 'other',   130, true),
  ('unmeasured_confounder', NULL, NULL, 'other',   140, true),
  ('collider',       NULL, NULL, 'other',          150, true),
  ('identifiers',    NULL, NULL, 'administrative', 160, true),
  ('time',           NULL, NULL, 'administrative', 170, true),
  ('unused',         NULL, NULL, 'administrative', 180, true)
on conflict (code) do nothing;

-- Causal roles (was ROLES + ROLE_LABEL). `selectable` marks the 8 picker roles.
insert into variable_role_catalog (code, label, group_code, selectable, sort_order, active) values
  ('outcome',               'Outcome',               'outcomes',       true,  10,  true),
  ('exposure',              'Exposure',              'exposure',       true,  20,  true),
  ('exposure_component',    'Exposure component',    'exposure',       true,  30,  true),
  ('effect_modifier',       'Effect modifier',       'engagement',     true,  40,  true),
  ('id',                    'ID',                    'administrative', true,  50,  true),
  ('time',                  'Time',                  'administrative', true,  60,  true),
  ('unused',                'Unused',                'administrative', true,  70,  true),
  ('other',                 'Other',                 'other',          true,  80,  true),
  ('measured_confounder',   'Measured confounder',   'other',          false, 90,  true),
  ('unmeasured_confounder', 'Unmeasured confounder', 'other',          false, 100, true),
  ('mediator',              'Mediator',              'other',          false, 110, true),
  ('collider',              'Collider',              'other',          false, 120, true)
on conflict (code) do nothing;
```

- [ ] **Step 2: Verify the SQL parses (syntax-only, no DB needed)**

Run: `python -c "import sqlparse,io" 2>/dev/null && python -c "import sqlparse; s=open('supabase/seed.sql').read(); print('statements:', len([x for x in sqlparse.split(s) if x.strip()]))" || echo "sqlparse not installed — visually confirm balanced quotes/parens"`
Expected: prints a statement count (or the fallback message). Manually confirm the doubled single-quotes in `user''s` / `did''it` and the `{partner}` tokens are intact.

- [ ] **Step 3: Commit**

```bash
git add apps/api/supabase/seed.sql
git commit -m "feat(reference): seed catalog data from frontend constants"
```

---

## Task 4: Pydantic schemas

**Files:**
- Modify: `apps/api/src/augura_api/modules/reference/schemas.py`

- [ ] **Step 1: Extend `StudyDesignOut` and add the new `*Out` schemas**

Add `description`, `tags`, `estimands` to the existing `StudyDesignOut`:
```python
class StudyDesignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    group_name: str | None = None
    description: str | None = None
    tags: list[Any] = []
    estimands: list[str] = []
    sort_order: int
```

Append the new schemas (add `list` is built-in; reuse existing `Any` import):
```python
class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    short_key: str
    label: str
    unit: str | None = None
    is_primary: bool = False
    description: str | None = None
    regulatory_tags: list[Any] = []
    verdict: str | None = None
    verdict_label: str | None = None
    sort_order: int


class EstimandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    description: str | None = None
    regulatory: str | None = None
    recommended: bool = False
    tag: str | None = None
    sort_order: int


class EstimatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    short: str
    recommended: bool = False
    bootstrap_pending: bool = False
    interpretability: int = 0
    stability: bool = True
    tooltip: str | None = None
    eligible_study_types: list[str] = []
    sort_order: int


class FrameworkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    sort_order: int


class CodeLabelOut(BaseModel):
    """Shared shape for evidence-types, domains, jurisdictions, literature designs."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    description: str | None = None
    sort_order: int


class PiiPatternOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    pattern: str


class BiomarkerRangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    pattern: str
    value_min: float | None = None
    value_max: float | None = None
    unit: str | None = None


class DqRulesOut(BaseModel):
    pii_patterns: list[PiiPatternOut]
    biomarker_ranges: list[BiomarkerRangeOut]


class VariableGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    description: str | None = None


class VariableRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    group_code: str | None = None
    selectable: bool = True


class VariableRolesOut(BaseModel):
    groups: list[VariableGroupOut]
    roles: list[VariableRoleOut]
    group_aliases: dict[str, str]
```

- [ ] **Step 2: Verify schemas import**

Run: `python -c "from augura_api.modules.reference import schemas; print(schemas.DqRulesOut.__name__, schemas.VariableRolesOut.__name__)"`
Expected: `DqRulesOut VariableRolesOut`

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/augura_api/modules/reference/schemas.py
git commit -m "feat(reference): Pydantic schemas for catalog endpoints"
```

---

## Task 5: Repo + Service (TDD)

**Files:**
- Modify: `apps/api/tests/test_reference_service.py`
- Modify: `apps/api/src/augura_api/modules/reference/repo.py`
- Modify: `apps/api/src/augura_api/modules/reference/service.py`

- [ ] **Step 1: Write the failing service tests**

Append to `tests/test_reference_service.py`. Extend `_FakeRepo` with the new list methods and add assertions. These tests use a fake repo (no DB), matching the existing `test_cesl_sources_and_designs_map`.

```python
from augura_api.modules.reference.models import (
    BiomarkerRangeCatalog,
    DomainCatalog,
    EstimandCatalog,
    EstimatorCatalog,
    EvidenceTypeCatalog,
    FrameworkCatalog,
    JurisdictionCatalog,
    LiteratureDesignCatalog,
    OutcomeCatalog,
    PiiPatternCatalog,
    VariableGroupCatalog,
    VariableRoleCatalog,
)


class _FakeCatalogRepo:
    async def list_outcomes(self) -> list[OutcomeCatalog]:
        return [OutcomeCatalog(code="hba1c_pct", short_key="hba1c", label="HbA1c change",
                               unit="%", is_primary=True, regulatory_tags=[["g", "DiGA"]],
                               verdict="g", verdict_label="★ Recommended", sort_order=10)]

    async def list_estimands(self) -> list[EstimandCatalog]:
        return [EstimandCatalog(key="ATE", name="ATE — Average Treatment Effect",
                                recommended=True, sort_order=10)]

    async def list_estimators(self) -> list[EstimatorCatalog]:
        return [EstimatorCatalog(key="lme", label="Mixed-effects (LME)", short="LME",
                                 recommended=True, interpretability=4, stability=True,
                                 eligible_study_types=["retro", "prosp"], sort_order=10)]

    async def list_frameworks(self) -> list[FrameworkCatalog]:
        return [FrameworkCatalog(code="diga", label="DiGA", sort_order=10)]

    async def list_evidence_types(self) -> list[EvidenceTypeCatalog]:
        return [EvidenceTypeCatalog(code="rct", label="RCT", description="…", sort_order=30)]

    async def list_domains(self) -> list[DomainCatalog]:
        return [DomainCatalog(code="cardiometabolic", label="Cardiometabolic", sort_order=10)]

    async def list_jurisdictions(self) -> list[JurisdictionCatalog]:
        return [JurisdictionCatalog(code="fda", label="FDA 🇺🇸", sort_order=10)]

    async def list_literature_designs(self) -> list[LiteratureDesignCatalog]:
        return [LiteratureDesignCatalog(code="rct_parallel", label="Parallel-group RCT", sort_order=10)]

    async def list_pii_patterns(self) -> list[PiiPatternCatalog]:
        return [PiiPatternCatalog(key="email", label="email", pattern=r"\bemail\b", sort_order=20)]

    async def list_biomarker_ranges(self) -> list[BiomarkerRangeCatalog]:
        return [BiomarkerRangeCatalog(code="bmi", pattern="^bmi$", value_min=10, value_max=70, unit="kg/m²", sort_order=40)]

    async def list_variable_groups(self) -> list[VariableGroupCatalog]:
        return [
            VariableGroupCatalog(code="outcomes", label="Outcomes", description="…", alias_of=None, sort_order=10),
            VariableGroupCatalog(code="environment", label=None, description=None, alias_of="engagement", sort_order=100),
        ]

    async def list_variable_roles(self) -> list[VariableRoleCatalog]:
        return [VariableRoleCatalog(code="outcome", label="Outcome", group_code="outcomes", selectable=True, sort_order=10)]


async def test_outcomes_estimands_estimators_map() -> None:
    svc = ReferenceService(_FakeCatalogRepo())  # type: ignore[arg-type]
    outcomes = await svc.outcomes()
    estimands = await svc.estimands()
    estimators = await svc.estimators()
    assert outcomes[0].code == "hba1c_pct"
    assert outcomes[0].regulatory_tags == [["g", "DiGA"]]
    assert estimands[0].key == "ATE" and estimands[0].recommended is True
    assert estimators[0].eligible_study_types == ["retro", "prosp"]


async def test_dq_rules_groups_two_lists() -> None:
    svc = ReferenceService(_FakeCatalogRepo())  # type: ignore[arg-type]
    rules = await svc.dq_rules()
    assert rules.pii_patterns[0].key == "email"
    assert rules.biomarker_ranges[0].code == "bmi"


async def test_variable_roles_splits_aliases() -> None:
    svc = ReferenceService(_FakeCatalogRepo())  # type: ignore[arg-type]
    out = await svc.variable_roles()
    # canonical group only (alias row excluded from `groups`)
    assert [g.code for g in out.groups] == ["outcomes"]
    assert out.group_aliases == {"environment": "engagement"}
    assert out.roles[0].code == "outcome"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_reference_service.py -q`
Expected: FAIL — `AttributeError: 'ReferenceService' object has no attribute 'outcomes'` (and the new model imports resolve, since Task 1 added them).

- [ ] **Step 3: Add the repo methods**

Append to `ReferenceRepo` in `repo.py` (add the new model imports to the existing import line). Pattern: filter `active`, order by `sort_order`.
```python
    async def list_outcomes(self) -> list[OutcomeCatalog]:
        res = await self.session.execute(
            select(OutcomeCatalog).where(OutcomeCatalog.active.is_(True)).order_by(OutcomeCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_estimands(self) -> list[EstimandCatalog]:
        res = await self.session.execute(
            select(EstimandCatalog).where(EstimandCatalog.active.is_(True)).order_by(EstimandCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_estimators(self) -> list[EstimatorCatalog]:
        res = await self.session.execute(
            select(EstimatorCatalog).where(EstimatorCatalog.active.is_(True)).order_by(EstimatorCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_frameworks(self) -> list[FrameworkCatalog]:
        res = await self.session.execute(
            select(FrameworkCatalog).where(FrameworkCatalog.active.is_(True)).order_by(FrameworkCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_evidence_types(self) -> list[EvidenceTypeCatalog]:
        res = await self.session.execute(
            select(EvidenceTypeCatalog).where(EvidenceTypeCatalog.active.is_(True)).order_by(EvidenceTypeCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_domains(self) -> list[DomainCatalog]:
        res = await self.session.execute(
            select(DomainCatalog).where(DomainCatalog.active.is_(True)).order_by(DomainCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_jurisdictions(self) -> list[JurisdictionCatalog]:
        res = await self.session.execute(
            select(JurisdictionCatalog).where(JurisdictionCatalog.active.is_(True)).order_by(JurisdictionCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_literature_designs(self) -> list[LiteratureDesignCatalog]:
        res = await self.session.execute(
            select(LiteratureDesignCatalog).where(LiteratureDesignCatalog.active.is_(True)).order_by(LiteratureDesignCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_pii_patterns(self) -> list[PiiPatternCatalog]:
        res = await self.session.execute(
            select(PiiPatternCatalog).where(PiiPatternCatalog.active.is_(True)).order_by(PiiPatternCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_biomarker_ranges(self) -> list[BiomarkerRangeCatalog]:
        res = await self.session.execute(
            select(BiomarkerRangeCatalog).where(BiomarkerRangeCatalog.active.is_(True)).order_by(BiomarkerRangeCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_variable_groups(self) -> list[VariableGroupCatalog]:
        res = await self.session.execute(
            select(VariableGroupCatalog).where(VariableGroupCatalog.active.is_(True)).order_by(VariableGroupCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_variable_roles(self) -> list[VariableRoleCatalog]:
        res = await self.session.execute(
            select(VariableRoleCatalog).where(VariableRoleCatalog.active.is_(True)).order_by(VariableRoleCatalog.sort_order)
        )
        return list(res.scalars().all())
```

Update the import in `repo.py`:
```python
from augura_api.modules.reference.models import (
    BiomarkerRangeCatalog,
    CeslSource,
    CeslStudyDesign,
    DomainCatalog,
    EstimandCatalog,
    EstimatorCatalog,
    EvidenceTypeCatalog,
    FrameworkCatalog,
    JurisdictionCatalog,
    LiteratureDesignCatalog,
    Org,
    OutcomeCatalog,
    PiiPatternCatalog,
    VariableGroupCatalog,
    VariableRoleCatalog,
)
```

- [ ] **Step 4: Add the service methods**

Extend the `_RefReader` Protocol in `service.py` with the new method signatures (mirror the repo signatures), then add the service methods. Update the schema/model imports.

Add to the `_RefReader` Protocol body:
```python
    async def list_outcomes(self) -> list[OutcomeCatalog]: ...
    async def list_estimands(self) -> list[EstimandCatalog]: ...
    async def list_estimators(self) -> list[EstimatorCatalog]: ...
    async def list_frameworks(self) -> list[FrameworkCatalog]: ...
    async def list_evidence_types(self) -> list[EvidenceTypeCatalog]: ...
    async def list_domains(self) -> list[DomainCatalog]: ...
    async def list_jurisdictions(self) -> list[JurisdictionCatalog]: ...
    async def list_literature_designs(self) -> list[LiteratureDesignCatalog]: ...
    async def list_pii_patterns(self) -> list[PiiPatternCatalog]: ...
    async def list_biomarker_ranges(self) -> list[BiomarkerRangeCatalog]: ...
    async def list_variable_groups(self) -> list[VariableGroupCatalog]: ...
    async def list_variable_roles(self) -> list[VariableRoleCatalog]: ...
```

Add the service methods to `ReferenceService`:
```python
    async def outcomes(self) -> list[schemas.OutcomeOut]:
        return [schemas.OutcomeOut.model_validate(r) for r in await self.repo.list_outcomes()]

    async def estimands(self) -> list[schemas.EstimandOut]:
        return [schemas.EstimandOut.model_validate(r) for r in await self.repo.list_estimands()]

    async def estimators(self) -> list[schemas.EstimatorOut]:
        return [schemas.EstimatorOut.model_validate(r) for r in await self.repo.list_estimators()]

    async def frameworks(self) -> list[schemas.FrameworkOut]:
        return [schemas.FrameworkOut.model_validate(r) for r in await self.repo.list_frameworks()]

    async def evidence_types(self) -> list[schemas.CodeLabelOut]:
        return [schemas.CodeLabelOut.model_validate(r) for r in await self.repo.list_evidence_types()]

    async def domains(self) -> list[schemas.CodeLabelOut]:
        return [schemas.CodeLabelOut.model_validate(r) for r in await self.repo.list_domains()]

    async def jurisdictions(self) -> list[schemas.CodeLabelOut]:
        return [schemas.CodeLabelOut.model_validate(r) for r in await self.repo.list_jurisdictions()]

    async def literature_designs(self) -> list[schemas.CodeLabelOut]:
        return [schemas.CodeLabelOut.model_validate(r) for r in await self.repo.list_literature_designs()]

    async def dq_rules(self) -> schemas.DqRulesOut:
        return schemas.DqRulesOut(
            pii_patterns=[schemas.PiiPatternOut.model_validate(r) for r in await self.repo.list_pii_patterns()],
            biomarker_ranges=[schemas.BiomarkerRangeOut.model_validate(r) for r in await self.repo.list_biomarker_ranges()],
        )

    async def variable_roles(self) -> schemas.VariableRolesOut:
        rows = await self.repo.list_variable_groups()
        groups = [schemas.VariableGroupOut.model_validate(g) for g in rows if g.alias_of is None]
        aliases = {g.code: g.alias_of for g in rows if g.alias_of is not None}
        roles = [schemas.VariableRoleOut.model_validate(r) for r in await self.repo.list_variable_roles()]
        return schemas.VariableRolesOut(groups=groups, roles=roles, group_aliases=aliases)
```

Update the model import in `service.py`:
```python
from augura_api.modules.reference.models import (
    BiomarkerRangeCatalog,
    CeslSource,
    CeslStudyDesign,
    DomainCatalog,
    EstimandCatalog,
    EstimatorCatalog,
    EvidenceTypeCatalog,
    FrameworkCatalog,
    JurisdictionCatalog,
    LiteratureDesignCatalog,
    Org,
    OutcomeCatalog,
    PiiPatternCatalog,
    VariableGroupCatalog,
    VariableRoleCatalog,
)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_reference_service.py -q`
Expected: PASS (all tests, including the pre-existing ones).

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/test_reference_service.py apps/api/src/augura_api/modules/reference/repo.py apps/api/src/augura_api/modules/reference/service.py
git commit -m "feat(reference): repo + service for catalog endpoints (TDD)"
```

---

## Task 6: Router endpoints (TDD)

**Files:**
- Modify: `apps/api/tests/test_app_routes.py`
- Modify: `apps/api/src/augura_api/modules/reference/router.py`

- [ ] **Step 1: Write the failing route tests**

In `tests/test_app_routes.py`, add the new paths to the existing OpenAPI presence assertion and the auth assertion. Find the existing tuple of `/reference/*` paths in `test_openapi_exposes_routes` and extend it; add a new test for the catalog routes requiring auth.

```python
def test_openapi_exposes_reference_catalogs() -> None:
    paths = create_app().openapi()["paths"]
    for path in (
        "/reference/outcomes",
        "/reference/estimands",
        "/reference/estimators",
        "/reference/frameworks",
        "/reference/evidence-types",
        "/reference/domains",
        "/reference/jurisdictions",
        "/reference/literature-study-designs",
        "/reference/dq-rules",
        "/reference/variable-roles",
    ):
        assert path in paths, f"missing route: {path}"


async def test_reference_catalogs_require_auth() -> None:
    from httpx import ASGITransport, AsyncClient

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/reference/outcomes", "/reference/dq-rules", "/reference/variable-roles"):
            r = await client.get(path)
            assert r.status_code == 401
            assert r.json()["code"] == "unauthorized"
```

> Note: match the exact `AsyncClient` construction style already used in
> `test_app_routes.py` (`test_protected_routes_require_auth`); copy that test's
> client setup rather than the snippet above if it differs.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_app_routes.py -q`
Expected: FAIL — assertion error "missing route: /reference/outcomes".

- [ ] **Step 3: Add the router endpoints**

Append to `router.py` (after `study_designs`):
```python
@router.get("/outcomes", response_model=list[schemas.OutcomeOut])
async def outcomes(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.OutcomeOut]:
    return await _service(session).outcomes()


@router.get("/estimands", response_model=list[schemas.EstimandOut])
async def estimands(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.EstimandOut]:
    return await _service(session).estimands()


@router.get("/estimators", response_model=list[schemas.EstimatorOut])
async def estimators(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.EstimatorOut]:
    return await _service(session).estimators()


@router.get("/frameworks", response_model=list[schemas.FrameworkOut])
async def frameworks(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.FrameworkOut]:
    return await _service(session).frameworks()


@router.get("/evidence-types", response_model=list[schemas.CodeLabelOut])
async def evidence_types(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.CodeLabelOut]:
    return await _service(session).evidence_types()


@router.get("/domains", response_model=list[schemas.CodeLabelOut])
async def domains(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.CodeLabelOut]:
    return await _service(session).domains()


@router.get("/jurisdictions", response_model=list[schemas.CodeLabelOut])
async def jurisdictions(tenant: CurrentTenantDep, session: SessionDep) -> list[schemas.CodeLabelOut]:
    return await _service(session).jurisdictions()


@router.get("/literature-study-designs", response_model=list[schemas.CodeLabelOut])
async def literature_study_designs(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.CodeLabelOut]:
    return await _service(session).literature_designs()


@router.get("/dq-rules", response_model=schemas.DqRulesOut)
async def dq_rules(tenant: CurrentTenantDep, session: SessionDep) -> schemas.DqRulesOut:
    return await _service(session).dq_rules()


@router.get("/variable-roles", response_model=schemas.VariableRolesOut)
async def variable_roles(tenant: CurrentTenantDep, session: SessionDep) -> schemas.VariableRolesOut:
    return await _service(session).variable_roles()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_app_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_app_routes.py apps/api/src/augura_api/modules/reference/router.py
git commit -m "feat(reference): catalog GET endpoints (TDD)"
```

---

## Task 7: Full suite + lint + type check

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest -q`
Expected: all tests pass (no regressions in other modules).

- [ ] **Step 2: Lint and type-check**

Run: `ruff check . && ruff format --check . && pyright src/augura_api/modules/reference`
Expected: no errors. Fix any reported issues (line length, import order) and re-run.

- [ ] **Step 3: Final commit (only if lint/format changed files)**

```bash
git add -A
git commit -m "chore(reference): lint + format catalog module"
```

---

## Self-review checklist (run before handing off)

- [ ] Every endpoint in the inventory table has a model (Task 1), DDL+RLS+migration (Task 2), seed rows (Task 3), schema (Task 4), repo+service (Task 5), and route (Task 6).
- [ ] `eligible_study_types` values (`retro`/`prosp`) match `ESTIMATOR_FILTER` in `config.js`: ipw & did are `retro`-only; lme/ols/mediation/tmle are both.
- [ ] Doubled single-quotes in seed prose (`user''s`, `''which users…''`, `''did it work…''`) are correct PostgreSQL escaping.
- [ ] `{partner}` tokens remain literal in `cesl_study_designs` seed (the frontend interpolates them).
- [ ] Method names are consistent across repo/service/Protocol (e.g. `list_variable_groups` everywhere, `variable_roles()` service method).
- [ ] The migration `down_revision` is `0003_literature_per_study_rls` and `revision` is `0004_reference_catalogs`.
