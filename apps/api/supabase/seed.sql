-- Augura Platform — seed
-- À appliquer APRÈS functions.sql et AVANT policies.sql (avant l'activation RLS).
--
-- Intentionnellement vide de données de démonstration. La base démarre sans
-- contenu ; les vraies données (cohortes, corpus, résultats de bootstrap) sont
-- importées via les scripts dédiés (P3/P5) ou créées par l'application en mode réel.
-- Le front rend des états vides tant qu'aucune donnée réelle n'est présente.

-- ─────────────────────────────────────────────────────────────────────────
-- Catalogues de référence CESL (config, pas des données de démo).
-- Reconstruits depuis les constantes du MVP (4 sources de l'agent E1 + designs).
-- À remplacer par l'export Supabase autoritaire si l'accès au projet MVP est fourni.
-- ─────────────────────────────────────────────────────────────────────────

insert into cesl_sources (code, label, doc_type, description, base_url, result_unit, sort_order, active) values
  ('pubmed',         'PubMed',            'study',         'Peer-reviewed biomedical literature (NCBI PubMed).',                'https://pubmed.ncbi.nlm.nih.gov/',                                            'studies',   10, true),
  ('clinicaltrials', 'ClinicalTrials.gov','trial',         'Registered interventional and observational clinical trials.',      'https://clinicaltrials.gov/',                                                 'trials',    20, true),
  ('maude',          'MAUDE',             'adverse_event', 'FDA Manufacturer and User Facility Device Experience adverse events.','https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfMAUDE/search.cfm',       'events',    30, true),
  ('guidance',       'FDA Guidance',      'guidance',      'FDA regulatory guidance documents.',                                'https://www.fda.gov/regulatory-information/search-fda-guidance-documents',     'documents', 40, true)
on conflict (code) do nothing;

insert into cesl_study_designs (code, label, group_name, sort_order, active) values
  ('retro_cohort',     'Retrospective cohort',     'observational', 10, true),
  ('pre_post',         'Pre/post',                 'observational', 20, true),
  ('external_matched', 'External matched control', 'observational', 30, true),
  ('mediation',        'Causal mediation',         'mechanistic',   40, true),
  ('prospective',      'Prospective cohort',       'prospective',   50, true)
on conflict (code) do nothing;
