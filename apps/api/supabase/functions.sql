-- Augura Platform — fonctions & vues
-- À appliquer APRÈS schema.sql.

begin;

-- Recherche sémantique sur le corpus (port du RPC match_chunks du front).
-- Scope tenant : chunks du corpus global (org_id NULL) + ceux du tenant courant
-- (app.tenant_id, posé par le backend via SET LOCAL). Filtre optionnel par
-- source_id / evidence_type passé en jsonb.
create or replace function match_chunks(
    query_embedding vector(1536),
    match_count int default 20,
    filter jsonb default '{}'::jsonb
)
returns table (
    id          uuid,
    document_id uuid,
    content     text,
    similarity  float,
    source_id   text,
    title       text
)
language sql
stable
set search_path = public, pg_temp
as $$
    select
        c.id,
        c.document_id,
        c.content,
        1 - (c.embedding <=> query_embedding) as similarity,
        d.source_id,
        d.title
    from chunks c
    join documents d on d.id = c.document_id
    where c.embedding is not null
      and (
        c.org_id is null
        or c.org_id = nullif(current_setting('app.tenant_id', true), '')::uuid
      )
      and (filter ->> 'source_id' is null or d.source_id = filter ->> 'source_id')
      and (filter ->> 'evidence_type' is null or d.evidence_type = filter ->> 'evidence_type')
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- Matrice de couverture (jurisdiction × evidence_type → doc_count).
-- Les cellules à zéro sont complétées côté service (corpus). gap_score/severity
-- sont dérivés dans le service à partir de doc_count.
create or replace view v_coverage_map with (security_invoker = on) as
    select
        coalesce(jurisdiction, 'unknown') as jurisdiction,
        coalesce(evidence_type, 'other')  as evidence_type,
        count(*)                          as doc_count
    from documents
    group by 1, 2;

-- ─────────────────────────────────────────────────────────────────────────
-- upsert_semantic_release : applique un batch d'enrichissement (B4) à la couche
-- sémantique gouvernée et bascule la release courante. SECURITY DEFINER : le rôle
-- applicatif (RLS FOR SELECT seulement) écrit EXCLUSIVEMENT via cette fonction.
-- Idempotent (CREATE OR REPLACE + upserts par clé).
-- ─────────────────────────────────────────────────────────────────────────
-- NB : le propriétaire de cette fonction doit être un rôle BYPASSRLS/privilégié
-- (service_role Supabase) pour que SECURITY DEFINER puisse écrire les catalogues
-- gouvernés malgré leur RLS FORCE … FOR SELECT.
create or replace function public.upsert_semantic_release(
  p_manifest jsonb,
  p_payload jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_version text := p_manifest->>'semantic_release_version';
begin
  if coalesce(v_version, '') = '' then
    raise exception 'semantic_release_version requis dans le manifest';
  end if;

  -- Concepts d'abord (cible FK des relations / synonyms / codes).
  insert into public.taxonomy_concepts
    select * from jsonb_populate_recordset(
      null::public.taxonomy_concepts,
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

  insert into public.taxonomy_synonyms
    select * from jsonb_populate_recordset(
      null::public.taxonomy_synonyms,
      coalesce(p_payload->'taxonomy_synonyms', '[]'::jsonb))
    on conflict (local_concept_id, synonym) do update set
      synonym_type = excluded.synonym_type,
      source = excluded.source,
      review_status = excluded.review_status;

  insert into public.taxonomy_standard_codes
    select * from jsonb_populate_recordset(
      null::public.taxonomy_standard_codes,
      coalesce(p_payload->'taxonomy_standard_codes', '[]'::jsonb))
    on conflict (local_concept_id, vocabulary_id, concept_code) do update set
      standard_concept_id = excluded.standard_concept_id,
      standard_concept_name = excluded.standard_concept_name,
      standard_concept_flag = excluded.standard_concept_flag,
      concept_class_id = excluded.concept_class_id;

  insert into public.ontology_relations
    select * from jsonb_populate_recordset(
      null::public.ontology_relations,
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

  insert into public.ontology_relation_evidence
    select * from jsonb_populate_recordset(
      null::public.ontology_relation_evidence,
      coalesce(p_payload->'ontology_relation_evidence', '[]'::jsonb))
    on conflict (evidence_id) do update set
      relation_id = excluded.relation_id,
      source_type = excluded.source_type,
      citation_or_url = excluded.citation_or_url,
      evidence_summary = excluded.evidence_summary,
      population_notes = excluded.population_notes,
      evidence_strength = excluded.evidence_strength,
      review_status = excluded.review_status;

  insert into public.ontology_relation_qualifiers
    select * from jsonb_populate_recordset(
      null::public.ontology_relation_qualifiers,
      coalesce(p_payload->'ontology_relation_qualifiers', '[]'::jsonb))
    on conflict (qualifier_id) do update set
      relation_id = excluded.relation_id,
      qualifier_type = excluded.qualifier_type,
      qualifier_concept_id = excluded.qualifier_concept_id,
      qualifier_value = excluded.qualifier_value,
      qualifier_effect = excluded.qualifier_effect,
      is_hard_constraint = excluded.is_hard_constraint,
      notes = excluded.notes;

  -- Bascule la release courante (append-only, une seule is_current).
  update public.semantic_releases set is_current = false where is_current;
  insert into public.semantic_releases (
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
    'relations', jsonb_array_length(coalesce(p_payload->'ontology_relations', '[]'::jsonb))
  );
end;
$$;

revoke all on function public.upsert_semantic_release(jsonb, jsonb) from public;
-- Grant au rôle-groupe augura_app (augura_api en hérite via `grant augura_app to augura_api`,
-- cf. policies.sql) : c'est le rôle que portent le runtime ET les tests d'intégration.
-- Conditionnel car le rôle peut manquer sur un Postgres vierge avant policies.sql.
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'augura_app') then
    execute 'grant execute on function public.upsert_semantic_release(jsonb, jsonb) to augura_app';
  end if;
end $$;

commit;
