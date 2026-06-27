# Plan — `/semantic` admin: Affix & DQ views + consolidate the semantic layer onto the `semantic` schema

**Date:** 2026-06-26
**Status:** Proposed
**Scope:** Add two **read-only** administration tabs to the `/semantic` workspace — (1) dimension
grammar / affix archetypes, (2) data-quality governance — modelled on the existing Taxonomy/Causal
tabs. Then **consolidate the whole semantic layer onto the `semantic` schema**: move *all* semantic
reads (admin + dataset mapping + causal DAG + enrichment) **and** the enrichment write path from the
`public` copy to the `semantic` schema, in a safe order, so `public`'s governed copy can later be
deprecated.

> **Decision (2026-06-26):** the admin views stay under the **existing `/semantic` endpoints** (no
> separate dedicated path), and **all shared consumers move to `semantic` together** — one consistent
> source of truth. This supersedes the earlier "leave other consumers on `public`" framing: that was
> rejected because `GET /semantic/bundle` (and `SemanticRepo`) are shared, so a partial move would
> split reads from the write path (see §1.2).
**Source specs:** `docs/specs/2026-06-25-augura-semantic-layer-v3.md` (§1.1, §2.3, §2.7, §15.4),
`docs/specs/2026-06-25-dq-management-north-star.md`, `docs/plans/2026-06-25-affix-archetypes-supabase-plan.md` (§9 UI follow-up).

---

## 1. Why

The `/semantic` workspace ([SemanticLayerPage.jsx](../../apps/web/src/workspace/SemanticLayerPage.jsx))
has four read-only tabs (Taxonomy, Causal, Enrichment, Versions) over the governed semantic layer
served by `GET /semantic/bundle`. Two governed capabilities have **data but no admin surface**:

1. **Dimension grammar / affix archetypes** (`dimension_kinds`, `affix_archetypes`,
   `affix_archetype_values`, `affix_archetype_aliases`) — already shipped in the bundle, never displayed.
2. **Data-quality governance** (`dq_constraints`, `table_archetypes`, `taxonomy_dq_valid_values`, and
   `dq_predicates`) — partly in the bundle; `dq_predicates` is deliberately excluded today
   ([repo.py:25](../../apps/api/src/augura_api/modules/semantic/repo.py)).

In parallel, the platform should read the governed layer from the **`semantic` schema** rather than the
`public` copy. Per the 2026-06-26 decision this is a **full consolidation** (not admin-only), staged
safely (§4).

### 1.1 Verified DB reality (checked live against `Augura_Prod`, `fqmoylmvjoafihiuiiuj`)

This inverts the assumption recorded in earlier notes, so it is stated explicitly:

- The governed layer **lives in `public`**. All ORM models use bare `__tablename__`; all bundle SQL
  uses bare table names → resolve to `public` via `search_path`. `public` is the **active source of
  truth** (it holds `semantic_releases`, current release **`2.3.0`**, and is what enrichment writes to
  via `public.upsert_semantic_release`).
- The `semantic` schema is **no longer the stale 16-table leftover** — it now holds **20 tables** and is
  **in sync** with `public` for the governed tables (affix 5/5, dimension_kinds 12/12,
  ontology_relations 75/75, taxonomy_concepts 172/172, dq_predicates 9/9, release **`2.3.0`**). It holds
  **all governed tables** the admin tool needs.
- **One naming gap:** `semantic` has a legacy **`releases`** table (same columns as
  `public.semantic_releases`); there is no `semantic.semantic_releases`.
- The app role **`augura_api` can already read `semantic`**: `USAGE` on the schema, RLS enabled, one
  policy, and `SELECT` granted on every governed table. So repointing reads is feasible.
- **Critical caveat:** the `semantic` schema is **NOT part of the managed DB bundle**
  (`apps/api/supabase/schema.sql` / alembic / `seed.sql` build only `public`). Dev and CI databases
  have **no `semantic` schema**. Repointing reads to it makes the backend depend on a schema that only
  exists in prod unless we bring it into the bundle (§4.3).

The plan is split so the **views (§3)** ship independently of the **schema migration (§4)**.

### 1.2 Blast radius of repointing reads (verified)

`GET /semantic/bundle` is **not** admin-only — it hydrates the frontend semantic store consumed by
**dataset mapping, causal DAG modeling, the enrichment panel, and PICOT parsing**. On the backend,
`modules/mapping/service.py` and `modules/causal/service.py` call `SemanticRepo` directly
(`list_concepts`/`list_synonyms`/`list_relations`…). So "make `/semantic` read `semantic`"
unavoidably moves mapping + causal + enrichment too. Two consequences drive the §4 ordering:

