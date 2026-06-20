"""upsert_semantic_release : write-path d'enrichissement de la couche sémantique (B4)

Fonction SECURITY DEFINER : le rôle applicatif (RLS FOR SELECT) écrit l'ontologie
globale EXCLUSIVEMENT via elle. Idempotente (CREATE OR REPLACE + grant conditionnel),
vit aussi dans le bundle canonique functions.sql exécuté par 0001_baseline.

Revision ID: 0006_semantic_enrich_function
Revises: 0005_semantic_release
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_semantic_enrich_function"
down_revision: str | None = "0005_semantic_release"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_SQL = r"""
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
      augura_domain = excluded.augura_domain,
      value_type = excluded.value_type,
      canonical_unit = excluded.canonical_unit,
      design_rationale = excluded.design_rationale,
      review_status = excluded.review_status,
      version = excluded.version,
      active = excluded.active;

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
    manifest = excluded.manifest, is_current = true;

  return jsonb_build_object(
    'version', v_version,
    'concepts', jsonb_array_length(coalesce(p_payload->'taxonomy_concepts', '[]'::jsonb)),
    'relations', jsonb_array_length(coalesce(p_payload->'ontology_relations', '[]'::jsonb))
  );
end;
$$;

revoke all on function public.upsert_semantic_release(jsonb, jsonb) from public;
-- Grant conditionnel : le rôle applicatif n'existe pas sur le Postgres de CI (db-bundle).
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'augura_api') then
    execute 'grant execute on function public.upsert_semantic_release(jsonb, jsonb) to augura_api';
  end if;
end $$;
"""


def upgrade() -> None:
    op.execute(_FUNCTION_SQL)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.upsert_semantic_release(jsonb, jsonb);")
