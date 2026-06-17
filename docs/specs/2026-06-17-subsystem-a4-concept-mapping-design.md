# Subsystem A4 — Concept mapping (deterministic lexical) — Design

**Date:** 2026-06-17
**Status:** Proposed (awaiting review)
**Part of:** Subsystem **A**, slice **A4**. Depends on A1 (taxonomy + synonyms) + A2 (uploaded datasets + `dataset_columns`). Deterministic, **no LLM** (the LLM path already exists as `/agents/variable-check`).

## Context

Port the MVP's deterministic lexical concept-matcher (`src/semantic/{lexical-normalizer,concept-matcher,confidence-scorer,semantic-mapper}.js`). It maps each dataset column name to the best-matching A1 taxonomy concept (via concept labels + synonyms), scores confidence, and writes proposals to `dataset_columns.{proposed_canonical_id, proposed_role, confidence}` (fields A2 created). It **complements** `/agents/variable-check` (LLM): A4 is the cheap deterministic first pass; variable-check refines / the user confirms (`final_*`). It also unlocks A3's concept-coupled DQ checks (range bounds, units, coded-values) in a later A3c.

## Scope (A4 = tractable core mapper)

**In:** normalizer (core pipeline + starter abbreviation map), string similarity (n-gram cosine + Levenshtein + token Jaccard blend), matcher (exact-synonym → fuzzy-label → fuzzy-synonym), confidence (reduced 3-component), taxonomy index loader (from A1), service (map a dataset's columns → persist proposals), endpoint `POST /datasets/{id}/map` (+ reuse `GET /datasets/{id}/columns` to read proposals).

**Deferred (noted):** domain-heuristic + value-range matching stages; the full 7-component confidence (A4 ships a reduced 3-component); the full ~172-entry abbreviation map (A4 ships a clinical starter subset — synonyms carry most matching); unit-scaling; PICOT parsing; embeddings (excluded by design).

## Architecture

New module `apps/api/src/augura_api/modules/mapping/`:
- `normalize.py` — `normalize(s) -> str`: lowercase → strip timepoint suffixes (`.bl/.3m/.6m/.12m/.pre/.post/.fu…`) → replace separators `[_.:\-/\\|]`→space → drop non-`[a-z0-9 ]` → tokenize → expand abbreviations (starter `ABBREV_MAP`) → drop noise tokens (`value/score/result/id/code/…`) → drop pure-numeric tokens → collapse. Plus `string_similarity(a,b)` = `0.45·ngram_cosine + 0.35·token_jaccard + 0.20·levenshtein`.
- `index.py` — `build_index(concepts, synonyms)`: per concept, precompute `norm_label`, `norm_synonyms`, and a `synonym_lookup: dict[normalized_str -> list[concept_id]]`. Concepts/synonyms come from the A1 `semantic` repo (`list_concepts()`, `list_synonyms()`).
- `matcher.py` — `match_column(norm_name, index, top_n=5) -> list[Candidate]`: exact-synonym (score 0.95, method `exact_synonym`) → else fuzzy: `fuzzy_label` (sim>0.85 ×0.92), `fuzzy_synonym` (sim>0.75 ×0.88); keep score>0.20; dedupe by concept; top-N.
- `confidence.py` — `compute_confidence(best, candidates) -> {score,label}` (reduced): `semantic=best.score (0.50)` + `method_quality (0.30)` (`exact_synonym 1.0 / fuzzy_label 0.92 / fuzzy_synonym 0.85 / else 0.5`) + `ambiguity (0.20)` (gap best−second: `<0.05→0.6, <0.10→0.75, <0.20→0.88, else 1.0`). Labels: ≥0.80 High, ≥0.60 Medium, ≥0.40 Low, >0 Very Low, else Unmapped.
- `service.py` — `MappingService.map_dataset(tenant, dataset_id)`: load `dataset_columns` (A2 profiles) → build index from A1 taxonomy → for each column: `normalize(name)` → `match_column` → `compute_confidence` → set `proposed_canonical_id = best.concept_id`, `proposed_role = best.dq_column_role`, `confidence = score` (only when score>0; leave pending/unmapped otherwise) → persist (update columns) → return a `MapResult` (per-column proposal + summary mapping-rate/avg-confidence). Reuses `datasets` repo to read/update columns.
- `repo.py` — column proposal updates (or reuse `DatasetRepo.replace_columns` carrying the new proposed_* while preserving stats — preferred: a focused `update_proposals(dataset_id, [{column_id, proposed_canonical_id, proposed_role, confidence}])`).
- `router.py` — `POST /datasets/{dataset_id}/map` → `MapResult`. (Read path already exists: `GET /datasets/{dataset_id}/columns`.)
- `__init__.py` — exports `router`; mounted in `main.py`.

`mapping` may import `datasets` + `semantic` public interfaces (neither in the data-module independence contract that covers studies/corpus/datasets — confirm `mapping` not added there; `mapping→datasets` and `mapping→semantic` are allowed).

### Persistence
No schema change — uses existing `dataset_columns.{proposed_canonical_id, proposed_role, confidence, rationale, user_decision}`. A4 sets the `proposed_*` + `confidence`; `user_decision` stays `pending`; `final_*` untouched (user/variable-check own those).

## Reconciliation with `/agents/variable-check`
Both write `dataset_columns` proposals. A4 = deterministic, instant, free; variable-check = LLM, slower, richer. Intended flow: A4 first (baseline proposals) → optionally variable-check to refine low-confidence columns → user confirms (`final_*`). A4 does **not** remove or change variable-check. (No endpoint conflict: A4 is `/datasets/{id}/map`, variable-check is `/agents/variable-check`.)

## Testing
- **Unit — normalize:** `HbA1c_value→"hemoglobin a1c"` (with starter abbrev), timepoint strip (`cgm_tir.BL→"cgm tir"`), noise/numeric removal, separators.
- **Unit — similarity:** identical→1.0; disjoint→low; blend monotonic.
- **Unit — matcher:** exact synonym hit (0.95); fuzzy label/synonym thresholds; top-N + dedupe.
- **Unit — confidence:** exact→High; ambiguous (close 1st/2nd)→penalized; unmapped→0.
- **Integration (DB):** upload (A2) → map → `dataset_columns` rows have `proposed_canonical_id`/`confidence` set for matchable columns; tenant-scoped.
- **Route:** `POST /datasets/{id}/map` in OpenAPI + 401.
- **api-client** regen; **real-DB validation** (upload a CSV with clinically-named columns + seeded taxonomy → map → proposals persisted).

## Acceptance criteria
1. `POST /datasets/{id}/map` maps columns against the A1 taxonomy and persists `proposed_canonical_id`/`proposed_role`/`confidence`; unmatched columns left pending.
2. Deterministic (no LLM); normalizer/matcher/confidence unit-tested against MVP behavior.
3. api-client regenerated; drift-check green.
4. Real-DB validation green (map persists proposals under RLS).

## Risks / open items
- **Starter abbrev map** is a subset of the MVP's ~172 entries — synonyms (1,372 rows) carry most matching; expand later if recall is low. Flagged.
- **Reduced confidence** (3 of 7 components) — data-type/value-range/std-code/missing components deferred (they need value_type/units/std-codes from concepts; fold in with A3c). Flagged.
- **Index build cost** per request (rebuild from taxonomy each map) — fine at current taxonomy size (171 concepts / 1,372 synonyms); cache later if needed.
- **Module independence:** ensure `mapping` is not added to the import-linter independence set; `mapping→{datasets,semantic}` allowed.
