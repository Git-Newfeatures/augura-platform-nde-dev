-- ─────────────────────────────────────────────────────────────────────────
-- semantic schema (Part B / B1): make the governed semantic layer reproducible
-- under a dedicated `semantic` schema in dev/CI (it already exists in prod).
--
-- Strategy: the governed catalogs are MIRRORED from their public counterparts
-- via `CREATE TABLE … (LIKE public.<t> INCLUDING ALL)` so the structure stays in
-- lock-step with schema.sql without duplicating DDL. RLS + grants reproduce the
-- public read-only model (backend_read, FOR SELECT). The release table is the
-- legacy `semantic.releases` (prod) exposed as `semantic.semantic_releases` via a
-- view so the bare name resolves once search_path = 'semantic, public'.
--
-- Idempotent: CREATE … IF NOT EXISTS / CREATE OR REPLACE / DROP … IF EXISTS.
-- Applied by alembic 0014_semantic_schema (NOT by the 0001 baseline, which runs
-- before this schema exists). Data is mirrored into `semantic` by seed.sql.
--
-- Transition note (B4): once writes are on `semantic` (B2) and `public` is later
-- dropped, the LIKE-from-public source and the public→semantic seed mirror must
-- be reworked to stand alone. `semantic` is the canonical schema going forward.
-- ─────────────────────────────────────────────────────────────────────────

create schema if not exists semantic;

-- Governed catalogs, mirrored structurally from public (FK constraints are NOT
-- copied by LIKE — unnecessary for a governed read mirror; the data is already
-- referentially valid). Order is irrelevant without FKs.
do $$
declare t text;
begin
  foreach t in array array[
    'taxonomy_concepts','taxonomy_synonyms','taxonomy_standard_codes',
    'taxonomy_therapeutic_areas','taxonomy_relationships','taxonomy_dq_valid_values',
    'taxonomy_measurement_units','unit_conversions','causal_predicates','dq_predicates',
    'ontology_relations','ontology_relation_evidence','ontology_relation_qualifiers',
    'dq_constraints','table_archetypes','dimension_kinds','affix_archetypes',
    'affix_archetype_values','affix_archetype_aliases'
  ] loop
    execute format('create table if not exists semantic.%I (like public.%I including all);', t, t);
  end loop;
end $$;

-- Release history: legacy table is `semantic.releases` (prod). Mirror its
-- structure from public.semantic_releases for dev/CI, then expose it under the
-- canonical name via a view so the bare `semantic_releases` resolves in-schema.
create table if not exists semantic.releases (like public.semantic_releases including all);

create or replace view semantic.semantic_releases
  with (security_invoker = true)
  as select * from semantic.releases;

-- RLS: global read-only (FOR SELECT), gated on a backend session (app.tenant_id
-- set) — identical to the public governed catalogs (policies.sql).
do $$
declare t text;
begin
  foreach t in array array[
    'taxonomy_concepts','taxonomy_synonyms','taxonomy_standard_codes',
    'taxonomy_therapeutic_areas','taxonomy_relationships','taxonomy_dq_valid_values',
    'taxonomy_measurement_units','unit_conversions','causal_predicates','dq_predicates',
    'ontology_relations','ontology_relation_evidence','ontology_relation_qualifiers',
    'dq_constraints','table_archetypes','dimension_kinds','affix_archetypes',
    'affix_archetype_values','affix_archetype_aliases','releases'
  ] loop
    execute format('alter table semantic.%I enable row level security;', t);
    execute format('alter table semantic.%I force row level security;', t);
    execute format('drop policy if exists backend_read on semantic.%I;', t);
    execute format($f$create policy backend_read on semantic.%I for select
        using (nullif(current_setting('app.tenant_id', true), '') is not null);$f$, t);
  end loop;
end $$;

-- Grants for the application role (augura_app; augura_api inherits it). Guarded:
-- the role is created in policies.sql (baseline) before this runs, but stay
-- defensive for out-of-bundle application. `all tables` covers the view too.
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'augura_app') then
    execute 'grant usage on schema semantic to augura_app';
    execute 'grant select on all tables in schema semantic to augura_app';
    execute 'alter default privileges in schema semantic grant select on tables to augura_app';
  end if;
end $$;