- **Read/write split (critical):** enrichment **writes** `public.upsert_semantic_release`. If reads move
  to `semantic` while writes stay on `public`, freshly-authored concepts/relations are invisible until a
  mirror runs. → the write path must move to `semantic` **before** reads (§4.2 before §4.3).
- **Dev/CI parity:** `semantic` exists only in prod. Repointing breaks local dev + `test_semantic_*` +
  the `db-bundle` CI unless `semantic` is first brought into the managed bundle (§4.1).

---

## 2. Pattern to reuse

Mirror `TaxonomyTab` / `CausalOntologyTab` in
[SemanticLayerPage.jsx](../../apps/web/src/workspace/SemanticLayerPage.jsx): `SubTabs` selector → filter
controls → `Card` table → detail modal. Data flows store → loader → tab, fully read-only (§15.4). Reuse
the existing chip/modal styles in that file (`DOMAIN_CHIP`, `MODAL_TAB`, etc.). Loaders follow the
join/index style of [taxonomy-loader.js](../../apps/web/src/semantic/taxonomy-loader.js) and
[ontology-loader.js](../../apps/web/src/causal/ontology-loader.js). Store getters live in
[semantic-store.js](../../apps/web/src/lib/semantic-store.js).

---

## 3. Part A — the two read-only admin tabs (main deliverable)

### 3.1 Backend — expose `dq_predicates` in the bundle

The DQ view needs `dq_predicates`, currently excluded.

1. [repo.py](../../apps/api/src/augura_api/modules/semantic/repo.py) — add `"dq_predicates"` to
   `_BUNDLE_TABLES` (bundle becomes **19 tables**). `_BUNDLE_SQL`/`_RELEASE_SQL` build from the tuple,
   so they follow automatically. Update the "18 tables" comment.
2. [schemas.py](../../apps/api/src/augura_api/modules/semantic/schemas.py) — add
   `dq_predicates: list[dict[str, Any]]` to `SemanticBundle`; update its "18 tables" docstring.
   (`DqPredicate` ORM already exists, `models.py:201`.)
3. Regenerate the contract (CLAUDE.md): `uv run python apps/api/scripts/dump_openapi.py` →
   `npm --prefix packages/api-client run generate`. The CI drift-check fails otherwise.
4. Update the bundle shape/count assertions (18 → 19) in
   [test_supabase_bundle.py](../../apps/api/tests/db/test_supabase_bundle.py),
   [test_semantic_repo.py](../../apps/api/tests/integration/test_semantic_repo.py),
   [test_semantic_service.py](../../apps/api/tests/test_semantic_service.py).

### 3.2 Frontend store — one getter

[semantic-store.js](../../apps/web/src/lib/semantic-store.js): add
`export const getStoredDqPredicates = () => get('dq_predicates')` and extend the contract comment.
Affix getters already exist (`getStoredDimensionKinds`, `getStoredAffixArchetypes`,
`getStoredAffixArchetypeValues`, `getStoredAffixArchetypeAliases`, `semantic-store.js:93-96`).

### 3.3 Frontend loaders (new)

- `apps/web/src/semantic/affix-loader.js` — index `affix_archetypes` joined to their
  `affix_archetype_values` and `affix_archetype_aliases` (group by `affix_archetype_id`); expose
  `dimension_kinds` keyed by `dimension_kind_id`. Synchronous reads from the store.
- `apps/web/src/dq/dq-loader.js` — expose `dq_constraints` (joined to `dq_predicates` by the bound
  predicate id), `table_archetypes`, and `taxonomy_dq_valid_values` grouped by concept.

### 3.4 The two tabs in `SemanticLayerPage.jsx`

Add to the `SubTabs` array (after `causal`, before `enrichment`):

- **`affixes` — "Dimensions & affixes":** a `dimension_kinds` table (kind, value_model, comparability)
  and an `affix_archetypes` table (name, kind, position, value_model, comparability, thresholds). Row →
  modal showing the archetype's canonical values + token aliases.
- **`dq` — "Data quality":** a main **Constraints** table (`dq_constraints` → bound predicate, scope,
  severity). A constraint row opens a detail modal whose sub-tabs **walk its linked entities** — the
  bound **Predicate** (`dq_predicates`), its **Scope**, and the relevant **Valid value sets**
  (`taxonomy_dq_valid_values`). **Table archetypes** (`table_archetypes` → key selectors, semantic
  score) appear as a secondary table whose rows open their own detail modal.
  **Decision (2026-06-26):** follow the north-star drill-down spine (constraint → predicate · scope ·
  valid values) — *not* four parallel flat lists. Predicates and valid value sets are reached *through*
  a constraint, not browsed as standalone top-level lists.

