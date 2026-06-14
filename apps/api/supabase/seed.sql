-- Augura Platform — seed (« mockup » de la base)
-- À appliquer APRÈS functions.sql et AVANT policies.sql (avant l'activation RLS).
-- Données représentatives pour faire vivre le front sans mocks. La cohorte
-- complète (N=824) et les résultats réels du bootstrap sont importés en P3/P5
-- via les scripts dédiés ; ici un échantillon cohérent.

begin;

-- ── Tenant Lucis (id historique conservé pour compat) ────────────────────
insert into orgs (id, name, slug, cesl_profile) values (
    '33cb3ba0-00fe-420b-a8c7-70736aaacc44',
    'Lucis',
    'lucis',
    '{
        "clinical_domain": ["cardiometabolic", "preventive_health", "patient_monitoring"],
        "evidence_type": ["rct", "cohort", "meta_analysis", "guidance", "rwe_study"]
    }'::jsonb
) on conflict (id) do nothing;

-- ── Étude démo Lucis ─────────────────────────────────────────────────────
insert into studies (id, org_id, name, slug, tagline, category, framework, n_subjects, lead, status)
values (
    'a1b2c3d4-0000-4000-8000-000000000001',
    '33cb3ba0-00fe-420b-a8c7-70736aaacc44',
    'Lucis — engagement & HbA1c',
    'lucis',
    'Effet de l''engagement sur le contrôle glycémique à 12 mois',
    'Cardiometabolic RPM',
    'FDA RWE · EU MDR',
    824,
    'Clinical Evidence',
    'active'
) on conflict (org_id, slug) do nothing;

insert into study_state (study_id, version, state) values (
    'a1b2c3d4-0000-4000-8000-000000000001',
    1,
    '{
        "selectedOutcome": "hba1c_12m",
        "cqExposure": "High engagement (>70) vs Low (<30)",
        "cqPopulation": "Adults with prediabetes",
        "studyType": "retro",
        "completedTab": "design"
    }'::jsonb
) on conflict (study_id, version) do nothing;

-- ── Échantillon cohorte (validation_v1) ──────────────────────────────────
insert into cohort_members (org_id, cohort_name, member_id, age, sex, bmi, engagement_group, country) values
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_001', 54, 'F', 28.4, 'high',   'FR'),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_002', 61, 'M', 31.0, 'low',    'UK'),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_003', 47, 'F', 26.1, 'medium', 'FR'),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_004', 58, 'M', 29.7, 'high',   'DE'),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_005', 50, 'F', 24.8, 'low',    'UK'),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_006', 63, 'M', 33.2, 'medium', 'DE');

insert into cohort_biomarkers (org_id, cohort_name, member_id, timepoint_months, hba1c_pct, ldl_mgdl, hs_crp_mgl, adherence_pct) values
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_001',  0, 6.4, 142, 2.1, 92),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_001', 12, 5.9, 128, 1.6, 90),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_002',  0, 6.8, 160, 3.0, 41),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_002', 12, 6.7, 155, 2.8, 38),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_003',  0, 6.1, 130, 1.8, 70),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_003', 12, 5.8, 122, 1.5, 73),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_004',  0, 6.6, 150, 2.6, 88),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_004', 12, 6.0, 133, 1.9, 85),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_005',  0, 6.3, 138, 2.2, 45),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_005', 12, 6.2, 136, 2.0, 44),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_006',  0, 6.9, 165, 3.4, 66),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'm_006', 12, 6.5, 150, 2.9, 69);

-- ── Corpus global (org_id NULL) — échantillon multi-sources ──────────────
insert into documents (org_id, source_id, evidence_type, jurisdiction, lifecycle, title, summary, url, published_at, priority_score, is_new) values
    (null, 'pubmed',         'rct',           'fda',    'pre_market',  'Digital engagement and glycemic control: a randomized trial', 'RCT showing engagement-linked HbA1c reduction at 12 months.', 'https://pubmed.ncbi.nlm.nih.gov/000001', '2026-04-02', 0.92, true),
    (null, 'pubmed',         'meta_analysis', 'global', 'policy',      'Adherence interventions in prediabetes: meta-analysis',       'Pooled effect of adherence interventions on HbA1c.',          'https://pubmed.ncbi.nlm.nih.gov/000002', '2026-02-18', 0.81, false),
    (null, 'clinicaltrials', 'trial_record',  'fda',    'pre_market',  'RPM cardiometabolic cohort — NCT0000000',                     'Prospective RPM cohort, primary endpoint HbA1c change.',       'https://clinicaltrials.gov/study/NCT0000000', '2026-05-20', 0.74, true),
    (null, 'guidance',       'guidance',      'fda',    'policy',      'FDA RWE guidance for digital health endpoints',               'Framework for real-world evidence in device submissions.',     'https://www.fda.gov/media/000003', '2025-11-10', 0.88, false),
    (null, 'guidance',       'guidance',      'ema',    'policy',      'EMA reflection paper on patient monitoring data',             'Considerations for longitudinal monitoring evidence.',         'https://www.ema.europa.eu/000004', '2025-09-30', 0.69, false),
    (null, 'maude',          'adverse_event', 'fda',    'post_market', 'MAUDE signal — continuous glucose monitor',                   'Adverse event cluster in CGM post-market surveillance.',       'https://www.accessdata.fda.gov/000005', '2026-03-12', 0.55, false),
    (null, 'pubmed',         'cohort',        'global', 'post_market', 'Real-world LDL outcomes under remote monitoring',             'Observational cohort, secondary LDL outcomes.',                'https://pubmed.ncbi.nlm.nih.gov/000006', '2026-01-08', 0.63, false),
    (null, 'clinicaltrials', 'trial_record',  'ema',    'pre_market',  'EU prevention trial — engagement stratification',             'Stratified analysis by engagement tertile.',                   'https://clinicaltrials.gov/study/NCT0000007', '2026-04-28', 0.71, true);

-- ── Résultats de simulation précalculés (mode VALIDATED) ─────────────────
-- 3 scénarios × 4 estimateurs. Valeurs représentatives (réelles = run_bootstrap.py, P5).
insert into simulation_results (org_id, cohort_name, scenario, estimator, effect_size, ci_lower, ci_upper, power, p_value) values
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'baseline',     'lme',  -0.42, -0.55, -0.29, 1.00, 0.0001),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'baseline',     'ols',  -0.40, -0.54, -0.26, 1.00, 0.0002),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'baseline',     'ipw',  -0.39, -0.56, -0.22, 0.98, 0.0006),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'baseline',     'tmle', -0.41, -0.53, -0.29, 0.99, 0.0003),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'conservative', 'lme',  -0.28, -0.41, -0.15, 0.87, 0.0030),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'conservative', 'ols',  -0.26, -0.40, -0.12, 0.83, 0.0050),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'conservative', 'ipw',  -0.25, -0.43, -0.07, 0.76, 0.0120),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'conservative', 'tmle', -0.27, -0.40, -0.14, 0.85, 0.0042),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'high_risk',    'lme',  -0.15, -0.30,  0.00, 0.52, 0.0500),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'high_risk',    'ols',  -0.13, -0.29,  0.03, 0.46, 0.0900),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'high_risk',    'ipw',  -0.12, -0.31,  0.07, 0.38, 0.1400),
    ('33cb3ba0-00fe-420b-a8c7-70736aaacc44', 'validation_v1', 'high_risk',    'tmle', -0.14, -0.30,  0.02, 0.49, 0.0700);

commit;
