# Plan — `/semantic` admin: Affix & DQ views + migrate reads to the `semantic` schema

**Date:** 2026-06-26
**Status:** Proposed
**Scope:** Add two **read-only** administration tabs to the `/semantic` workspace — (1) dimension
grammar / affix archetypes, (2) data-quality governance — modelled on the existing Taxonomy/Causal
tabs. Separately, begin **migrating the `/semantic` admin reads from the `public` schema to the
`semantic` schema**, leaving the other consumers on `public` for now.
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

In parallel, the `/semantic` admin tool should read from the **`semantic` schema** rather than the
`public` copy that the rest of the platform consumes.

### 1.1 Verified DB reality (checked live against `Augura_Prod`, `fqmoylmvjoafihiuiiuj`)

This inverts the assumption recorded in earlier notes, so it is stated explicitly:

- The governed layer **lives in `public`**. All ORM models use bare `__tablename__`; all bundle SQL
  uses bare table names → resolve to `public` via `search_path`. `public` is the **active source of
  truth** (it holds `semantic_releases`, current release `2.2.0`, and is what enrichment writes to via
  `public.upsert_semantic_release`).
- The `semantic` schema is **no longer the stale 16-table leftover** — during planning it was brought
  to **20 tables** and is currently **in sync** with `public` for the governed tables (affix 5/5,
  dimension_kinds 12/12, ontology_relations 75/75, taxonomy_concepts 172/172). It holds **19 of the 20
  governed tables** the admin tool needs.
- **One naming gap:** `semantic` has a legacy **`releases`** table (same columns as
  `public.semantic_releases`); there is no `semantic.semantic_releases`.
- The app role **`augura_api` can already read `semantic`**: `USAGE` on the schema, RLS enabled, one
  policy, and `SELECT` granted on every governed table. So repointing reads is feasible.
- **Critical caveat:** the `semantic` schema is **NOT part of the managed DB bundle**
  (`apps/api/supabase/schema.sql` / alembic / `seed.sql` build only `public`). Dev and CI databases
  have **no `semantic` schema**. Repointing reads to it makes the backend depend on a schema that only
  exists in prod unless we bring it into the bundle (§4.3).

The plan is split so the **views (§3)** ship independently of the **schema migration (§4)**.

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
- **`dq` — "Data quality":** sub-sections (inner segmented control) for **Constraints**
  (`dq_constraints` → bound predicate, scope, severity), **Predicates** (`dq_predicates`), **Table
  archetypes** (`table_archetypes` → key selectors, semantic score), and **Valid value sets**
  (`taxonomy_dq_valid_values` grouped by concept). Row → detail modal.

No nav/route change — both live inside the existing `/semantic` page
([sections.js:20](../../apps/web/src/shell/sections.js), [App.jsx:59](../../apps/web/src/App.jsx)).

---

## 4. Part B — migrate `/semantic` admin reads from `public` → `semantic`

Goal: only the **read** endpoints of the semantic module resolve to the `semantic` schema; all other
modules and the enrichment **write** path stay on `public`.

### 4.1 Scope the switch to the semantic READ endpoints only

Reads: `GET /semantic/bundle`, `/semantic/release`, `/semantic/concepts`, `/semantic/relations`. They
use shared ORM models (bare tablenames) + raw bundle SQL, so the cleanest contained switch is a
**transaction-local `search_path`** set per request, applied **only** to those routes:

1. Add a semantic-specific session dependency (new `modules/semantic/deps.py`) that takes the request
   session and runs `select set_config('search_path', 'semantic, public', true)` — transaction-local,
   like the tenant GUCs in [core/db.py:91-117](../../apps/api/src/augura_api/core/db.py). Use it in
   [router.py](../../apps/api/src/augura_api/modules/semantic/router.py) for the four read endpoints in
   place of the plain `SessionDep`.
2. **Do NOT apply it to the enrich endpoints** (`/semantic/enrich/apply`, `/propose`). Their helpers
   (`max_relation_seq`, `get_relation_row`, `existing_concept_ids`, and `apply_release` →
   `public.upsert_semantic_release`) must keep reading/writing `public`. `upsert_semantic_release` is
   already `public.`-qualified and so is safe regardless.
3. `search_path = semantic, public` makes any table missing from `semantic` fall back to `public` — a
   built-in safety net.

### 4.2 Fix the release-table name gap

With `search_path = semantic, public`, `_RELEASE_SQL`'s bare `semantic_releases` would fall through to
`public.semantic_releases` (inconsistent with the bundle now reading `semantic`). Add an **additive
view** in the `semantic` schema so the release read resolves there:

```sql
create view semantic.semantic_releases as select * from semantic.releases;
```

No code change to `_RELEASE_SQL`, future-proof. (Alternative — rename `semantic.releases`; rejected as
needlessly destructive.)

### 4.3 The big decision — make `semantic` a first-class, reproducible schema