No nav/route change — both live inside the existing `/semantic` page
([sections.js:20](../../apps/web/src/shell/sections.js), [App.jsx:59](../../apps/web/src/App.jsx)).

---

## 4. Part B — consolidate the semantic layer onto the `semantic` schema

Goal (per the 2026-06-26 decision): **all** semantic reads (the `/semantic` read endpoints **and** the
`mapping`/`causal` services that call `SemanticRepo`) **and** the enrichment write path resolve to the
`semantic` schema. `public`'s governed copy becomes unused and is deprecated later. The four steps are
ordered so nothing breaks mid-flight — **B1 → B2 → B3 → B4**.

### 4.1 (B1, prerequisite) Make `semantic` reproducible in dev/CI

`semantic` exists only in prod, so repointing first breaks local dev + `test_semantic_*` + `db-bundle`.
Bring it into the managed bundle:

- Add the `semantic` schema DDL + RLS + grants under `apps/api/supabase/` (a dedicated
  `semantic_schema.sql`, or a guarded section of `schema.sql`).
- New idempotent migration `0014_semantic_schema.py`,
  `down_revision = "0013_dataset_column_dimensions"` (0011–0013 are already taken by the affix work).
- Populate/seed it (mirror the `public` governed seed into `semantic`) so CI + local dev have the same
  data.
- Add the release view so the bare `semantic_releases` name resolves inside the schema:

  ```sql
  create view semantic.semantic_releases as select * from semantic.releases;
  ```

  (Additive; avoids a destructive rename of the legacy `semantic.releases`. Keeps `_RELEASE_SQL`'s bare
  `semantic_releases` working once `search_path` is `semantic, …`.)

### 4.2 (B2) Flip the write path to `semantic` — BEFORE repointing reads

`public.upsert_semantic_release` is `public.`-qualified internally, so it writes `public` regardless of
`search_path`. Provide a `semantic`-writing release function (schema-qualify its inserts to `semantic.*`
and the release switch to `semantic.releases`), and point `SemanticRepo.apply_release` + the enrich
helpers (`max_relation_seq`, `get_relation_row`, `existing_concept_ids`) at `semantic`. Doing this
before §4.3 keeps authored data and reads consistent (else freshly-enriched concepts/relations vanish
from every UI). *Interim fallback if a hard cutover is too risky: keep writing `public` and mirror
`public → semantic` at the end of the function — but a clean cutover matches the "deprecate `public`"
goal.*

### 4.3 (B3) Repoint reads via one transaction-local `search_path`

`semantic` holds only the 20 governed tables, so `search_path = semantic, public` routes governed reads
to `semantic` and everything else (tenant tables: `dataset_columns`, `datasets`, …) to `public`
automatically.

- **Decision (2026-06-26):** do this in **one central place** — a single shared helper/dependency that
  runs `select set_config('search_path', 'semantic, public', true)` transaction-locally, in the style of
  the tenant GUCs in [core/db.py:91-117](../../apps/api/src/augura_api/core/db.py). Never scattered or
  duplicated per module.
- **Incremental rollout:** wire that one helper to the `/semantic` read endpoints **first** (the admin
  tool) and prove it. Then attach the **same** helper to the `mapping`/`causal` request sessions (they
  read governed data via `SemanticRepo`). Those two **must** adopt it by the time the write path moves
  (B2), or they read stale `public` rows — but it is the same single function, not new per-module logic.
- **Watch-out:** `semantic, public` silently falls back to `public` for any table missing in
  `semantic` — a useful transition net, but it **hides drift**. Once B1 makes `semantic` complete,
  tighten to `search_path = semantic` (no fallback) so gaps error loudly instead of serving stale
  `public` rows.

### 4.4 (B4) Verify, then deprecate `public`

After reads + writes are on `semantic` and CI is green, the `public` governed tables are unused by the
app. Dropping them is a **separate later migration** (out of scope here) — flag for the team. Until
then, `public` simply goes stale harmlessly (nothing reads or writes it).

> **Source-of-truth resolved:** `semantic` is canonical; authoring writes `semantic` (B2). No ongoing
> `public ↔ semantic` sync function is introduced — `public` is frozen and later dropped. (This matches
> the directive: no always-on sync; the layer consolidates on `semantic`.)

---

## 5. Files touched (summary)

