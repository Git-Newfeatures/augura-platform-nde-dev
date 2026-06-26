# Supabase Update Plan — Affix Archetypes & Dimension Grammar

**Date:** 2026-06-25
**Status:** Proposed
**Scope:** Add the **dimension grammar / affix archetype** capability to the governed semantic layer, plus the adjacent semantic-layer gaps it depends on or exposes.
**Source specs:** `docs/specs/2026-06-25-augura-semantic-layer-v3.md` (§2.7, §1.1, §13 Phase 1) and `docs/specs/2026-06-25-dq-management-north-star.md` (Phase 1, Steps 1.2–1.3).

---

## 1. Why

Step 1.2 of the DQ North Star and §2.7 of the Semantic Layer v3 require that a column label resolve to a **base concept + a set of governed dimensions** instead of minting a new taxonomy concept per concept-and-context combination (`hba1c_baseline`, `hba1c_6mo`, `knee_rom_left`). The decomposition must be governed by **evidence-ranked recognition shapes** — *affix archetypes* — exactly the way `table_archetypes` already governs table-grain recognition. §2.7 rule 4 further requires an affix archetype (wide encoding) and a table archetype (long encoding) to emit the **same canonical dimension representation**.

The current Supabase schema (`apps/api/supabase/schema.sql:515-730`) has **no representation of dimensions or affixes at all**. `table_archetypes` exists but is minimal; `dimension`/`affix` appear nowhere in `apps/api/src`. This is the **Phase 1 gap** called out in §13 (“Introduce dimension grammar and affix archetypes…”) and Architecture Decision §1069.

This plan adds the fifth semantic capability from §1.1 — **dimension grammar** — as new declarative artifacts, sitting beside the taxonomy, causal ontology, DQ ontology, and archetype repository, referencing the shared taxonomy by id (no concept duplication).

---

## 2. Data model (new tables)

Four new governed, read-only tables in the `public` schema, following the existing pattern (text PKs, `review_status`/`version`/`active`, FKs into `taxonomy_concepts`, RLS `backend_read`). They are SHACL-like closed-world recognition profiles, not a new ontology (§2.7, §2.3).

### 2.1 `dimension_kinds` — the closed catalogue of dimension families

One row per structural family from §2.7 (“Dimension kinds”): `scheduled_time`, `relative_time`, `laterality`, `body_site`, `specimen`, `method`, `derived_statistic`, `aggregation_window`, `rater`, `replicate`, `vocabulary`, `condition_status`.

```sql
create table if not exists dimension_kinds (
  dimension_kind_id     text primary key,         -- 'laterality', 'relative_time', ...
  label                 text not null,
  description           text not null,
  value_model           text not null,            -- closed_set | scheduled | parametric | event_anchored | ordinal
  default_comparability text not null check (default_comparability in
                          ('preserves','forks','case_by_case')),  -- §2.7 dimension-vs-distinct-concept
  structural_role       text,                     -- optional Layer-0 role for long-table reconciliation (§2.7 rule 4)
  review_status         text not null,
  version               text not null,
  active                boolean not null
);
```

`structural_role` is the hook for §2.7 rule 4 / North Star Step 1.3: e.g. `relative_time` ↔ a Layer-0 `observation_time` role, so the dimension carried in a column name (wide) reconciles to the same canonical statement as the one carried in a value column (long).

### 2.2 `affix_archetypes` — governed recognition shapes

One row per matcher pattern. Carries everything §2.7 lists an affix archetype must declare: matcher position, the dimension kind it yields, how to extract operator/value/anchor, the comparability flag, and evidence weights/thresholds.

```sql
create table if not exists affix_archetypes (
  affix_archetype_id      text primary key,
  archetype_name          text not null,
  dimension_kind_id       text not null references dimension_kinds(dimension_kind_id),
  position                text not null check (position in ('prefix','suffix','separator')),
  separator_style         text,                   -- '_', '-', camelCase, ...  (matcher)
  value_model             text not null check (value_model in
                            ('closed_set','parametric','event_anchored')),
  comparability           text not null check (comparability in ('preserves','forks')),  -- §2.7: must declare
  anchor_concept_id       text references taxonomy_concepts(local_concept_id),  -- relative-time anchor (postop→surgery)
  operator                text,                   -- pre|post|peri  OR a statistic fn (mean|delta|auc...)
  extraction_rule         text,                   -- how to parse offset/value (regex or named spec id)
  requires_residual_maps  boolean not null default true,   -- rule 1: carve only if residual maps to a concept
  requires_sibling_family boolean not null default false,  -- rule 2: family evidence required
  evidence_weight         numeric not null,
  confidence_threshold    numeric not null check (confidence_threshold between 0 and 1),
  review_status           text not null,
  version                 text not null,
  active                  boolean not null
);
```

