# Spec — Ad-hoc literature search port (+ Browse removal)

> Date: 2026-06-19 · Branch: `Quentin` · Status: **validated, pending review**
> Source of the ported UI: `lucis-dashboard@corpus-live` → `src/literature/AdHocQuery/*`
> Target: `augura-platform` (`apps/web` + `apps/api/modules/corpus`)

## 1. Context & objective

The current Literature page ([apps/web/src/workspace/CorpusPage.jsx](../../../apps/web/src/workspace/CorpusPage.jsx)) has 3 sub-tabs — **Browse**, **Study matches** (semantic search), **Ad-hoc query** (simple PubMed textarea). The user wants to:

1. **Remove Browse.**
2. Replace the **ad-hoc query** with the rich multi-source search from the old branch (reference capture): PubMed + ClinicalTrials.gov sources, date & study-type filters, *Recent queries*, *Saved evidence*, results grouped by source, Keep/Dismiss, Save to study/standalone.
3. (Decided in brainstorming) add an **"Add to corpus"** action so that the "Study matches" semantic search has something to feed on.

**Key observation:** the current `corpus` backend is already largely capable. Already present:
- `POST /corpus/literature/retrieve` — PubMed + CT.gov fan-out, streamed in NDJSON (`meta → group(s) → done`), known-item routing (PMID/DOI/title→PubMed, NCT→CT.gov). ([router.py:147](../../../apps/api/src/augura_api/modules/corpus/router.py#L147))
- `POST/GET /corpus/literature/snapshots/{id}` — reproducible freeze (content-hash). ([router.py:182](../../../apps/api/src/augura_api/modules/corpus/router.py#L182))
- `POST/GET /corpus/literature/sessions(+events)` — sessions + event log. ([router.py:200](../../../apps/api/src/augura_api/modules/corpus/router.py#L200))

## 2. Scope

**Included**
- Removal of the Browse sub-tab.
- Port of the rich UI, wired 100% to the real endpoints (no-mock rule).
- **Backend: date + study-type filters** on `retrieve`.
- **Backend: `GET /corpus/literature/snapshots`** (list) — for *Saved evidence*.
- **Backend: `POST /corpus/literature/ingest`** (by PMIDs) — for "Add to corpus".

**Deferred** (hidden in the UI as long as it is not backed — otherwise it would be a mock)
- **Cache** → the distinction *Search sources* (cache-first) vs *Refresh from source* (bypass); for now **a single button** "Search sources" (always live).
- **Agent activity panel** → the stream does not emit `intent`/`agent_activity` events.

**Out of scope / not ported**
- Demo mode and `demoFixture.js` (forbidden by the no-mock rule).
- The old repo's Vercel serverless API (`api/literature.js`) — we already have FastAPI.
- Restoring the filters when re-opening a *recent query* (no cache → we relaunch live).
- CT.gov ingestion (corpus ingestion is PubMed-only today) → "Add to corpus" disabled on a CT.gov result, with an honest note.

## 3. Backend architecture (`apps/api/src/augura_api/modules/corpus`)

### 3.1 Filters on `retrieve`
- **Schema** ([schemas.py:129](../../../apps/api/src/augura_api/modules/corpus/schemas.py#L129)) — extend `LiteratureRetrieveRequest`:
  - `date_range: Literal["any","1y","5y","10y"] = "any"`
  - `study_types: list[Literal["rct","observational","systematic_review","meta_analysis"]] = []`
- **Plumbing** — thread the filters through `LiteratureRetriever.retrieve() → _topical() → _pubmed_topical()/_ctgov_topical()` ([retrieval.py:114](../../../apps/api/src/augura_api/modules/corpus/retrieval.py#L114)). Extend the `Protocol` `PubMedClient.search` / `CTGovClient.search` (+ real implementations + test fakes).
  - **PubMed** ([pubmed.py:173](../../../apps/api/src/augura_api/modules/corpus/pubmed.py#L173)): add to `_esearch` the params `mindate`/`maxdate` (computed from `date_range`, current year − N) + `datetype=pdat`. Types → `[pt]` terms combined `(query) AND (a[pt] OR b[pt])`:
    | study_type | PubMed term |
    |---|---|
    | rct | `Randomized Controlled Trial[pt]` |
    | meta_analysis | `Meta-Analysis[pt]` |
    | systematic_review | `Systematic Review[pt]` |
    | observational | `Observational Study[pt]` |
  - **CT.gov** ([ctgov.py:88](../../../apps/api/src/augura_api/modules/corpus/ctgov.py#L88)): date via `filter.advanced=AREA[StudyFirstPostDate]RANGE[<min>,MAX]`; type via `aggFilters=studyType:int|obs`. **Partial mapping assumed**: `observational`→`obs`, `rct`→`int`; `systematic_review`/`meta_analysis` have no CT.gov equivalent → ignored on the CT.gov side (if **only** these two types are checked, CT.gov returns nothing filtered — documented behavior, not an error).
  - **Known-item**: the `_known_item` path ignores the filters (an exact identifier is not filtered) — documented in the docstring.

### 3.2 Snapshot list — `GET /corpus/literature/snapshots`
- `LiveRepo.list_snapshots(tenant_id, *, study_id: UUID | None = None)` ([live_repo.py](../../../apps/api/src/augura_api/modules/corpus/live_repo.py)) — `select` scoped to `org_id == tenant`, optional `study_id` filter, sort `created_at desc`.
- New lightweight schema `SnapshotSummary`: `id, study_id, query, sources, created_at, result_count` (we do NOT return `results` nor re-verify the hash for a list).
- Route `GET /corpus/literature/snapshots?study_id=` → `list[SnapshotSummary]`. Re-opening a snapshot stays `GET …/snapshots/{id}` (full results + hash check, already in place).

### 3.3 Ingestion by records — `POST /corpus/literature/ingest`
- Request: `{ pmids: list[str] }` (1–50).
- Service: `fetch_by_ids(pmids)` (already in `NCBIPubMedClient`) → reuses the ingestion machinery of `LiteratureService` (Document + Chunk + optional embedding, dedup by URL/tenant already existing).
- Response: `LiteratureSearchResult` (reused: `found`, `ingested`, `embedded`, `documents`).
- **PubMed only** — CT.gov not supported for ingestion (known gap).

### 3.4 Snapshot provenance
The `retrieve` does not use an LLM. For `SnapshotWriteRequest` (which requires `model_version`/`prompt_version`), the frontend sends provenance constants of the retrieve pipeline: `model_version="retrieve"`, `prompt_version="v1"` (no LLM expansion in this path).

### 3.5 Contract & CI
`uv run python scripts/dump_openapi.py` → `packages/api-client/openapi.json`, then `npm --prefix packages/api-client run generate`. Full CI gate: `ruff format --check`, `ruff check`, `pyright`, `lint-imports`, `pytest`.

## 4. Frontend architecture (`apps/web/src/workspace`)

### 4.1 `CorpusPage.jsx`
- Remove the `{ id:'browse', … }` entry from `SubTabs` ([CorpusPage.jsx:236](../../../apps/web/src/workspace/CorpusPage.jsx#L236)) and the `{sub === 'browse' && (…)}` block (lines 244-291).
- `useState('browse')` → default to the workbench tab (e.g. `'query'`).
- Remove the now-dead fetch `useCollection('corpus_coverage')` (line 206) and the imports/`CORPUS_ICON` that served only the Browse cards (keep `Library`, still used by the `EmptyState`).
- **Keep** `useCollection('corpus_sources')` (serves the `total` subtitle + the empty-state gating).
- Final tabs: **Ad-hoc query** (workbench, default) + **Study matches** (semantic, unchanged).

### 4.2 New `workspace/literature/` folder
Components ported and adapted to the repo's primitives (the old repo already uses shadcn Card/Button/Badge → minimal restyle):
- `LiteratureWorkbench.jsx` — container (state via `useReducer`), orchestrates search/save/recent/saved.
- `QueryInput.jsx` — textarea + source toggles (PubMed/CT.gov) + date buttons (Any/1y/5y/10y) + type toggles (RCT/Observational/Systematic review/Meta-analysis) + **a single** "Search sources" button.
- `ResultsList.jsx` / `ResultCard.jsx` — results grouped by source, count badges, collapsible abstract, **Keep/Dismiss** buttons, **Add to corpus** button (disabled if source = CT.gov).
- `RecentQueries.jsx` — collapsible list from `GET …/sessions`.
- `SavedEvidence.jsx` — collapsible list from `GET …/snapshots`, read-only re-open via `GET …/snapshots/{id}`.
- `SessionActions.jsx` — Save to study / Save standalone / New query / Discard.
- `StudyPicker.jsx` — modal, study list via the existing `studies` collection (dataClient).
- `literatureClient.js` — wrappers over `apiFetch`/`apiJson` + **NDJSON reader** (`res.body.getReader()` + `TextDecoder`, line buffer, `JSON.parse`, dispatch `type` ∈ `meta|group|done`). No streaming helper exists today in [api.js](../../../apps/web/src/api.js).

### 4.3 Data flow (all on real endpoints)
| UI | Endpoint |
|---|---|
| Search (grouped results) | `POST /corpus/literature/retrieve` (NDJSON stream) |
| Recent queries | `POST …/sessions` (1 per search) + `GET …/sessions` |
| Keep / Dismiss (audit) | `POST …/sessions/{id}/events` |
| Save to study / standalone | `POST …/snapshots` |
| Saved evidence (list + re-open) | `GET …/snapshots` *(new)* + `GET …/snapshots/{id}` |
| Add to corpus | `POST …/ingest` *(new, PubMed only)* |
| StudyPicker | existing `studies` collection |

## 5. Error handling
- Stream: network error / server-side `raise_for_status` → error card in the relevant group; group `note` (e.g. known-item miss) shown as-is.
- `AbortController` to cancel a stream in progress (query change / New query).
- Snapshot save failure → inline message (no global toast if the repo has none).
- `GET snapshot/{id}` with a hash divergence → hard error propagated (already handled backend) → "evidence not verifiable" card.
- "Add to corpus": success = "ingested" badge on the result; failure = inline message; CT.gov = disabled button + tooltip.

## 6. Tests
**Backend (pytest, clients injected as fakes — existing pattern)**
- `_esearch` correctly builds `mindate/maxdate/datetype=pdat` according to `date_range`, and the `term` includes the `[pt]` according to `study_types`.
- CT.gov: `filter.advanced` / `aggFilters` params according to filters; "only systematic_review/meta_analysis" case → no CT.gov studyType filter.
- `list_snapshots`: tenant-scoping (one tenant does not see another's snapshots), `study_id` filter.
- `POST /ingest`: `fetch_by_ids` called with the PMIDs, dedup reused.
**Frontend**: verification via preview (the web CI gate = eslint). Lint `npm run lint`.

## 7. Implementation breakdown (tentative — detailed in the plan)
1. **Backend filters**: schemas + retrieval + pubmed/ctgov + tests.
2. **Backend `GET snapshots` + `POST ingest`**: repo + service + router + schemas + tests.
3. **OpenAPI**: dump + regen api-client.
4. **Frontend — Browse removal** (CorpusPage).
5. **Frontend — workbench**: `literature/` + NDJSON reader + wiring.
6. **Preview check** + lint + full CI gate.

## 8. Risks / watch points
- **Imperfect CT.gov mapping** of study types (assumed & documented).
- **Aggressive PubMed `[pt]`**: too many types checked may over-filter → verify that at least one result comes back on typed queries.
- **Potentially empty corpus**: Browse removed + ephemeral retrieve → "Study matches" now depends on "Add to corpus" and the existing ingestion.
- **NDJSON on Modal/Vercel**: confirm that `application/x-ndjson` streaming passes end-to-end in prod (otherwise fallback: read the full response then split — the line-by-line format allows it).
- **Commit**: per CLAUDE.md, **no commit/push without an explicit request** — this doc is not committed until you ask for it.
