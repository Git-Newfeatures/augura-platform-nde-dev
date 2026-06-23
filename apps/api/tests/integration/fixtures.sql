-- Integration test fixtures — NOT shipped seed data.
--
-- The integration suite and the CI db-bundle smoke steps expect a fixed tenant
-- (org "Lucis" 33cb3ba0…, owner 11111111…) plus a small, deterministic demo
-- dataset. seed.sql is intentionally free of demo data, so this file provides
-- exactly what the tests assert. Applied AFTER seed.sql (and after policies.sql)
-- by a privileged role (CI: postgres superuser → RLS bypassed) so it can insert
-- the global corpus (org_id NULL) and the org itself.
--
-- Apply locally against a throwaway DB:
--   psql -v ON_ERROR_STOP=1 -f tests/integration/fixtures.sql
-- Idempotent: re-running is a no-op (fixed ids + ON CONFLICT).

-- ── Tenant + membership ──────────────────────────────────────────────────────
insert into orgs (id, name, slug) values
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'Lucis', 'lucis')
on conflict (id) do nothing;

insert into memberships (org_id, user_id, role) values
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', '11111111-1111-4111-8111-111111111111', 'owner')
on conflict (org_id, user_id) do nothing;

-- ── Global corpus: 8 documents (org_id NULL → visible to every tenant) ────────
-- Asserts: total = 8, source 'pubmed' = 3, coverage cell (fda, rct) = 1 and
-- (fda, preprint) = 0. Jurisdictions/types are drawn from the coverage grid
-- (COVERAGE_JURISDICTIONS × COVERAGE_EVIDENCE_TYPES).
insert into documents (id, org_id, source_id, jurisdiction, evidence_type, title) values
    ('d0c00000-0000-4000-8000-000000000001', null, 'pubmed', 'fda',    'rct',       'FDA RCT on cardiometabolic outcomes'),
    ('d0c00000-0000-4000-8000-000000000002', null, 'pubmed', 'ema',    'rct',       'EMA randomized trial summary'),
    ('d0c00000-0000-4000-8000-000000000003', null, 'pubmed', 'global', 'guidance',  'WHO global guidance note'),
    ('d0c00000-0000-4000-8000-000000000004', null, 'ct_gov', 'fda',    'guidance',  'FDA guidance on trial design'),
    ('d0c00000-0000-4000-8000-000000000005', null, 'ct_gov', 'ema',    'rwe_study', 'EMA real-world evidence study'),
    ('d0c00000-0000-4000-8000-000000000006', null, 'fda',    'imdrf',  'guidance',  'IMDRF harmonization guidance'),
    ('d0c00000-0000-4000-8000-000000000007', null, 'who',    'global', 'rwe_study', 'Global registry RWE report'),
    ('d0c00000-0000-4000-8000-000000000008', null, 'ema',    'ema',    'guidance',  'EMA scientific advice')
on conflict (id) do nothing;

-- ── VALIDATED read-model: 12 simulation_results (3 scenarios × 4 estimators) ──
insert into simulation_results
    (org_id, cohort_name, scenario, estimator, effect_size, ci_lower, ci_upper, power, p_value,
     bias, variance, mse, n_total, n_treatment, dropout)
select
    '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', s.scenario, e.estimator,
    0.30, 0.10, 0.50, 0.82, 0.03, 0.01, 0.02, 0.03, 824, 412, 0.08
from (values ('baseline'), ('conservative'), ('high_risk')) as s(scenario)
cross join (values ('lme'), ('ols'), ('ipw'), ('tmle')) as e(estimator)
on conflict (org_id, cohort_name, scenario, estimator) do nothing;

-- ── validation_v1 cohort: 6 members + 12 biomarker rows (2 timepoints each) ───
insert into cohort_members (id, org_id, cohort_name, member_id, age, sex, engagement_group) values
    ('c0e00000-0000-4000-8000-000000000001', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm1', 54, 'F', 'high'),
    ('c0e00000-0000-4000-8000-000000000002', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm2', 61, 'M', 'medium'),
    ('c0e00000-0000-4000-8000-000000000003', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm3', 47, 'F', 'low'),
    ('c0e00000-0000-4000-8000-000000000004', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm4', 58, 'M', 'high'),
    ('c0e00000-0000-4000-8000-000000000005', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm5', 52, 'F', 'medium'),
    ('c0e00000-0000-4000-8000-000000000006', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm6', 65, 'M', 'low')
on conflict (id) do nothing;

insert into cohort_biomarkers
    (id, org_id, cohort_name, member_id, timepoint_months, hba1c_pct) values
    ('c0b00000-0000-4000-8000-000000000001', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm1', 0,  8.1),
    ('c0b00000-0000-4000-8000-000000000002', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm1', 12, 7.2),
    ('c0b00000-0000-4000-8000-000000000003', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm2', 0,  7.8),
    ('c0b00000-0000-4000-8000-000000000004', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm2', 12, 7.0),
    ('c0b00000-0000-4000-8000-000000000005', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm3', 0,  9.0),
    ('c0b00000-0000-4000-8000-000000000006', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm3', 12, 8.3),
    ('c0b00000-0000-4000-8000-000000000007', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm4', 0,  7.5),
    ('c0b00000-0000-4000-8000-000000000008', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm4', 12, 6.9),
    ('c0b00000-0000-4000-8000-000000000009', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm5', 0,  8.4),
    ('c0b00000-0000-4000-8000-000000000010', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm5', 12, 7.6),
    ('c0b00000-0000-4000-8000-000000000011', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm6', 0,  8.9),
    ('c0b00000-0000-4000-8000-000000000012', '33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm6', 12, 8.0)
on conflict (id) do nothing;
