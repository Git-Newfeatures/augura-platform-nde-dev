# Workstream A — Abstract-based curation on `/corpus/literature/retrieve`

**Date:** 2026-06-21
**Status:** design validated (pending spec review)
**Scope:** backend (`corpus` module) + a small frontend touch (show the rationale, stamp the provenance at freeze time)

## Context & objective

`POST /corpus/literature/retrieve` fans out PubMed + CT.gov live, grouped by
source, streamed in NDJSON (`meta` → `group`/source → `done`). Today the
retrieval is "dumb": PubMed `esearch` with `sort=relevance` → `efetch` of the
top-N verbatim; CT.gov via the API v2's native relevance order. **No
abstract reading, no prioritization by evidence level, no rationale.**

This is the only *retrieval-quality* regression still real vs the old
`augura/corpus-live` branch (whose agent read the abstracts and returned "the N
most relevant / highest evidence level" with a rationale).

**Objective:** restore this **curation** behavior on the topical path of
`retrieve`, in a typed, bounded, reproducible and cheap way.

## Decisions (from the brainstorming)

1. **Behavior = curation parity.** Over-fetch a large pool, the LLM reads the
   candidates, returns the best N ranked by relevance + evidence strength, with
   one rationale per item. **Curation may drop weak results.**
2. **Two sources.** PubMed curated by abstract; CT.gov curated by its
   structured fields (title / conditions / interventions / phase / status).
3. **Streaming = group curated at once.** A source's `group` is only emitted once
   curation is finished. The NDJSON `meta|group|done` contract is **kept**; the
   frontend just shows a "curating…" state. Minimal frontend change.
4. **Always active, graceful degradation.** Curation by default on every
   `retrieve`. No Anthropic key / LLM failure → silent fall back to the current
   relevance top-N order (the same way `expand_pubmed_query` degrades). No opt-in flag.
5. **Approach = structured agent, one call per source.** Reuses
   `run_structured_agent` (forced tool + Pydantic validation + 1 repair retry) and
   `settings.agent_model_fast`. The LLM returns **only ordered ids + rationale**.

## Non-goals (YAGNI)

- No agentic tool-use loop (approach 3) — that is the territory of the "big
  feature" B (keyword workbench), not A.
- No numeric per-item scoring (approach 2).
- No `evidence_tier` produced by the LLM: we keep the deterministic `evidence_type`
  already derived in `pubmed.py`. The LLM is *instructed* to weigh evidence strength
  in its ranking, but fabricates no evidence field.
- No result cache (separate item C).
- No keyword / MeSH-UID / openFDA re-validation (feature B).

## Architecture

New file `apps/api/src/augura_api/modules/corpus/curation.py`, sibling of
`pubmed.py` / `ctgov.py`, isolating all the LLM logic:

- **`Curator` Protocol** — injectable (tests provide a fake curator without
  network):
  ```
  async def curate(query, source, candidates: list[CurationCandidate]) -> list[CuratedRef]
  ```
- **`CurationCandidate`** (dataclass): `id`, `title`, `text` — `text` = abstract
  (PubMed) or a summary of the structured fields (CT.gov), truncated (~1200 chars) to bound the
  tokens.
- **`CuratedRef`** (output): `id`, `rationale`. The **order of the list** carries the
  ranking.
- **`LLMCurator`**: the real implementation. Forced tool returning
  `{ "selected": [ { "id": str, "rationale": str }, ... ] }` (≤ `max_results`).
  System: "biomedical librarian; rank by relevance to the question,
  bringing up stronger evidence (meta-analyses / systematic reviews / RCT >
  observational > other); short rationale per item; never invent an id".
- **Constant** `CURATION_PROMPT_VERSION = "curate-v1"` exported for provenance.

`retrieval.py` imports the **`Curator` Protocol** (not the Anthropic client) →
clean layers. `curation.py` imports `core.llm.runtime`; `corpus` may import
`core.llm` (`lint-imports` contract respected).

## Data flow

**Topical path only.** The known-item (PMID/DOI/title/NCT) stays an exact lookup
with 1 result — **never curated**.

```
_topical(query, srcs, max_results, day, filters)
  for each requested source (in parallel, via the existing gather):
    1. over-fetch a pool: POOL = min(50, max(25, max_results * 2))
       (bounded by retmax ≤ 50 on the PubMed side; CT.gov pageSize equivalent)
    2. if curator present:
         render the candidates (id + title + truncated text)
         → curator.curate(query, source, candidates) → ordered [CuratedRef]
         → map ids → ALREADY-fetched records (the LLM only emits ids
           → zero content fabrication), reorder, keep max_results,
           attach rationale.
    3. if curator absent: trim relevance top-N (= current behavior).
  → SourceGroup(source, query_string, items[, note])
```

Default POOL = 25 (`max_results` default 10 → pool 25, bounded to 50).

**Deterministic guardrails** (in `retrieval.py`, outside the LLM):
- ids outside the pool (hallucinated) → ignored;
- duplicate ids → deduplicated (first kept);
- **empty output / everything filtered while there were candidates → fall back to relevance
  top-N** (never an empty group due to a curation fault).

## Contract changes (⇒ regen OpenAPI + client, CI drift-check)

- `RetrievedItem` (`retrieval.py` dataclass): new field `rationale: str | None = None`.
- `schemas.RetrievedItemOut`: `rationale: str | None = None`.
- `schemas.FrozenResult`: `rationale: str | None = None` (snapshot persistence).
- Stream **`meta`** event enriched: `curated: bool`, `model_version: str | None`,
  `prompt_version: str | None` (= `CURATION_PROMPT_VERSION`). Gives the frontend the
  provenance to *freeze* a reproducible snapshot (the snapshot's `model_version` /
  `prompt_version` fields already exist, waiting for this).
- `snapshot_service.to_retrieve_response`: passes `rationale=i.rationale`.
- `snapshot_service._build_payload`: adds `"rationale": r.rationale` to the results.

**Snapshot compat**: `rationale` optional. Old snapshots (payload without the
key) re-read without breakage — `FrozenResult(**r)` tolerates the absence (default `None`), and
`verify_content_hash` recomputes on the **as-stored** payload → unchanged hash.
New snapshots include `rationale` in the hash.

After the contract: `uv run python apps/api/scripts/dump_openapi.py` then
`npm --prefix packages/api-client run generate`.

## Error handling / degradation

- The curation call is wrapped: `AgentUpstreamError` / `AgentInvalidOutput` → `warning`
  log + fall back to relevance top-N **without rationale**; no exception ever propagated.
- Combined with the existing `_safe_group`: a source that fails (403 CT.gov, LLM failure) breaks
  neither the fan-out nor the stream — the other source comes back normally.
- No Anthropic key → `curator=None` (the router catches it as for the embedder) →
  `retrieve` behaves exactly as today. **Zero regression possible.**

## Router wiring

In `literature_retrieve`:
- build the curator from `get_anthropic_client(settings)`; on
  `AgentUpstreamError` → `curator=None` (same pattern as the embedder in `/literature`).
- pass `curator` + `settings.agent_model_fast` to `LiteratureRetriever`.
- the LLM `AsyncClient` is not an HTTP request-scoped one: `LLMCurator` holds the
  injected Anthropic client; the NDJSON `gen()` stays unchanged (the `group` arrives already
  curated). The `meta` event now carries `curated` / `model_version` / `prompt_version`.

## Tests (CI: ruff · strict pyright · lint-imports · pytest · OpenAPI drift-check)

- **`curation.py`** (LLM mocked via the `LLMClient` Protocol): reorders according to the
  output; drops the non-selected ones; ignores hallucinated ids; deduplicates;
  truncates the text; invalid tool output → `AgentInvalidOutput` (tested at the
  `run_structured_agent` level, already covered; here we test the mapping).
- **`retrieval.py`** (curator stub): over-fetch → curate → trim to `max_results`;
  known-item **not curated**; `curator=None` → relevance top-N unchanged; curator that
  raises → graceful fallback + stream intact; empty output → fall back to relevance top-N.
- **regression**: the existing `retrieve` tests pass (add `curator=None`
  or a stub depending on the case).

## Files touched

| File | Change |
|---|---|
| `corpus/curation.py` | **NEW** — `Curator` Protocol, `LLMCurator`, candidates, tool + output, `CURATION_PROMPT_VERSION` |
| `corpus/retrieval.py` | over-fetch + curation in `_topical`; `rationale` field; guardrails |
| `corpus/router.py` | build curator; pass to the retriever; enriched `meta` |
| `corpus/schemas.py` | `rationale` on `RetrievedItemOut` + `FrozenResult` |
| `corpus/snapshot_service.py` | pass `rationale` (response + payload) |
| `apps/web/src/workspace/literature/literatureClient.js` + UI | show rationale; stamp model/prompt at freeze |
| backend tests | `curation.py` + `retrieval.py` |
| `packages/api-client` | regen OpenAPI + client |

## Risks / open points

- **Latency**: +1 LLM call per source (≈2–5 s) before emitting the group. Mitigated
  by the `agent_model_fast` model and the bounded pool (25). Accepted (streaming decision).
- **Abstract truncation**: 1200 chars may cut a long abstract; enough to
  judge relevance. Configurable if needed.
- **Token cost**: ~25 candidates × ~1200 chars ≈ ~10–15k input tokens per source.
  Bounded, on a fast model.

## Commit policy

`CLAUDE.md`: "only commit/push/deploy on explicit request". The spec is
**written but not committed**; commit on request.
```