- **Part A backend:** `modules/semantic/repo.py`, `schemas.py`; regenerate
  `packages/api-client/openapi.json` + `schema.d.ts`; tests in `tests/db/`, `tests/integration/`,
  `tests/test_semantic_service.py`.
- **Part A frontend:** `lib/semantic-store.js`, `workspace/SemanticLayerPage.jsx`, new
  `semantic/affix-loader.js` + `dq/dq-loader.js`.
- **Part B backend:** new `apps/api/supabase/semantic_schema.sql` (+ RLS/grants) and
  `alembic/versions/0014_semantic_schema.py` (B1); `supabase/functions.sql` semantic-writing release fn
  + `SemanticRepo.apply_release`/helpers (B2); the `search_path` set in `core/db.py` or a shared
  dependency, applied to the semantic read endpoints **and** `mapping`/`causal` sessions (B3);
  `modules/semantic/router.py` if wiring via a dependency.
- **Part B DB (prod, via Supabase MCP):** `create view semantic.semantic_releases`; apply the managed
  `semantic` schema DDL/seed from B1; deploy the semantic-writing release function from B2.

---

## 6. Validation & CI

1. **Backend contract:** `cd apps/api && uv run ruff format --check . && uv run ruff check . &&
   uv run pyright && uv run lint-imports && uv run pytest -q`. The `db-bundle` job and OpenAPI
   drift-check must pass (regen the client after §3.1).
2. **Bundle includes `dq_predicates`:** `GET /semantic/bundle` returns the key with 9 rows.
3. **Reads hit `semantic` (Part B):** with the repoint active, confirm `GET /semantic/bundle` and
   `/semantic/release` return `semantic`-schema data (compare counts; temporarily diverge one row in
   `semantic` to prove the source).
4. **Write/read consistency (proves B2-before-B3):** run an enrichment `/apply`, then re-fetch the
   bundle and confirm the newly-authored concept/relation **appears** (it must land in `semantic`).
5. **Frontend:** `cd apps/web && npm run dev`, open `/semantic`; verify the two new tabs render the
   affix (5 archetypes / 12 kinds) and DQ (32 constraints / 9 predicates / 8 archetypes) data, modals
   open, filters work, and Taxonomy/Causal/Versions tabs still load.
6. **Shared consumers moved cleanly:** dataset mapping + causal DAG still work and now read `semantic`;
   tenant tables (`dataset_columns`, `datasets`) still resolve to `public` (governed-only `semantic`).

---

## 7. Execution checklist

**Part A — read-only tabs (ship first, independently):**
1. [ ] `repo.py` / `schemas.py` — add `dq_predicates` to the bundle (18 → 19); update comments.
2. [ ] Regenerate OpenAPI + `packages/api-client`; update bundle count/shape tests.
3. [ ] `semantic-store.js` — add `getStoredDqPredicates`.
4. [ ] New `affix-loader.js` + `dq-loader.js`.
5. [ ] `SemanticLayerPage.jsx` — add the `affixes` and `dq` SubTabs (read-only).

**Part B — consolidate onto `semantic` (strict order B1 → B4):**
6. [ ] **B1** `semantic_schema.sql` + `0014_semantic_schema.py` + seed/populate + `create view
   semantic.semantic_releases`; `db-bundle` CI + local dev build `semantic`.
7. [ ] **B2** semantic-writing release function + `SemanticRepo.apply_release`/helpers → `semantic`
   (deploy before B3).
8. [ ] **B3** one central helper sets transaction-local `search_path = semantic, public` — wired to the
   semantic read endpoints first, then the **same** helper attached to `mapping`/`causal` sessions;
   tighten to `semantic` once B1 is complete.
9. [ ] **B4** verify (incl. enrich-apply visibility); schedule the later `public` drop (separate migration).
10. [ ] CI green (lint/types/import-linter/pytest/db-bundle/drift) + manual frontend verification.

## 8. Risks / notes

- **Order is load-bearing:** B1 (dev/CI parity) before any repoint; B2 (write path) before B3 (reads),
  or freshly-authored enrichment data disappears from every UI.
- The memory note `semantic-layer-canonical-in-public` becomes outdated once Part B lands (`semantic`
  becomes canonical) — update it then.
- The `search_path = semantic, public` fallback hides drift; tighten to `semantic`-only after B1.
- Both new tabs (Part A) stay strictly **read-only** — consistent with Taxonomy/Causal (§15.4). Part B
  adds no data writes beyond moving the existing enrichment write path; its only new schema objects are
  a view + the managed `semantic` DDL.