### 2.3 `affix_archetype_values` — closed-set canonical values

For `closed_set` archetypes only (`left`/`right`/`bilateral`; `serum`/`plasma`/`urine`). Parametric and event-anchored archetypes extract their value via `extraction_rule` and carry no rows here.

```sql
create table if not exists affix_archetype_values (
  affix_archetype_id text not null references affix_archetypes(affix_archetype_id),
  canonical_value    text not null,               -- 'left','right','serum',...
  label              text not null,
  review_status      text not null,
  primary key (affix_archetype_id, canonical_value)
);
```

### 2.4 `affix_archetype_aliases` — the token/alias layer

The matcher token set and its synonyms, analogous to `taxonomy_synonyms` (`6mo ≡ m6 ≡ month6 ≡ v3`; `OD ≡ right`). `canonical_value` is null for parametric archetypes (value extracted by rule).

```sql
create table if not exists affix_archetype_aliases (
  affix_archetype_id text not null references affix_archetypes(affix_archetype_id),
  token              text not null,               -- the source label fragment
  canonical_value    text,                        -- → affix_archetype_values.canonical_value (closed_set); null otherwise
  source             text not null,
  review_status      text not null,
  primary key (affix_archetype_id, token)
);
create index if not exists affix_archetype_aliases_token_idx on affix_archetype_aliases (lower(token));
```

> Design notes
> - Anchors are **taxonomy concepts** (§2.7 event-anchored time), so `anchor_concept_id` FKs into `taxonomy_concepts` — no new anchor vocabulary.
> - `comparability` is enforced per-archetype (Governance Invariant §18): `preserves` ⇒ a true dimension; `forks` ⇒ the residual must route to a distinct concept.
> - Compositionality (§2.7 rule 3, `bp_sitting_left_6mo`) is a **runtime peeling** concern over these rows, not a stored combination — no table needed.
> - We deliberately do **not** add an RDF/SHACL store (§2.3, §2.7): Supabase tables + application-code evaluation, consistent with `table_archetypes`.

---

## 3. Where the changes land (the DB bundle invariants)

Per `CLAUDE.md`, the schema lives in `apps/api/supabase/` and is applied three different ways. **All three must be updated** or the live DB, the CI db-bundle check, and a fresh `alembic upgrade` will diverge.

1. **`apps/api/supabase/schema.sql`** (canonical) — append the four `create table if not exists` blocks in §2 to the A1 semantic block (after `dq_constraints`, before the B1 block at line 625). Add the alias index.
2. **`apps/api/supabase/policies.sql`** — add the four new tables to the **B1 RLS loop array** (lines 299-310) so each gets `enable/force row level security` + a `backend_read` `FOR SELECT` policy gated on `app.tenant_id`. (Read-only governed catalog; no write policy — writes go through the privileged role / enrichment function.)
3. **New alembic migration `0011_affix_archetypes.py`** — idempotent (`CREATE TABLE IF NOT EXISTS`, `DROP POLICY IF EXISTS … CREATE POLICY`), mirroring §2 DDL + RLS, modeled on `0005_semantic_release.py`. `down_revision = "0010_dataset_files"`. `downgrade()` = `DROP TABLE IF EXISTS … CASCADE` for the four tables. This is what already-migrated DBs use (a table added only to `schema.sql` **bypasses alembic** on a migrated DB — CLAUDE.md gotcha).
4. **`apps/api/supabase/seed.sql`** — seed the initial `dimension_kinds` (the 12 families) and a starter set of `affix_archetypes` + values + aliases (see §6). Seed is applied **separately** (not by alembic, not by Modal).
5. **Apply to the live prod DB by hand.** The Modal deployment runs **neither migrations nor seed**, and `psql`/the app role can’t do DDL. Run the DDL + RLS + seed against `Augura_Prod` (ref `fqmoylmvjoafihiuiiuj`). This is the actual “update to Supabase.”

   > **Execution channel (verified 2026-06-25):** the Supabase MCP `execute_sql` tool is **not available in the current Claude Code session** (only the standard harness tools are surfaced). So the live prod apply must be done one of two ways:
   > - **(a)** paste the consolidated DDL + RLS + seed SQL into the **Supabase SQL editor** (the implementer produces a single ready-to-run script as the deliverable for this step), or
   > - **(b)** run it from a session/environment where the Supabase MCP is connected.
   >
   > All the *local* changes (steps 1–4, §4–§5, §8) are fully doable here; only this live-apply step is gated on the channel above. The migration (`0011`) is what brings the live DB to head when alembic is run there; the SQL editor route is the manual equivalent.

