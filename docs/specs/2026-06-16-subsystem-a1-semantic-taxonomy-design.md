# Subsystem A1 — Semantic taxonomy (DQ-subset) — Design

**Date:** 2026-06-16
**Status:** Proposed (awaiting review)
**Part of:** MVP→platform port. Subsystem **A** (Data Intake + DQ) is decomposed into slices **A1→A2→(A3∥A4)→A5**. This is **A1**, the foundation the DQ engine (A3) and concept mapper (A4) depend on.

## Context

The user chose to pull the semantic taxonomy into subsystem A so the full DQ check suite runs (not just heuristics). A1 ports the **DQ-relevant subset** of the MVP's `semantic` schema into the platform: the reference tables the DQ engine and concept mapper read. It is **D-shaped** — global read-only reference tables + seed + a small read API — and reuses the exact patterns subsystem D established (`FOR SELECT` reference RLS, vertical-slice module, bundle seed, api-client regen).

DDL source of truth: `/tmp/augura-src/supabase/migrations/20260610000000_create_semantic_schema.sql`.
Seed source: `/tmp/augura-src/obsolete/standards/*.csv`.

## Goals

1. Add the 7 DQ-subset taxonomy tables to the platform's canonical SQL bundle (`public` schema), with read-only RLS.
2. Seed them from the MVP CSVs (~1,700 rows) via a committed, deterministic CSV→SQL generator.
3. Provide a backend `semantic` module: ORM models + repo (consumed internally by A3/A4) + a minimal read API for the frontend.
4. Regenerate the api-client; keep CI green.

## Non-goals (deferred)

- **Versioning / releases / enrichment workflow** → subsystem B (we keep the `version`/`review_status`/`active` columns but seed a constant version and never mutate).
- **Causal ontology** tables (`ontology_relations`, `causal_predicates`, `taxonomy_relationships`, `therapeutic_areas`, `taxonomy_standard_codes`) → subsystem B.
- **DQ engine** (A3), **concept mapper** (A4), **upload/parse** (A2), **intake wizard** (A5).
- Write/CRUD on taxonomy (read-only; seed-loaded).

## Architecture

### Tables (added to `apps/api/supabase/schema.sql`, `public` schema)

Port these 7 table definitions from the MVP migration, **stripping the `semantic.` schema prefix** (→ `public`), keeping every column and type verbatim, adding `if not exists`, and **dropping FK references to non-ported tables** (e.g. to `semantic.releases`). Intra-subset FKs (child tables → `taxonomy_concepts.local_concept_id`) are kept.

| Table | PK | Rows | Key columns (used by A3/A4) |
|-------|----|----|------|
| `taxonomy_concepts` | `local_concept_id` | 171 | `concept_name, augura_domain, value_type, value_min, value_max, canonical_unit, unit_source_value, dq_column_role, range_support_status, unit_coverage_status, layer, review_status, version, active` |
| `taxonomy_synonyms` | (composite) | 1372 | `local_concept_id, synonym, synonym_type, source, review_status` |
| `taxonomy_dq_valid_values` | (composite) | 30 | `local_concept_id, value, label, coding_system, review_status` |
| `taxonomy_measurement_units` | `unit_id` | 78 | `concept_id, ucum_code, display_label, source_aliases, status, quantity_kind, is_preferred, review_status, version` |
| `unit_conversions` | `conversion_id` | 16 | `from_ucum, to_ucum, quantity_kind, applicable_concept_id, conversion_type, equation_id, scale_factor, precision, bidirectional, review_status, version` |
| `table_archetypes` | `archetype_id` | 8 | `archetype_name, key_selectors, semantic_score, is_surrogate, description_template, review_status, version, active` |
| `dq_constraints` | `constraint_id` | 32 | `target_scope, subject_concept_or_role, operator, object_concept_or_role, parameters, applies_when, severity, implementation_id, evidence_source, status, version` |

Note: `taxonomy_synonyms` and `taxonomy_dq_valid_values` have no single-column PK in the MVP DDL — port their DDL as-is (add a `primary key` only if the MVP defines one; otherwise leave keyless as the MVP does). Match the MVP exactly.

### RLS (`apps/api/supabase/policies.sql`)

All 7 are **global, read-only** reference tables — identical treatment to D's `cesl_sources`/`cesl_study_designs`: enable + force RLS, one `FOR SELECT` policy `backend_read` gated on `app.tenant_id is not null`. No write policy (seed loads via the privileged role; tenant sessions cannot write). Add the 7 names to a dedicated `do $$ ... foreach ... array[...]` loop **or** explicit `alter table` blocks — but the bundle test asserts literal table names, so use **explicit per-table statements** (as D's implementer found necessary).

### Seed (generated, then committed)

The seed is ~1,700 rows — too large and error-prone to hand-write. Approach:

1. Add a committed generator script `apps/api/scripts/gen_semantic_seed.py` that reads the 7 CSVs from a path arg and emits idempotent `insert into <table> (...) values (...) on conflict do nothing;` SQL to stdout, handling: CSV→SQL quoting/escaping, empty cell → `NULL`, boolean normalization (`true`/`false`/`t`/`1`), numeric passthrough, and column-order alignment to the DDL.
2. Run it once against `/tmp/augura-src/obsolete/standards/` and append the output to `apps/api/supabase/seed.sql` under a clearly-commented `-- semantic taxonomy (A1)` section. (The generator stays in the repo so the seed is reproducible/auditable; the seed SQL is what actually loads.)
3. Seed runs before RLS (Supabase order) or as superuser (CI) — both bypass the read-only policy, so inserts succeed (proven in D's validation).

> **Caveat (flagged, non-blocking):** the CSVs live in the MVP's `obsolete/standards/` folder, so they may lag the live Supabase taxonomy. Functionally sufficient for the DQ engine; swap for authoritative rows later if the user provides MVP DB access. Same posture as D's seed.

### Backend module `semantic` (vertical slice)

`apps/api/src/augura_api/modules/semantic/` — `__init__.py` (exports router), `models.py` (7 ORM tables), `schemas.py`, `repo.py`, `service.py`, `router.py`. Mounted in `main.py`.

- **Repo** (the foundation A3/A4 consume internally): `list_concepts(active=True)`, `get_concept(id)`, `list_synonyms()`, `list_constraints(active/status)`, `list_archetypes(active=True)`, `list_measurement_units()`, `list_unit_conversions()`, `list_valid_values()`. Global reads (no tenant filter); RLS allows read under any backend session.
- **Read API (minimal, YAGNI):** only the frontend-facing endpoint now —
  `GET /semantic/concepts` → `list[ConceptOut]` (optional `?domain=` and `?active=` filters, ordered by `local_concept_id`).
  The other 6 tables are **repo-only** (consumed by A3/A4 in-process); they get models + repo methods but **no HTTP endpoint** until a consumer needs one.
- **Schemas:** `ConceptOut` (the columns the frontend/mapper need: `local_concept_id, concept_name, augura_domain, layer, value_type, value_min, value_max, canonical_unit, dq_column_role, range_support_status, active`). `from_attributes=True`.

## Error handling

- Missing/invalid Bearer → 401 (existing `CurrentTenantDep`).
- Empty result → `200 []` (honest empty).
- No LLM/upstream calls → no new 5xx paths.

## Testing

- **Unit (service, fake repo):** `concepts()` maps rows → `ConceptOut`, applies `active`/`domain` filters; ordering passthrough.
- **Route:** add `/semantic/concepts` to `test_app_routes.py` (OpenAPI presence + 401).
- **Integration (DB, `-m integration`):** new `tests/integration/test_semantic_repo.py` — after seed, `list_concepts` returns active rows ordered; counts match (concepts≈171, constraints=32, archetypes=8, units=78); RLS: readable under `augura_app`+tenant, **write denied**, no-tenant read → 0.
- **DB bundle (`test_supabase_bundle.py`):** add the 7 tables to `EXPECTED_TABLES`; assert seed contains `insert into taxonomy_concepts`/`dq_constraints`/`table_archetypes`; assert `backend_read` FOR SELECT policy on each.
- **Generator unit test:** `tests/test_gen_semantic_seed.py` — feed a tiny fixture CSV, assert correct SQL (NULLs, quoting, booleans).
- **api-client drift:** regenerate; CI green (use a clean worktree if the working tree has unrelated WIP, per D's lesson).

## Acceptance criteria

1. 7 taxonomy tables in the bundle (`public`), RLS read-only, seeded (concepts≈171, synonyms≈1372, units≈78, constraints=32, valid_values=30, conversions=16, archetypes=8).
2. `GET /semantic/concepts` returns the documented shape for an authenticated user; 401 unauthenticated; filters work.
3. Repo methods for all 7 tables exist and are tenant-read/write-denied (validated against real Postgres, as D was).
4. api-client regenerated; drift-check green.
5. Backend + DB-bundle + generator tests pass.

## Risks / open items

- **Seed authenticity:** `obsolete/standards` CSVs may lag live taxonomy (flagged; swap later).
- **Generator correctness on 1,372 synonyms:** covered by the generator unit test + integration count assertions.
- **Forward-compat with B:** B will add ontology/causal tables + a versioning/releases workflow in the same `public` schema; A1 keeps the `version`/`active` columns so B can layer versioning without a migration of A1's tables.
- **`dq_constraints.parameters` / `applies_when`:** free-text/JSON-ish columns consumed by A3's check-planner — port as `text` exactly as the MVP DDL defines; A3 parses them.