-- ─────────────────────────────────────────────────────────────────────────
-- semantic.upsert_semantic_release (B2): the enrichment write path, targeting
-- `semantic`. Mirror of public.upsert_semantic_release with every table
-- schema-qualified to semantic.* and the release switch on semantic.releases.
-- SECURITY DEFINER: the app role (RLS FOR SELECT only) writes EXCLUSIVELY via
-- this function. Created here (after the tables exist) so check_function_bodies
-- can validate the semantic.* references at creation time.
-- ─────────────────────────────────────────────────────────────────────────
create or replace function semantic.upsert_semantic_release(
  p_manifest jsonb,
  p_payload jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, semantic
as $$
declare
  v_version text := p_manifest->>'semantic_release_version';
begin
  if coalesce(v_version, '') = '' then
    raise exception 'semantic_release_version required in the manifest';
  end if;

  insert into semantic.taxonomy_concepts
    select * from jsonb_populate_recordset(
      null::semantic.taxonomy_concepts,
      coalesce(p_payload->'taxonomy_concepts', '[]'::jsonb))
    on conflict (local_concept_id) do update set
      layer = excluded.layer,
      concept_name = excluded.concept_name,
      review_section = excluded.review_section,
      augura_domain = excluded.augura_domain,
      omop_domain_id = excluded.omop_domain_id,
      omop_target_table = excluded.omop_target_table,
      omop_target_concept_field = excluded.omop_target_concept_field,
      namespace = excluded.namespace,
      unit_source_value = excluded.unit_source_value,
      value_min = excluded.value_min,
      value_max = excluded.value_max,
      value_type = excluded.value_type,
      design_rationale = excluded.design_rationale,
      review_status = excluded.review_status,
      version = excluded.version,
      active = excluded.active,
      canonical_unit = excluded.canonical_unit,
      temporality = excluded.temporality,
      dq_column_role = excluded.dq_column_role,
      fhir_crosswalk = excluded.fhir_crosswalk,
      sdtm_crosswalk = excluded.sdtm_crosswalk,
      unit_coverage_status = excluded.unit_coverage_status,
      range_support_status = excluded.range_support_status;

  insert into semantic.taxonomy_synonyms
    select * from jsonb_populate_recordset(
      null::semantic.taxonomy_synonyms,
      coalesce(p_payload->'taxonomy_synonyms', '[]'::jsonb))
    on conflict (local_concept_id, synonym) do update set
      synonym_type = excluded.synonym_type,
      source = excluded.source,
      review_status = excluded.review_status;

  insert into semantic.taxonomy_standard_codes
    select * from jsonb_populate_recordset(
      null::semantic.taxonomy_standard_codes,
      coalesce(p_payload->'taxonomy_standard_codes', '[]'::jsonb))
    on conflict (local_concept_id, vocabulary_id, concept_code) do update set
      standard_concept_id = excluded.standard_concept_id,
      standard_concept_name = excluded.standard_concept_name,
      standard_concept_flag = excluded.standard_concept_flag,
      concept_class_id = excluded.concept_class_id;

  insert into semantic.ontology_relations
    select * from jsonb_populate_recordset(
      null::semantic.ontology_relations,
      coalesce(p_payload->'ontology_relations', '[]'::jsonb))
    on conflict (relation_id) do update set
      subject_concept_id = excluded.subject_concept_id,
      predicate = excluded.predicate,
      object_concept_id = excluded.object_concept_id,
      polarity = excluded.polarity,
      default_strength = excluded.default_strength,
      default_temporal_lag = excluded.default_temporal_lag,
      mechanism_summary = excluded.mechanism_summary,
      review_status = excluded.review_status,
      version = excluded.version,
      active = excluded.active;

  insert into semantic.ontology_relation_evidence
    select * from jsonb_populate_recordset(
      null::semantic.ontology_relation_evidence,
      coalesce(p_payload->'ontology_relation_evidence', '[]'::jsonb))
    on conflict (evidence_id) do update set
      relation_id = excluded.relation_id,
      source_type = excluded.source_type,
      citation_or_url = excluded.citation_or_url,
      evidence_summary = excluded.evidence_summary,
      population_notes = excluded.population_notes,
      evidence_strength = excluded.evidence_strength,
      review_status = excluded.review_status;

  insert into semantic.ontology_relation_qualifiers
    select * from jsonb_populate_recordset(
      null::semantic.ontology_relation_qualifiers,
      coalesce(p_payload->'ontology_relation_qualifiers', '[]'::jsonb))
    on conflict (qualifier_id) do update set
      relation_id = excluded.relation_id,
      qualifier_type = excluded.qualifier_type,
      qualifier_concept_id = excluded.qualifier_concept_id,
      qualifier_value = excluded.qualifier_value,
      qualifier_effect = excluded.qualifier_effect,
      is_hard_constraint = excluded.is_hard_constraint,
      notes = excluded.notes;

  insert into semantic.dimension_kinds
    select * from jsonb_populate_recordset(
      null::semantic.dimension_kinds,
      coalesce(p_payload->'dimension_kinds', '[]'::jsonb))
    on conflict (dimension_kind_id) do update set
      label = excluded.label,
      description = excluded.description,
      value_model = excluded.value_model,
      default_comparability = excluded.default_comparability,
      structural_role = excluded.structural_role,
      review_status = excluded.review_status,
      version = excluded.version,
      active = excluded.active;

  insert into semantic.affix_archetypes
    select * from jsonb_populate_recordset(
      null::semantic.affix_archetypes,
      coalesce(p_payload->'affix_archetypes', '[]'::jsonb))
    on conflict (affix_archetype_id) do update set
      archetype_name = excluded.archetype_name,
      dimension_kind_id = excluded.dimension_kind_id,
      position = excluded.position,
      separator_style = excluded.separator_style,
      value_model = excluded.value_model,
      comparability = excluded.comparability,
      anchor_concept_id = excluded.anchor_concept_id,
      operator = excluded.operator,
      extraction_rule = excluded.extraction_rule,
      requires_residual_maps = excluded.requires_residual_maps,
      requires_sibling_family = excluded.requires_sibling_family,
      evidence_weight = excluded.evidence_weight,
      confidence_threshold = excluded.confidence_threshold,
      review_status = excluded.review_status,
      version = excluded.version,
      active = excluded.active;

  insert into semantic.affix_archetype_values
    select * from jsonb_populate_recordset(
      null::semantic.affix_archetype_values,
      coalesce(p_payload->'affix_archetype_values', '[]'::jsonb))
    on conflict (affix_archetype_id, canonical_value) do update set
      label = excluded.label,
      review_status = excluded.review_status;

  insert into semantic.affix_archetype_aliases
    select * from jsonb_populate_recordset(
      null::semantic.affix_archetype_aliases,
      coalesce(p_payload->'affix_archetype_aliases', '[]'::jsonb))
    on conflict (affix_archetype_id, token) do update set
      canonical_value = excluded.canonical_value,
      source = excluded.source,
      review_status = excluded.review_status;

  -- Switch the current release (append-only, single is_current) on semantic.releases.
  update semantic.releases set is_current = false where is_current;
  insert into semantic.releases (
    semantic_release_version, taxonomy_version, causal_ontology_version,
    dq_ontology_version, omop_cdm_version, source, manifest, is_current
  ) values (
    v_version,
    coalesce(p_manifest->>'taxonomy_version', v_version),
    coalesce(p_manifest->>'causal_ontology_version', v_version),
    coalesce(p_manifest->>'dq_ontology_version', v_version),
    p_manifest->>'omop_cdm_version',
    coalesce(p_manifest->>'description', p_manifest->>'source'),
    p_manifest,
    true
  )
  on conflict (semantic_release_version) do update set
    taxonomy_version = excluded.taxonomy_version,
    causal_ontology_version = excluded.causal_ontology_version,
    dq_ontology_version = excluded.dq_ontology_version,
    omop_cdm_version = excluded.omop_cdm_version,
    source = excluded.source,
    manifest = excluded.manifest,
    is_current = true;

  return jsonb_build_object(
    'version', v_version,
    'concepts', jsonb_array_length(coalesce(p_payload->'taxonomy_concepts', '[]'::jsonb)),
    'relations', jsonb_array_length(coalesce(p_payload->'ontology_relations', '[]'::jsonb)),
    'affix_archetypes', jsonb_array_length(coalesce(p_payload->'affix_archetypes', '[]'::jsonb))
  );
end;
$$;

revoke all on function semantic.upsert_semantic_release(jsonb, jsonb) from public;
-- Strip the implicit Supabase anon/authenticated EXECUTE grant (survives the
-- `from public` revoke). Guarded: those roles are absent on bare Postgres (CI).
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke execute on function semantic.upsert_semantic_release(jsonb, jsonb) from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke execute on function semantic.upsert_semantic_release(jsonb, jsonb) from authenticated';
  end if;
end $$;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'augura_app') then
    execute 'grant execute on function semantic.upsert_semantic_release(jsonb, jsonb) to augura_app';
  end if;
end $$;
