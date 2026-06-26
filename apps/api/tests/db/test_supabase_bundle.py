"""Structural check of the Supabase SQL bundle (without a database).

Guards against omissions / typos / drift. The real execution of the bundle is
proven in CI against a Postgres + pgvector (job `db-bundle`).
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
    "dataset_files",
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
    # Dimension grammar / affix archetypes (A1) — global, read-only.
    "dimension_kinds",
    "affix_archetypes",
    "affix_archetype_values",
    "affix_archetype_aliases",
    # Ontology/causal (B1) — global, read-only.
    "taxonomy_standard_codes",
    "taxonomy_therapeutic_areas",
    "taxonomy_relationships",
    "causal_predicates",
    "dq_predicates",
    "ontology_relations",
    "ontology_relation_evidence",
    "ontology_relation_qualifiers",
    "semantic_releases",
    "dq_bundles",
    "literature_snapshots",
    "search_sessions",
    "literature_events",
    "literature_queries",
    # Reference catalogs (frontend real-only cleanup) — global, read-only.
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
    # Compliance / audit (Phase 3).
    "audit_events",
}

# Reference catalogs (frontend real-only cleanup): global, read-only.
REFERENCE_CATALOGS = {
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
}

# Tenant-scoped tables that MUST carry an RLS policy.
RLS_REQUIRED = {
    "orgs",
    "memberships",
    "studies",
    "study_members",
    "study_state",
    "datasets",
    "dataset_columns",
    "dataset_files",
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
    "dq_bundles",
    "literature_snapshots",
    "search_sessions",
    "literature_events",
    "literature_queries",
}


def _read(name: str) -> str:
    return (SUPABASE_DIR / name).read_text(encoding="utf-8")


def test_bundle_files_present_and_non_empty() -> None:
    for name in ("schema.sql", "functions.sql", "policies.sql", "seed.sql"):
        text = _read(name)
        assert text.strip(), f"{name} is empty"


def test_schema_declares_every_expected_table() -> None:
    schema = _read("schema.sql")
    declared = set(re.findall(r"create table if not exists (\w+)", schema))
    assert declared == EXPECTED_TABLES, {
        "missing": EXPECTED_TABLES - declared,
        "extra": declared - EXPECTED_TABLES,
    }


def test_schema_enables_pgvector_and_hnsw() -> None:
    schema = _read("schema.sql")
    assert "create extension if not exists vector" in schema
    assert "vector(1536)" in schema
    assert "using hnsw" in schema


def test_policies_enable_rls_on_every_tenant_table() -> None:
    policies = _read("policies.sql")
    # Tables covered by the array loops (there are several) + the explicit ALTERs.
    array_blocks = re.findall(r"array\[(.*?)\]", policies, re.DOTALL)
    assert array_blocks
    looped = {name for block in array_blocks for name in re.findall(r"'(\w+)'", block)}
    explicit = set(re.findall(r"alter table (\w+) enable row level security", policies))
    covered = looped | explicit
    missing = RLS_REQUIRED - covered
    assert not missing, f"RLS missing on: {missing}"
    assert "force row level security" in policies


def test_functions_define_match_chunks_and_coverage_view() -> None:
    fns = _read("functions.sql")
    assert "create or replace function match_chunks" in fns
    assert "create or replace view v_coverage_map" in fns
    assert "embedding <=> query_embedding" in fns  # pgvector cosine distance


def test_seed_includes_cesl_reference_catalogs() -> None:
    seed = _read("seed.sql").lower()
    assert "insert into cesl_sources" in seed
    assert "insert into cesl_study_designs" in seed


def test_reference_tables_have_select_only_rls() -> None:
    policies = _read("policies.sql")
    for t in ("cesl_sources", "cesl_study_designs"):
        assert f"alter table {t} enable row level security" in policies
        assert f"create policy backend_read on {t}" in policies
    # Read-only: the reference policy is FOR SELECT (no tenant writes).
    assert "for select" in policies


def test_reference_catalogs_have_select_only_rls() -> None:
    policies = _read("policies.sql")
    array_blocks = re.findall(r"array\[(.*?)\]", policies, re.DOTALL)
    looped = {name for block in array_blocks for name in re.findall(r"'(\w+)'", block)}
    explicit = set(re.findall(r"alter table (\w+) enable row level security", policies))
    covered = looped | explicit
    missing = REFERENCE_CATALOGS - covered
    assert not missing, f"backend_read RLS missing on catalogs: {missing}"
    assert "create policy backend_read" in policies
    assert "for select" in policies


def test_taxonomy_tables_have_select_only_rls() -> None:
    policies = _read("policies.sql")
    for t in (
        "taxonomy_concepts",
        "taxonomy_synonyms",
        "taxonomy_dq_valid_values",
        "taxonomy_measurement_units",
        "unit_conversions",
        "table_archetypes",
        "dq_constraints",
    ):
        assert f"alter table {t} enable row level security" in policies
        assert f"create policy backend_read on {t}" in policies


def test_seed_includes_semantic_taxonomy() -> None:
    seed = _read("seed.sql").lower()
    for t in (
        "taxonomy_concepts",
        "dq_constraints",
        "table_archetypes",
        "taxonomy_measurement_units",
    ):
        assert f"insert into {t} " in seed


# ── Ontology/causal (B1): 8 global tables, read-only, seeded. ──────
ONTOLOGY_TABLES = (
    "taxonomy_standard_codes",
    "taxonomy_therapeutic_areas",
    "taxonomy_relationships",
    "causal_predicates",
    "dq_predicates",
    "ontology_relations",
    "ontology_relation_evidence",
    "ontology_relation_qualifiers",
)


def test_ontology_tables_have_select_only_rls() -> None:
    # RLS set via a format() loop: we check membership in the looped array
    # + that the emitted policy is indeed FOR SELECT (read-only, no tenant writes).
    policies = _read("policies.sql")
    array_blocks = re.findall(r"array\[(.*?)\]", policies, re.DOTALL)
    looped = {name for block in array_blocks for name in re.findall(r"'(\w+)'", block)}
    missing = set(ONTOLOGY_TABLES) - looped
    assert not missing, f"backend_read RLS missing on ontology: {missing}"
    assert "create policy backend_read on %i for select" in policies.lower()


def test_seed_includes_ontology() -> None:
    seed = _read("seed.sql").lower()
    for t in ("ontology_relations", "causal_predicates", "taxonomy_standard_codes"):
        assert f"insert into {t} " in seed


# ── Dimension grammar / affix archetypes (A1): 4 governed read-only tables. ──
AFFIX_TABLES = (
    "dimension_kinds",
    "affix_archetypes",
    "affix_archetype_values",
    "affix_archetype_aliases",
)


def test_affix_tables_have_select_only_rls() -> None:
    # RLS set via the same B1 format() loop as the ontology catalogs.
    policies = _read("policies.sql")
    array_blocks = re.findall(r"array\[(.*?)\]", policies, re.DOTALL)
    looped = {name for block in array_blocks for name in re.findall(r"'(\w+)'", block)}
    missing = set(AFFIX_TABLES) - looped
    assert not missing, f"backend_read RLS missing on affix tables: {missing}"


def test_seed_includes_affix_grammar() -> None:
    seed = _read("seed.sql").lower()
    for t in AFFIX_TABLES:
        assert f"insert into {t} " in seed
    # The relative-time archetype's anchor concept must be seeded too (FK).
    assert "'l1_surgery'" in seed


def test_affix_archetypes_declare_comparability() -> None:
    """Comparability invariant (§18): affix archetypes declare 'preserves' or
    'forks' (enforced by the DB CHECK; the starter set exercises both)."""
    seed = _read("seed.sql")
    block = re.search(r"insert into affix_archetypes\b.*?on conflict do nothing;", seed, re.DOTALL)
    assert block, "affix_archetypes seed block not found"
    assert "'preserves'" in block.group(0)
    assert "'forks'" in block.group(0)


# ── Seed hygiene: seed.sql must stay demo-free (tenant/demo data lives only in
# tests/integration/fixtures.sql). Reference/ontology catalogs are allowed. ──
TENANT_DATA_TABLES = {
    "orgs",
    "memberships",
    "studies",
    "study_members",
    "study_state",
    "datasets",
    "dataset_columns",
    "dataset_files",
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
    "dq_bundles",
    "literature_snapshots",
    "search_sessions",
    "literature_events",
    "literature_queries",
}


def test_seed_has_no_tenant_data_inserts() -> None:
    seed = _read("seed.sql").lower()
    inserted = set(re.findall(r"insert into (\w+)", seed))
    leaked = inserted & TENANT_DATA_TABLES
    assert not leaked, f"seed.sql must stay demo-free; tenant-data inserts found: {sorted(leaked)}"


# ── schema.sql ↔ alembic guard: a table added to schema.sql after baseline but
# with no migration exists on fresh DBs/CI yet is MISSING on already-migrated prod. ──
ALEMBIC_VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"

# Tables introduced AFTER the 0001 baseline (each must ship in a >=0002 migration).
POST_BASELINE_TABLES = {
    "literature_snapshots",
    "search_sessions",
    "literature_events",
    "literature_queries",
    "semantic_releases",
    "dataset_files",
    "audit_events",
    # Dimension grammar / affix archetypes (0011_affix_archetypes).
    "dimension_kinds",
    "affix_archetypes",
    "affix_archetype_values",
    "affix_archetype_aliases",
} | REFERENCE_CATALOGS

# Everything the baseline bundle (0001 applies schema.sql wholesale) already created.
BASELINE_TABLES = EXPECTED_TABLES - POST_BASELINE_TABLES


def _tables_created_in_migrations() -> set[str]:
    tables: set[str] = set()
    for path in sorted(ALEMBIC_VERSIONS.glob("0*.py")):
        if path.name.startswith("0001"):
            continue
        src = path.read_text(encoding="utf-8").lower()
        tables |= set(re.findall(r"create table(?: if not exists)? (\w+)", src))
        tables |= set(re.findall(r"create_table\(\s*[\"'](\w+)", src))
    return tables


def test_usage_events_is_append_only() -> None:
    """The login-event forgery vector (authenticated INSERT) is removed and the app
    role cannot UPDATE/DELETE audit rows (Part 11 / HIPAA 164.312(b))."""
    policies = _read("policies.sql").lower()
    assert "grant insert on usage_events to authenticated" not in policies
    assert "create policy usage_events_insert on usage_events" in policies
    assert re.search(r"revoke[^;]*update[^;]*on usage_events from augura_app", policies, re.S)


def test_outbox_events_is_append_only() -> None:
    policies = _read("policies.sql").lower()
    assert "create policy outbox_events_insert on outbox_events" in policies
    assert re.search(r"revoke[^;]*on outbox_events from augura_app", policies, re.S)


def test_datasets_bucket_provisioned_private() -> None:
    """The datasets bucket is created private in the bundle (guarded so bare-Postgres
    CI is a no-op)."""
    policies = _read("policies.sql").lower()
    assert "storage.buckets" in policies
    assert "'datasets'" in policies
    # Pin the privacy intent: the conflict path must force public = false (not merely
    # mention "public" — a public=true block would otherwise slip through).
    assert re.search(r"public\s*=\s*false", policies)


def test_post_baseline_tables_each_have_a_migration() -> None:
    """Any table in schema.sql that isn't part of the 0001 baseline MUST also be
    created by a >=0002 migration, or it will be missing on already-migrated prod DBs."""
    schema_tables = set(re.findall(r"create table if not exists (\w+)", _read("schema.sql")))
    in_migrations = _tables_created_in_migrations()
    unguarded = {t for t in schema_tables if t not in BASELINE_TABLES and t not in in_migrations}
    assert not unguarded, (
        "tables in schema.sql with no >=0002 migration (would be missing on prod): "
        f"{sorted(unguarded)}. Add a migration, or add to BASELINE_TABLES if it predates 0002."
    )


def test_audit_events_append_only() -> None:
    """audit_events carries the INSERT policy, the trigger function, and the
    revoke that makes it append-only for augura_app (HIPAA 164.312(b) / GDPR)."""
    policies = _read("policies.sql").lower()
    assert "create policy audit_events_insert" in policies
    assert "audit_row_change" in policies
    assert re.search(r"revoke[^;]*on audit_events from augura_app", policies, re.S)
