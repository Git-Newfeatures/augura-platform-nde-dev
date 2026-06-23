# Design — B4 port: "on-the-fly" semantic enrichment

**Date:** 2026-06-19
**Status:** approved (design), to be planned
**Subsystem:** B4 (`enrich-propose/apply`) — last brick of the B chain (B1 ontology → B2 `dag-llm` → B3 `picot-parse` → **B4 enrich** → B5 frontend).

## 1. Context & objective

DAG Generation (B2, `POST /causal/dag`) works: the LLM **proposes** new concepts/relations (`proposed_concepts` / `proposed_relations`, rendered as dashed orange edges), **but nothing persists them**. The enrichment loop is open: `modules/semantic/repo.py` is read-only, no write route exists, the `upsert_semantic_release` RPC is absent, and the frontend surfaces (`CausalEnrichPanel`/`EnrichmentSection`/`LearnFromQuestionPanel`) were deliberately omitted (cf. `apps/web/src/workspace/SemanticLayerPage.jsx:12-13`).

Objective: **close the loop** — make it possible to enrich the governed semantic layer (propose + apply), by faithfully porting the old repo's feature, adapted to the platform's conventions.

## 2. Provenance (port source)

- Repo: `Augura-Health/augura`, branch `data-intake-nde` (Nicolas Delporte). Local working copy: `/Users/quentin/Desktop/Augure/lucis-dashboard`.
- Commit: **`98c1023`** "feat(data-intake): DAG generation refinements, semantic governed vocab, new docs" (2026-06-17) — Nicolas's last commit, **not picked up** during the initial port (proof: `apps/api/.../causal/prompt.py:141` still carries the drifted polarity enum `["increases","decreases","mixed","unknown"]` that `governed-vocab.js` corrects to `["increases","decreases","neutral"]`).
- Source files:
  - `api/enrich-propose.js` — coverage analysis + LLM proposal generation (SSE).
  - `api/enrich-apply.js` — versioned write-back (4 paths).
  - `src/semantic/governed-vocab.js` — shared governed enums.
  - `src/workspace/LearnFromQuestionPanel.jsx` (492 lines) — frontend review surface.
  - `supabase/migrations/20260610000000_create_semantic_schema.sql:258` — `upsert_semantic_release` function.

## 3. Framing decisions (validated with the user)

1. **Governance = global, admin-gated (faithful port).** The semantic layer is global (tables in `public`, RLS `FOR SELECT` shared by all tenants). Enrichment therefore mutates the shared ontology; the **apply is reserved for the `owner` role**. Guardrails: `pending_review`→`approved` workflow + `semantic_releases` versioning. Write via a `SECURITY DEFINER` SQL function (the app role does not have direct write). **No** per-tenant overlay.
2. **Execution of the *propose* = background job.** The pipeline (long, multi-LLM-call) runs via the existing job engine; progress goes through `set_progress()` (replaces the SSE events); the frontend polls the job. The **apply stays synchronous**.
3. **Proposals stored as a JSON artifact** (via `core/storage.py`, like `documents`) — **no** new table. The apply receives the batch + the selection in the body (faithful to the original).

## 4. Architecture

Faithful port split into 3 independently deliverable phases. All the new backend code lives in the `modules/semantic/` vertical slice (the `causal → semantic` import-linter contract is already allowed).

### Phase 1 — Write-path (apply)

**SQL.** Port of `upsert_semantic_release(p_manifest jsonb, p_payload jsonb)`:
- Targets the **`public`** schema (and not `semantic.*` like the original) and the **platform column set**.
- Idempotent per-table upsert (`jsonb_populate_recordset` + `on conflict … do update`) for: `taxonomy_concepts`, `taxonomy_synonyms`, `taxonomy_standard_codes`, `ontology_relations`, `ontology_relation_evidence`, `ontology_relation_qualifiers` (the only tables written by enrichment).
- Handles `semantic_releases`: inserts the new release row (from `p_manifest`) and flips `is_current` (append-only, a single current one) — the platform table has the shape `{semantic_release_version pk, taxonomy_version, causal_ontology_version, dq_ontology_version, omop_cdm_version, source, manifest jsonb, imported_at, is_current}`.
- `SECURITY DEFINER`, privileged owner, explicit `set search_path`; `grant execute` to the application role.
- **Delivery**: addition in `apps/api/supabase/functions.sql` (bundle source) **+** **idempotent** alembic migration `0002+` (`CREATE OR REPLACE FUNCTION`) **+** application to the live DB via Supabase MCP (invariant: the Modal deployment applies neither migrations nor seed).

