"""Vérification structurelle du bundle SQL Supabase (sans base de données).

Garde contre les omissions / typos / dérive. L'exécution réelle du bundle est
prouvée en CI contre un Postgres + pgvector (job `db-bundle`).
"""

import re
from pathlib import Path

SUPABASE_DIR = Path(__file__).parents[2] / "supabase"

EXPECTED_TABLES = {
    "orgs",
    "memberships",
    "studies",
    "study_members",
    "study_state",
    "datasets",
    "dataset_columns",
    "cohort_members",
    "cohort_biomarkers",
    "documents",
    "chunks",
    "agent_runs",
    "agent_cache",
    "simulation_runs",
    "simulation_results",
    "jobs",
    "generated_documents",
    "usage_events",
    "outbox_events",
    "artifacts",
    "cesl_sources",
    "cesl_study_designs",
    "taxonomy_concepts",
    "taxonomy_synonyms",
    "taxonomy_dq_valid_values",
    "taxonomy_measurement_units",
    "unit_conversions",
    "table_archetypes",
    "dq_constraints",
}

# Tables tenant-scopées qui DOIVENT porter une policy RLS.
RLS_REQUIRED = {
    "orgs",
    "memberships",
    "studies",
    "study_members",
    "study_state",
    "datasets",
    "dataset_columns",
    "cohort_members",
    "cohort_biomarkers",
    "documents",
    "chunks",
    "agent_runs",
    "simulation_runs",
    "simulation_results",
    "jobs",
    "generated_documents",
    "usage_events",
    "artifacts",
}


def _read(name: str) -> str:
    return (SUPABASE_DIR / name).read_text(encoding="utf-8")


def test_bundle_files_present_and_non_empty() -> None:
    for name in ("schema.sql", "functions.sql", "policies.sql", "seed.sql"):
        text = _read(name)
        assert text.strip(), f"{name} est vide"


def test_schema_declares_every_expected_table() -> None:
    schema = _read("schema.sql")
    declared = set(re.findall(r"create table if not exists (\w+)", schema))
    assert declared == EXPECTED_TABLES, {
        "manquantes": EXPECTED_TABLES - declared,
        "en trop": declared - EXPECTED_TABLES,
    }


def test_schema_enables_pgvector_and_hnsw() -> None:
    schema = _read("schema.sql")
    assert "create extension if not exists vector" in schema
    assert "vector(1536)" in schema
    assert "using hnsw" in schema


def test_policies_enable_rls_on_every_tenant_table() -> None:
    policies = _read("policies.sql")
    # Tables couvertes par la boucle array + les ALTER explicites.
    array_block = re.search(r"array\[(.*?)\]", policies, re.DOTALL)
    assert array_block is not None
    looped = set(re.findall(r"'(\w+)'", array_block.group(1)))
    explicit = set(re.findall(r"alter table (\w+) enable row level security", policies))
    covered = looped | explicit
    missing = RLS_REQUIRED - covered
    assert not missing, f"RLS manquante sur : {missing}"
    assert "force row level security" in policies


def test_functions_define_match_chunks_and_coverage_view() -> None:
    fns = _read("functions.sql")
    assert "create or replace function match_chunks" in fns
    assert "create or replace view v_coverage_map" in fns
    assert "embedding <=> query_embedding" in fns  # distance cosinus pgvector


def test_seed_includes_cesl_reference_catalogs() -> None:
    seed = _read("seed.sql").lower()
    assert "insert into cesl_sources" in seed
    assert "insert into cesl_study_designs" in seed


def test_reference_tables_have_select_only_rls() -> None:
    policies = _read("policies.sql")
    for t in ("cesl_sources", "cesl_study_designs"):
        assert f"alter table {t} enable row level security" in policies
        assert f"create policy backend_read on {t}" in policies
    # Read-only : la policy de référence est FOR SELECT (pas d'écriture tenant).
    assert "for select" in policies


def test_taxonomy_tables_have_select_only_rls() -> None:
    policies = _read("policies.sql")
    for t in (
        "taxonomy_concepts", "taxonomy_synonyms", "taxonomy_dq_valid_values",
        "taxonomy_measurement_units", "unit_conversions", "table_archetypes", "dq_constraints",
    ):
        assert f"alter table {t} enable row level security" in policies
        assert f"create policy backend_read on {t}" in policies