---

## 4. Backend wiring (so the bundle exposes them)

The frontend loads the whole governed layer through `GET /semantic/bundle`. New tables are invisible until added to the bundle.

1. **`modules/semantic/models.py`** — add ORM classes `DimensionKind`, `AffixArchetype`, `AffixArchetypeValue`, `AffixArchetypeAlias` (mirror the `TableArchetype`/`DqConstraint` style).
2. **`modules/semantic/repo.py`** — append the four table names to `_BUNDLE_TABLES` (`repo.py:27-42`); `_BUNDLE_SQL` and `_RELEASE_SQL` build from that tuple, so counts and bundle follow automatically. Add `list_*` accessors if any service needs them directly (optional for now).
3. **`modules/semantic/schemas.py`** — extend `SemanticBundle` with the four new keys (and per-row out-schemas) so the OpenAPI contract advertises them.
4. **Regenerate the contract** (CLAUDE.md): `uv run python apps/api/scripts/dump_openapi.py` → `npm --prefix packages/api-client run generate`. The CI drift-check fails otherwise.

---

## 5. Semantic release bump (governance)

The dimension grammar is part of the semantic release (§15, §1.1 fifth capability).

- Insert a **new `semantic_releases` row** with `is_current = true` and flip the previous current row to `false` (append-only history). Bump `semantic_release_version` (e.g. `2.2.0 → 2.3.0`); `taxonomy_version` = release version; `dq_ontology_version` bumps even though DQ artifacts didn’t change (§15.1 rule).
- Update the `manifest` JSON `source` to note the dimension-grammar addition, and ensure per-table counts in `GET /semantic/release` include the four new tables (automatic via `_BUNDLE_TABLES`).
- Record per-entity pre-apply state for rollback (§15.2) — at minimum, note this is an additive release (new tables, empty before seed ⇒ rollback = drop tables + restore prior current release).

---

## 6. Seed content (initial governed set)

Keep it small and accurate (Governing priority §2: accuracy over coverage). Starter rows that exercise every `value_model`:

| Archetype | kind | value_model | comparability | tokens → value |
|---|---|---|---|---|
| `AFX_LATERALITY` | laterality | closed_set | preserves | `left/l/od→right? ` `right/r`, `bilateral/bilat`, ophthalmic `od→right, os→left, ou→bilateral` |
| `AFX_SCHEDULED_TIME` | scheduled_time | parametric | preserves | `baseline`, `screening`, `eot`, `week12/wk12/w12`, `6mo/m6/month6` (resolved via study visit map) |
| `AFX_RELATIVE_TIME_POSTOP` | relative_time | event_anchored | preserves | `postop/post_op` → operator `post`, `anchor_concept_id` = surgery concept |
| `AFX_SPECIMEN` | specimen | closed_set | **forks** | `serum`, `plasma`, `urine`, `csf` (case-by-case ⇒ forks here) |
| `AFX_DERIVED_STAT` | derived_statistic | parametric | preserves | `mean`, `min/max`, `sd`, `delta/change`, `auc`, `nadir` (may change unit/range) |

Each row sets `requires_residual_maps = true`; family-sensitive kinds (laterality, scheduled_time) set `requires_sibling_family = true` (§2.7 rule 2 — a lone affixed column is weak evidence). Confidence thresholds and evidence weights start conservative and are tuned against the fixtures in §8.

---

## 7. Adjacent semantic-layer changes worth doing in/around this release

These are the other gaps from §12.1 / §2.6 / §3.3 that the affix work either touches or naturally precedes. **Recommended ordering: do (A) and (B) with this release; defer (C)–(E).**

**(A) Reconcile dimensions onto the per-dataset mapping — required to make affixes useful.** `dataset_columns` (`schema.sql:101`) records `proposed_canonical_id`/`final_canonical_id` but has **no place for dimensions**. Add `proposed_dimensions jsonb` / `final_dimensions jsonb` (canonical `{kind, value | operator+anchor+offset}` list), or a child `dataset_column_dimensions` table. This is the runtime output of affix decomposition and the join point with grain-derived dimensions (North Star Step 1.3). Tenant-scoped, so RLS is the dataset’s org — not a governed catalog. *Strongly recommended in the same release; without it the new governed tables have no consumer.*

**(B) Archetype recognition shapes — sibling capability, low marginal cost.** `table_archetypes` is currently just `key_selectors` + `semantic_score`. §2.3 wants required/optional/alternative/disqualifying **roles**, candidate keys, cardinalities, and evidence weights → an `archetype_roles` child table, and an optional `archetype_relationships` (`is_subtype_of`, `specializes`) vocabulary. §2.7 rule 4 explicitly pairs affix and grain archetypes (“two faces of one dimension model”), so doing them together keeps the reconciliation coherent.

