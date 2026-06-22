-- Augura Platform — schéma de base de données (Supabase-ready)
-- Source de vérité du schéma. À appliquer dans un NOUVEAU projet Supabase
-- (SQL Editor) ou via la migration Alembic baseline qui exécute ce fichier.
-- Réf : docs/specs/2026-06-13-delivery-design.md §3.
--
-- Ordre d'application : schema.sql → functions.sql → seed.sql → policies.sql
-- (le seed passe AVANT l'activation RLS pour éviter toute friction d'insertion)
--
-- 19 tables, groupées par module. Toutes les tables tenant-scopées portent
-- une colonne org_id ; les policies RLS (policies.sql) s'y adossent.

begin;

create extension if not exists pgcrypto;   -- gen_random_uuid()
create extension if not exists vector;     -- pgvector (embeddings)

-- ─────────────────────────────────────────────────────────────────────────
-- Module : tenancy
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists orgs (
    id           uuid primary key default gen_random_uuid(),
    name         text not null,
    slug         text not null unique,
    cesl_profile jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);

-- user_id référence auth.users(id) côté Supabase. Pas de FK dure ici pour que
-- le bundle reste applicable même si le schéma auth n'est pas encore présent.
create table if not exists memberships (
    id         uuid primary key default gen_random_uuid(),
    org_id     uuid not null references orgs(id) on delete cascade,
    user_id    uuid not null,
    role       text not null default 'member' check (role in ('owner', 'member', 'viewer')),
    created_at timestamptz not null default now(),
    unique (org_id, user_id)
);
create index if not exists ix_memberships_user on memberships(user_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : studies
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists studies (
    id         uuid primary key default gen_random_uuid(),
    org_id     uuid not null references orgs(id) on delete cascade,
    name       text not null,
    slug       text not null,
    tagline    text,
    category   text,
    framework  text,
    n_subjects integer,
    lead       text,
    status     text not null default 'draft'
               check (status in ('draft', 'active', 'archived')),
    created_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (org_id, slug)
);
create index if not exists ix_studies_org on studies(org_id);

create table if not exists study_members (
    id       uuid primary key default gen_random_uuid(),
    study_id uuid not null references studies(id) on delete cascade,
    user_id  uuid not null,
    role     text not null default 'member' check (role in ('owner', 'member', 'viewer')),
    unique (study_id, user_id)
);

-- État de workflow versionné (remplace le sessionStorage augura_session_v3_*).
create table if not exists study_state (
    id         uuid primary key default gen_random_uuid(),
    study_id   uuid not null references studies(id) on delete cascade,
    version    integer not null default 1,
    state      jsonb not null default '{}'::jsonb,
    created_by uuid,
    created_at timestamptz not null default now(),
    unique (study_id, version)
);
create index if not exists ix_study_state_study on study_state(study_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : datasets (+ cohortes)
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists datasets (
    id           uuid primary key default gen_random_uuid(),
    org_id       uuid not null references orgs(id) on delete cascade,
    study_id     uuid references studies(id) on delete set null,
    name         text not null,
    storage_path text,
    row_count    integer,
    status       text not null default 'uploaded'
                 check (status in ('uploaded', 'profiled', 'mapped', 'error')),
    created_at   timestamptz not null default now()
);
create index if not exists ix_datasets_org on datasets(org_id);

create table if not exists dataset_columns (
    id                   uuid primary key default gen_random_uuid(),
    dataset_id           uuid not null references datasets(id) on delete cascade,
    sheet                text not null,
    name                 text not null,
    value_kind           text check (value_kind in ('numeric', 'text', 'binary', 'timestamp')),
    n_total              integer,
    n_non_null           integer,
    null_pct             numeric,
    n_distinct           integer,
    min                  numeric,
    max                  numeric,
    top_values           jsonb,
    proposed_role        text,
    proposed_group       text,
    proposed_canonical_id text,
    confidence           numeric,
    rationale            text,
    user_decision        text not null default 'pending'
                         check (user_decision in ('pending', 'confirmed', 'rejected')),
    final_role           text,
    final_canonical_id   text
);
create index if not exists ix_dataset_columns_dataset on dataset_columns(dataset_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : dq (A3a) — bundles de qualité des données (tenant-scopé)
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists dq_bundles (
    id                  uuid primary key default gen_random_uuid(),
    org_id              uuid not null references orgs(id) on delete cascade,
    dataset_id          uuid not null references datasets(id) on delete cascade,
    score_profile       text not null default 'exploratory',
    overall_score       numeric,
    status              text not null default 'draft' check (status in ('draft', 'sealed')),
    requires_resolution boolean not null default false,
    bundle              jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);
create index if not exists dq_bundles_dataset_idx on dq_bundles (dataset_id, created_at desc);

-- Cohorte démographique (= validation_members côté front).
create table if not exists cohort_members (
    id               uuid primary key default gen_random_uuid(),
    org_id           uuid not null references orgs(id) on delete cascade,
    dataset_id       uuid references datasets(id) on delete cascade,
    cohort_name      text not null,
    member_id        text not null,
    age              numeric,
    sex              text check (sex in ('F', 'M')),
    bmi              numeric,
    engagement_group text check (engagement_group in ('low', 'medium', 'high')),
    country          text
);
create index if not exists ix_cohort_members_lookup
    on cohort_members(org_id, cohort_name);

-- Cohorte biomarqueurs longitudinaux (= validation_biomarkers côté front).
create table if not exists cohort_biomarkers (
    id               uuid primary key default gen_random_uuid(),
    org_id           uuid not null references orgs(id) on delete cascade,
    dataset_id       uuid references datasets(id) on delete cascade,
    cohort_name      text not null,
    member_id        text not null,
    timepoint_months integer not null,
    hba1c_pct        numeric,
    ldl_mgdl         numeric,
    hs_crp_mgl       numeric,
    adherence_pct    numeric
);
create index if not exists ix_cohort_biomarkers_lookup
    on cohort_biomarkers(org_id, cohort_name, member_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : corpus (org_id NULLABLE ⇒ corpus global partagé)
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists documents (
    id             uuid primary key default gen_random_uuid(),
    org_id         uuid references orgs(id) on delete cascade,
    source_id      text not null,
    evidence_type  text,
    jurisdiction   text,
    lifecycle      text,
    title          text not null,
    summary        text,
    url            text,
    published_at   date,
    ingested_at    timestamptz not null default now(),
    priority_score numeric,
    is_new         boolean not null default false
);
create index if not exists ix_documents_facets
    on documents(jurisdiction, evidence_type);
create index if not exists ix_documents_feed
    on documents(ingested_at desc);

create table if not exists chunks (
    id          uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents(id) on delete cascade,
    org_id      uuid references orgs(id) on delete cascade,
    content     text not null,
    embedding   vector(1536),
    token_count integer
);
-- Index HNSW pour la recherche par similarité cosinus (pgvector).
create index if not exists ix_chunks_embedding_hnsw
    on chunks using hnsw (embedding vector_cosine_ops);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : agents (observabilité + cache)
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists agent_runs (
    id            uuid primary key default gen_random_uuid(),
    org_id        uuid not null references orgs(id) on delete cascade,
    study_id      uuid references studies(id) on delete set null,
    agent_type    text not null,
    model         text,
    status        text not null default 'running'
                  check (status in ('running', 'succeeded', 'failed')),
    duration_ms   integer,
    input_tokens  integer,
    output_tokens integer,
    cost_usd      numeric,
    created_at    timestamptz not null default now()
);
create index if not exists ix_agent_runs_org on agent_runs(org_id, created_at desc);

-- Cache des réponses d'agents déterministes (fix U2).
create table if not exists agent_cache (
    id         uuid primary key default gen_random_uuid(),
    agent_type text not null,
    input_hash text not null,
    response   jsonb not null,
    created_at timestamptz not null default now(),
    unique (agent_type, input_hash)
);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : simulation
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists simulation_runs (
    id         uuid primary key default gen_random_uuid(),
    org_id     uuid not null references orgs(id) on delete cascade,
    study_id   uuid references studies(id) on delete set null,
    params     jsonb not null default '{}'::jsonb,
    job_id     uuid,
    status     text not null default 'queued'
               check (status in ('queued', 'running', 'succeeded', 'failed')),
    results    jsonb,
    created_at timestamptz not null default now()
);
create index if not exists ix_simulation_runs_org on simulation_runs(org_id);

-- Read-model précalculé pour le mode VALIDATED du front (3 scénarios × 4 estimateurs).
create table if not exists simulation_results (
    id          uuid primary key default gen_random_uuid(),
    org_id      uuid not null references orgs(id) on delete cascade,
    cohort_name text not null,
    scenario    text not null check (scenario in ('baseline', 'conservative', 'high_risk')),
    estimator   text not null check (estimator in ('lme', 'ols', 'ipw', 'mediation', 'tmle', 'did')),
    effect_size numeric,
    ci_lower    numeric,
    ci_upper    numeric,
    power       numeric,
    p_value     numeric,
    -- Métriques bootstrap (scatter Bias-vs-MSE) + paramètres de cohorte par scénario.
    bias        numeric,
    variance    numeric,
    mse         numeric,
    n_total     integer,
    n_treatment integer,
    dropout     numeric,
    unique (org_id, cohort_name, scenario, estimator)
);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : jobs
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists jobs (
    id              uuid primary key default gen_random_uuid(),
    org_id          uuid not null references orgs(id) on delete cascade,
    type            text not null,
    status          text not null default 'queued'
                    check (status in ('queued', 'running', 'succeeded', 'failed')),
    progress        numeric not null default 0,
    payload         jsonb not null default '{}'::jsonb,
    result_ref      text,
    result_json     jsonb,
    error           text,
    idempotency_key text,
    modal_call_id   text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (org_id, idempotency_key)
);
create index if not exists ix_jobs_org_status on jobs(org_id, status);

-- FK simulation_runs.job_id -> jobs(id) : posée ici car jobs est créé APRÈS
-- simulation_runs. Idempotente (re-run du bundle sans erreur).
do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'simulation_runs_job_id_fkey') then
        alter table simulation_runs
            add constraint simulation_runs_job_id_fkey
            foreign key (job_id) references jobs(id) on delete set null;
    end if;
end $$;
create index if not exists ix_simulation_runs_job on simulation_runs(job_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : documents générés
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists generated_documents (
    id           uuid primary key default gen_random_uuid(),
    org_id       uuid not null references orgs(id) on delete cascade,
    study_id     uuid references studies(id) on delete set null,
    type         text not null check (type in ('protocol', 'report')),
    storage_path text,
    status       text not null default 'pending'
                 check (status in ('pending', 'generating', 'ready', 'failed')),
    created_at   timestamptz not null default now()
);
create index if not exists ix_generated_documents_org on generated_documents(org_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : analytics / observabilité
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists usage_events (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid,
    org_id     uuid references orgs(id) on delete set null,
    event_type text not null,
    route      text,
    metadata   jsonb,
    created_at timestamptz not null default now()
);
create index if not exists ix_usage_events_created on usage_events(created_at desc);

create table if not exists outbox_events (
    id             uuid primary key default gen_random_uuid(),
    aggregate_type text not null,
    aggregate_id   uuid,
    event_type     text not null,
    payload        jsonb not null default '{}'::jsonb,
    created_at     timestamptz not null default now(),
    processed_at   timestamptz
);
create index if not exists ix_outbox_unprocessed
    on outbox_events(created_at) where processed_at is null;

-- Artefacts versionnés & hashés — colonne vertébrale reproductibilité (spec §2).
-- Tout objet reproductible (snapshot dataset, rapport QC, mapping, DAG, SAP, run)
-- y est stocké : contenu canonique + SHA-256 + provenance + lock de pré-spécification.
create table if not exists artifacts (
    id          uuid primary key default gen_random_uuid(),
    org_id      uuid not null references orgs(id) on delete cascade,
    study_id    uuid references studies(id) on delete set null,
    kind        text not null
                check (kind in ('dataset_snapshot', 'qc_report', 'mapping', 'dag',
                                'sap', 'run_manifest')),
    version     integer not null default 0,        -- v0 = machine-proposé, v1 = humain-approuvé…
    sha256      text not null,                     -- hash du contenu canonique
    content     jsonb,                             -- corps inline (edge list, SAP, manifest…)
    storage_ref text,                              -- ou pointeur Storage si volumineux
    provenance  jsonb not null default '{}'::jsonb, -- {source, prompt_hash, model_id, parent_version, diff…}
    locked      boolean not null default false,    -- artefact figé (DAG/SAP approuvé)
    created_by  uuid,
    created_at  timestamptz not null default now(),
    unique (study_id, kind, version)
);
create index if not exists ix_artifacts_org on artifacts(org_id);
create index if not exists ix_artifacts_study_kind on artifacts(study_id, kind);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : reference — catalogues CESL globaux (non tenant-scopés, lecture seule)
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists cesl_sources (
    code        text primary key,
    label       text not null,
    doc_type    text,
    description text,
    base_url    text,
    result_unit text,
    sort_order  int     not null default 0,
    active      boolean not null default true
);

create table if not exists cesl_study_designs (
    code       text primary key,
    label      text not null,
    group_name text,
    sort_order int     not null default 0,
    active     boolean not null default true
);

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

-- ─────────────────────────────────────────────────────────────────────────
-- Module : semantic (A1) — taxonomie DQ globale (lecture seule). DDL porté de
-- l'MVP semantic schema → public. Versioning/ontologie causale = subsystem B.
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists taxonomy_concepts (
  local_concept_id text primary key,
  layer smallint not null check (layer between 0 and 2),
  concept_name text not null,
  review_section text,
  augura_domain text not null,
  omop_domain_id text,
  omop_target_table text,
  omop_target_concept_field text,
  namespace text,
  unit_source_value text,
  value_min numeric,
  value_max numeric,
  value_type text,
  design_rationale text,
  review_status text not null,
  version text not null,
  active boolean not null,
  canonical_unit text,
  temporality text,
  dq_column_role text,
  fhir_crosswalk text,
  sdtm_crosswalk text,
  unit_coverage_status text,
  range_support_status text,
  check (value_min is null or value_max is null or value_min <= value_max)
);

create table if not exists taxonomy_synonyms (
  local_concept_id text not null references taxonomy_concepts(local_concept_id),
  synonym text not null,
  synonym_type text not null,
  source text not null,
  review_status text not null,
  primary key (local_concept_id, synonym)
);

create table if not exists taxonomy_dq_valid_values (
  local_concept_id text not null references taxonomy_concepts(local_concept_id),
  value text not null,
  label text not null,
  coding_system text not null,
  review_status text not null,
  primary key (local_concept_id, value)
);

create table if not exists taxonomy_measurement_units (
  unit_id text primary key,
  concept_id text not null references taxonomy_concepts(local_concept_id),
  ucum_code text not null,
  display_label text not null,
  source_aliases text not null,
  status text not null,
  quantity_kind text not null,
  is_preferred boolean not null,
  review_status text not null,
  version text not null
);

create table if not exists unit_conversions (
  conversion_id text primary key,
  from_ucum text not null,
  to_ucum text not null,
  quantity_kind text not null,
  applicable_concept_id text references taxonomy_concepts(local_concept_id),
  conversion_type text not null,
  equation_id text not null,
  scale_factor numeric,
  "offset" numeric,
  precision integer not null,
  bidirectional boolean not null,
  provenance text not null,
  review_status text not null,
  version text not null
);

create table if not exists table_archetypes (
  archetype_id text primary key,
  archetype_name text not null,
  key_selectors text not null,
  semantic_score numeric not null check (semantic_score between 0 and 1),
  is_surrogate boolean not null,
  description_template text not null,
  review_status text not null,
  version text not null,
  active boolean not null
);

create table if not exists dq_constraints (
  constraint_id text primary key,
  target_scope text not null,
  subject_concept_or_role text not null,
  operator text not null,
  object_concept_or_role text,
  parameters text,
  applies_when text not null,
  severity text not null,
  implementation_id text not null,
  evidence_source text not null,
  status text not null,
  version text not null
);

create index if not exists taxonomy_synonyms_synonym_idx on taxonomy_synonyms (lower(synonym));
create index if not exists taxonomy_measurement_units_concept_idx on taxonomy_measurement_units (concept_id);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : semantic (B1) — ontologie/causal globale (lecture seule). DDL porté
-- de l'MVP semantic schema → public, FKs vers taxonomy_concepts conservées.
-- Substrat consommé par B2 (dag-llm) et B4 (enrich). Ordre : parents FK d'abord
-- (codes/areas/relationships → concepts ; causal_predicates → ontology_relations
-- → evidence/qualifiers).
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists taxonomy_standard_codes (
  local_concept_id      text not null references taxonomy_concepts(local_concept_id),
  vocabulary_id         text not null,
  concept_code          text not null,
  standard_concept_id   text,
  standard_concept_name text,
  standard_concept_flag text,
  concept_class_id      text,
  primary key (local_concept_id, vocabulary_id, concept_code)
);

create table if not exists taxonomy_therapeutic_areas (
  local_concept_id text not null references taxonomy_concepts(local_concept_id),
  therapeutic_area text not null,
  primary key (local_concept_id, therapeutic_area)
);

create table if not exists taxonomy_relationships (
  relationship_id   text primary key,
  from_concept_id   text not null references taxonomy_concepts(local_concept_id),
  to_concept_id     text not null references taxonomy_concepts(local_concept_id),
  relationship_type text not null,
  provenance        text not null,
  notes             text
);

create table if not exists causal_predicates (
  predicate_id   text primary key,
  label          text not null,
  description    text not null,
  direction_type text not null,
  review_status  text not null,
  version        text not null
);

create table if not exists dq_predicates (
  predicate_id   text primary key,
  label          text not null,
  description    text not null,
  direction_type text not null,
  review_status  text not null,
  version        text not null
);

create table if not exists ontology_relations (
  relation_id          text primary key,
  subject_concept_id   text not null references taxonomy_concepts(local_concept_id),
  predicate            text not null references causal_predicates(predicate_id),
  object_concept_id    text not null references taxonomy_concepts(local_concept_id),
  polarity             text not null,
  default_strength     text not null,
  default_temporal_lag text not null,
  mechanism_summary    text not null,
  review_status        text not null,
  version              text not null,
  active               boolean not null
);

create table if not exists ontology_relation_evidence (
  evidence_id       text primary key,
  relation_id       text not null references ontology_relations(relation_id),
  source_type       text not null,
  citation_or_url   text not null,
  evidence_summary  text not null,
  population_notes  text not null,
  evidence_strength text not null,
  review_status     text not null
);

create table if not exists ontology_relation_qualifiers (
  qualifier_id         text primary key,
  relation_id          text not null references ontology_relations(relation_id),
  qualifier_type       text not null,
  qualifier_concept_id text references taxonomy_concepts(local_concept_id),
  qualifier_value      text not null,
  qualifier_effect     text not null,
  is_hard_constraint   boolean not null,
  notes                text not null
);

create index if not exists ontology_relations_subject_idx on ontology_relations (subject_concept_id);
create index if not exists ontology_relations_object_idx on ontology_relations (object_concept_id);
create index if not exists ontology_relation_evidence_relation_idx
  on ontology_relation_evidence (relation_id);

-- Historique de version de la couche sémantique gouvernée (sert GET /semantic/release).
-- Append-only, une seule ligne is_current ; la ligne courante est seedée (cf. 0005).
create table if not exists semantic_releases (
  semantic_release_version text primary key,
  taxonomy_version         text not null,
  causal_ontology_version  text not null,
  dq_ontology_version      text not null,
  omop_cdm_version         text,
  source                   text,
  manifest                 jsonb not null,
  imported_at              timestamptz not null default now(),
  is_current               boolean not null default false
);

-- ─────────────────────────────────────────────────────────────────────────
-- Module : corpus — recherche live (retrieve-and-freeze)
-- Miroir de la migration alembic 0002_literature_live_search. Verbe distinct de
-- l'ingestion : récupère + gèle un jeu de preuves (content_hash), sans toucher au
-- corpus. Refs externes (org_id, study_id, created_by) = UUID nus (les orgs/users
-- vivent côté auth Supabase) ; seule events.session_id est une FK intra-tables.
-- ─────────────────────────────────────────────────────────────────────────

create table if not exists literature_snapshots (
    id           uuid primary key default gen_random_uuid(),
    org_id       uuid not null,
    study_id     uuid,           -- NULL ⇒ snapshot standalone (créateur seul, cf. RLS)
    created_by   uuid not null,
    -- payload = l'artefact canonique EXACT qui a été haché (autorité du hash) :
    -- {query, sources, model_version, prompt_version, study_id, created_by,
    --  created_at, results:[…]}. Les colonnes ci-dessus le dénormalisent pour la
    -- RLS / l'indexation / le tri ; le hash ne fait foi que sur payload.
    payload      jsonb not null,
    content_hash text not null,
    created_at   timestamptz not null default now()
);
create index if not exists ix_literature_snapshots_org_id on literature_snapshots (org_id);
create index if not exists ix_literature_snapshots_study_id on literature_snapshots (study_id);
create index if not exists ix_literature_snapshots_created_by on literature_snapshots (created_by);

create table if not exists search_sessions (
    id         uuid primary key default gen_random_uuid(),
    org_id     uuid not null,
    study_id   uuid,
    query      text,
    status     text not null default 'active',
    created_by uuid not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists ix_search_sessions_org_id_status on search_sessions (org_id, status);
create index if not exists ix_search_sessions_created_by on search_sessions (created_by);

create table if not exists literature_events (
    id         uuid primary key default gen_random_uuid(),
    session_id uuid not null references search_sessions (id) on delete cascade,
    org_id     uuid not null,
    event_type text not null,
    payload    jsonb not null default '{}'::jsonb,
    created_by uuid not null,
    created_at timestamptz not null default now()
);
create index if not exists ix_literature_events_session_id on literature_events (session_id);

create table if not exists literature_queries (
    id           uuid primary key default gen_random_uuid(),
    org_id       uuid not null,
    source       text not null,
    query_string text not null,
    result       jsonb not null,
    retrieved_at timestamptz not null default now(),
    constraint uq_literature_queries_org_source_query unique (org_id, source, query_string)
);

commit;