**Route.** `POST /semantic/enrich/apply`, **`require_role("owner")`**. 4 paths (port of `enrich-apply.js`):
- `proposals` + `selected_concept_ids` + `selected_relation_ids` → filters the approved rows (cascade to synonyms/codes/evidence/qualifiers), stamps `approved`/`active`, bumps **minor** if concepts added otherwise **patch**.
- `direct_relations` → lightweight relations (without IDs) from the DAG proposals: validates that the concepts exist, assigns `ENRR_{date}_{NNN}`, auto-stubs evidence if absent, bumps **patch**. Returns a `relation_id_map` (reconciliation of the DAG's provisional IDs).
- `deactivate_relation` → deactivates a relation deemed false (bump patch, `review_status='deprecated'`).
- `add_qualifier` → adds a qualifier restricting the applicability of a relation (bump patch).

**Repo.** A **single** write method `apply_release(manifest, payload)` that calls the RPC; the rest of `repo.py` stays read-only.

### Phase 2 — Propose pipeline (+ governed-vocab, + polarity fix)

**Governed enums.** New module `modules/semantic/vocab.py`: `POLARITY=["increases","decreases","neutral"]`, `AUGURA_DOMAINS`, `QUALIFIER_TYPES`, `QUALIFIER_EFFECTS`, `STANDARD_CODE_VOCABULARIES`, `RELATION_STRENGTH`, `CAUSAL_PREDICATES` (mirror of the table). Imported by enrichment **and** causal → single source, end of the drift.

**Polarity fix.** `modules/causal/prompt.py` (and `schemas.py`/`builder.py` if the enum is duplicated there) consume `vocab.POLARITY`. Contract changed → **regeneration of the api client** (CI drift-check).

**Pure logic.** `modules/semantic/enrichment.py`, without I/O (testable with mocked LLM):
- `match_tokens`, `directed_bfs`, `analyze_coverage` (port of the coverage analysis: missing concepts + path gaps).
- proposal helpers: `group_missing_concepts`, `apply_prechecks` (reject self-loop/dup/orphan/unknown predicate/L1-without-code; auto-stub evidence), `reassign_ids`, `stamp_rows`, `merge_into`.
- The LLM tool schema `PROPOSAL_SCHEMA` (Pydantic) derives from `vocab.py`.

**Job.** New kind `"enrich_propose"` + `handle_enrich_propose(ctx)` in `jobs/handlers.py`:
- reads the semantic bundle (concepts, synonyms, relations, predicates),
- runs the batches (Batch 1 missing concepts, Batch 2 path gaps, Batch 3 bootstrap of the new concepts; + `selected_concepts` shortcut) via `core/llm/runtime.run_structured_agent`,
- `set_progress()` at each step (setup/coverage/propose/precheck) — this is the ported "live log",
- persists the batch of proposals (concepts/relations/evidence/qualifiers + `coverage_summary` + `precheck_log`) as a **JSON artifact** (`core/storage.py`); returns the `result_ref`.

**Route.** `POST /semantic/enrich/propose` (body: `{questions[]}` or `{selected_concepts[]}`) → `create_job("enrich_propose", params)` + `enqueue_job` → returns `job_id`. The frontend polls `GET /jobs/{id}`; on success, fetches the proposals artifact.

### Phase 3 — Frontend

- Port of `LearnFromQuestionPanel.jsx` → review component mounted in `SemanticLayerPage`: triggers the propose job, shows the progress (job polling), lists proposed concepts/relations with selection (checkboxes + cascade), POSTs `apply`. **No mock/fallback** (everything comes from the real backend).
- `CausalModelingPage`: "accept" button on the `proposed_*` edges → `apply` via `direct_relations`, then `resetSemanticStore()` (already defined, never wired) + re-fetch of the bundle.

## 5. Tests

- **Unit** (pytest, mocked LLM) — `enrichment.py`: coverage, `directed_bfs`, pre-checks (each rejection), dedup, reassign IDs, auto-stub evidence. Logic core, high ROI.
- **Integration** (`@pytest.mark.integration`, requires `AUGURA_DATABASE_URL`) — `upsert_semantic_release`: insert + conflict update + `is_current` flip; RLS isolation (the app role writes *via* the function, not directly).
- **Apply** — `owner` gating (403 otherwise); `direct_relations` / `deactivate_relation` / `add_qualifier` paths.
- **Job** — `handle_enrich_propose` with mocked LLM: produces a coherent batch, `set_progress` called, artifact written.

## 6. Contracts & CI

`ruff format --check` + `ruff check` + `pyright` (strict) + `lint-imports` (causal→semantic OK) + `pytest`. **Regeneration** `apps/api/scripts/dump_openapi.py` → `openapi.json` then `npm --prefix packages/api-client run generate` (new routes + polarity enum). **Idempotent** migration + live DB application via Supabase MCP. Frontend: `npm run lint` + `npm run build`.

## 7. Out of scope (YAGNI)

- Per-tenant overlay/enrichment (decision: global ontology).
- SSE streaming (decision: job + polling).
- Dedicated proposals table (decision: JSON artifact).
- Releases/rollback management UI (the table exists, so does `GET /semantic/release`; no new versioning UI here).
- Rewrite of the non-enrichment-related DAG refinements present in `98c1023` (we only port what serves enrichment + the polarity fix).

## 8. Risks / attention points

- **`upsert_semantic_release` must target `public`** (the original targets `semantic.*`) and match the platform columns exactly — a schema divergence = a silent bug. Verify column by column against `schema.sql`.
- **Writing under RLS**: validate that `SECURITY DEFINER` + `grant execute` to the `augura_api` role is enough (the role is non-BYPASSRLS, RLS `FOR SELECT` only).
- **Polarity enum change**: potential breakage of existing DAG data typed `mixed`/`unknown` — verify that no live data depends on these values before switching.
- **Apply after deploy**: the SQL function must be applied to the live DB separately (Modal does not migrate).