Because dev/CI build only `public`, repointing reads breaks local dev and the `test_semantic_*`
integration tests unless the `semantic` schema exists there too. Two paths:

- **4.3a (recommended, correct): bring `semantic` into the managed bundle.** Add the `semantic` schema
  DDL + RLS + grants to `apps/api/supabase/` (a dedicated `semantic_schema.sql` or a section of
  `schema.sql`), create it in a new idempotent migration (`0013_semantic_schema.py`,
  `down_revision = "0012_affix_release_function"`), and define how it is populated/kept in sync with
  `public` (see §4.4). Then `db-bundle` CI and local dev both have it and the repoint is reproducible.
- **4.3b (interim, lighter): env-gated repoint.** Add a setting (e.g. `AUGURA_SEMANTIC_SCHEMA`, default
  `public`); only set the `search_path` when configured (prod). Dev/CI stay on `public`. Fast to ship
  but introduces prod-vs-dev divergence — the admin tool is then "migrated" in prod only. Acceptable as
  a deliberate first step, to be promoted to 4.3a later.

### 4.4 Source-of-truth / sync coherence (must be decided, not assumed)

Enrichment writes go to **`public`** (`upsert_semantic_release`), and the affix migration was applied to
**both** schemas during planning — so something keeps `semantic` in sync, but the mechanism is not in
this repo. After this change the admin tool reads `semantic` while authoring still targets `public`;
they drift unless sync is explicit. Decide and document one of: (a) keep authoring in `public` and add a
release-time mirror `public` → `semantic`; or (b) make `semantic` the authored copy and mirror to
`public` for the other consumers. This is the key open governance item.

---

## 5. Files touched (summary)

- **Backend:** `modules/semantic/repo.py`, `schemas.py`, `router.py`, new `modules/semantic/deps.py`;
  (4.3a) `apps/api/supabase/*.sql` + `alembic/versions/0013_semantic_schema.py`; regenerate
  `packages/api-client/openapi.json` + `schema.d.ts`; tests in `tests/db/`, `tests/integration/`,
  `tests/test_semantic_service.py`.
- **Frontend:** `lib/semantic-store.js`, `workspace/SemanticLayerPage.jsx`, new
  `semantic/affix-loader.js` + `dq/dq-loader.js`.
- **DB (prod, via Supabase MCP):** `create view semantic.semantic_releases` (§4.2); confirm
  `dq_predicates` in `semantic` has RLS + grant; (4.3a) apply the managed `semantic` schema DDL.

---

## 6. Validation & CI

1. **Backend contract:** `cd apps/api && uv run ruff format --check . && uv run ruff check . &&
   uv run pyright && uv run lint-imports && uv run pytest -q`. The `db-bundle` job and OpenAPI
   drift-check must pass (regen the client after §3.1).
2. **Bundle includes `dq_predicates`:** `GET /semantic/bundle` returns the key with 9 rows.
3. **Reads hit `semantic` (Part B):** with the repoint active, confirm `GET /semantic/bundle` and
   `/semantic/release` return `semantic`-schema data (compare counts; temporarily diverge one row in
   `semantic` to prove the source). Confirm enrichment `/apply` still targets `public`.
4. **Frontend:** `cd apps/web && npm run dev`, open `/semantic`; verify the two new tabs render the
   affix (5 archetypes / 12 kinds) and DQ (32 constraints / 9 predicates / 8 archetypes) data, modals
   open, filters work, and Taxonomy/Causal/Versions tabs still load.
5. **No regression for other modules:** dq/mapping/causal endpoints still read `public` (search_path
   change scoped to semantic read routes only).

---

## 7. Execution checklist

1. [ ] `repo.py` / `schemas.py` — add `dq_predicates` to the bundle (18 → 19); update comments.
2. [ ] Regenerate OpenAPI + `packages/api-client`; update bundle count/shape tests.
3. [ ] `semantic-store.js` — add `getStoredDqPredicates`.
4. [ ] New `affix-loader.js` + `dq-loader.js`.
5. [ ] `SemanticLayerPage.jsx` — add the `affixes` and `dq` SubTabs (read-only).
6. [ ] `modules/semantic/deps.py` — scoped `search_path` dependency; wire the 4 read endpoints (§4.1).
7. [ ] `create view semantic.semantic_releases` in prod (§4.2).
8. [ ] Decide §4.3 (managed schema vs env-gate) and §4.4 (sync direction); implement chosen path.
9. [ ] CI green (lint/types/import-linter/pytest/db-bundle/drift) + manual frontend verification.

## 8. Risks / notes

- The memory note `semantic-layer-canonical-in-public` is now partially outdated (the `semantic` schema
  is being kept in sync, not stale) — update it after this lands.
- Part B couples the app to the `semantic` schema; do **not** ship it without §4.3 (managed schema or
  env-gate) or local dev + CI break.
- Both new tabs stay strictly read-only — consistent with Taxonomy/Causal (§15.4).