**(C) Range profiles — larger, defer.** Today ranges are scalar `value_min`/`value_max` on `taxonomy_concepts`. §3.3 wants `concept_ranges` (range_kind: plausibility/reference/critical/clinical_decision/study_target, with precedence) + `range_context_profiles` (qualifier types: age/sex/pregnancy/condition/specimen/method/laboratory). `range_support_status` already exists on the concept row. This is Phase 2/4 work, independent of affixes — defer to its own release.

**(D) Layer-0 structural concepts & crosswalks — partial.** `fhir_crosswalk`/`sdtm_crosswalk` columns exist on `taxonomy_concepts`; §13 Phase 1 wants the Layer-0 role set fully seeded. The `dimension_kinds.structural_role` link (§2.1) assumes a stable role vocabulary, so seeding Layer-0 roles strengthens (A)/(B). Light touch; can ride along.

**(E) DQ predicate/constraint governance — out of scope here.** `dq_predicates` and `dq_constraints` exist; no change needed for affixes. A dimension “enables cross-variant coherence” checks (North Star Step 2.2), but those constraints are authored later against the new dimension data, not part of this schema change.

---

## 8. Validation & CI (before declaring the release stable)

Per Semantic Layer §11 and `CLAUDE.md` CI (`ruff format --check`, `ruff check`, `pyright`, `lint-imports`, `pytest`, plus the `db-bundle` job and OpenAPI drift-check):

- **Identifier uniqueness & referential integrity** — affix archetype ids unique; every `anchor_concept_id`/`canonical_value` FK resolves; every `affix_archetype_aliases.canonical_value` exists in `affix_archetype_values` for closed-set archetypes.
- **Comparability invariant (§18)** — no `forks` archetype is treated as a comparable dimension; a small check/test that `preserves` vs `forks` is declared on every row.
- **db-bundle CI** — proves the bundle creates on real Postgres+pgvector and seed loads; the four tables must appear with correct counts.
- **Hardcoded expected-table lists in tests** — the existing bundle/db-bundle tests assert the **old 14-table** bundle shape (the count and the table-name set). These are coupled to `_BUNDLE_TABLES` and **will fail** once the four tables are added. Update the expected list (and any count assertion) in the same change. *(Flagged by the readiness audit; not in the original plan.)*
- **OpenAPI drift-check** — passes only after regenerating `openapi.json` + `schema.d.ts`.
- **Affix recognition fixtures** — golden mapping tests (§11 “mapping golden sets”): wide `hba1c_6mo`/`hba1c_12mo` and long `analyte+time` reconcile to the **same** canonical dimension (rule 4); over-carving guard (`min` not stripped from a concept name; lone affixed column rejected without family evidence, rule 2).

---

## 9. Optional UI surface

The `/semantic` workspace is a read-only admin view (§15.4). Add a **“Dimensions” tab** listing `dimension_kinds` and `affix_archetypes` (with tokens/values), mirroring the Taxonomy/Causal tabs. Optional — the data ships in the bundle regardless; the tab is a follow-up.

---

## 10. Execution checklist

1. [ ] `schema.sql` — add 4 tables + alias index (A1 block).
2. [ ] `policies.sql` — add 4 tables to the B1 RLS loop.
3. [ ] `0011_affix_archetypes.py` — idempotent DDL + RLS (mirror 0005).
4. [ ] `seed.sql` — `dimension_kinds` (12) + starter affix archetypes/values/aliases (§6).
5. [ ] *(A)* `dataset_columns` dimensions column/child table + migration.
6. [ ] `models.py` / `repo.py` (`_BUNDLE_TABLES`) / `schemas.py` — expose in bundle.
7. [ ] `dump_openapi.py` → regenerate `packages/api-client`.
8. [ ] New `semantic_releases` row, flip `is_current` (§5).
9. [ ] Update hardcoded expected-table lists/counts in the bundle & db-bundle tests (§8).
10. [ ] Apply DDL + RLS + seed to `Augura_Prod` — **via the SQL editor or an MCP-connected session** (`execute_sql` is not in this session; Modal won’t apply it either). Deliverable: one consolidated SQL script.
11. [ ] CI green (lint/types/import-linter/pytest/db-bundle/drift) + affix fixtures.
12. [ ] *(optional)* `/semantic` Dimensions tab.
13. [ ] *(deferred, separate releases)* (B) archetype roles, (C) range profiles, (D) full Layer-0.
