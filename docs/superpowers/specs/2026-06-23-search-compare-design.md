# Search-compare tool — design spec

**Date:** 2026-06-23
**Location:** `tools/search-compare/` (repo root, self-contained)
**Goal:** An interactive Jupyter notebook that runs one clinical question through three
literature-search "lanes" and renders a side-by-side comparison table of their answers.

## The three lanes

| # | Lane | Status today | Auth |
|---|------|--------------|------|
| 1 | **PubMed (LLM-curated)** | Fully working | none (NCBI key optional, raises rate limit) |
| 2 | **Consensus** | Real documented API, gated access | `x-api-key` |
| 3 | **OpenEvidence** | Enterprise + BAA only, contract unverified | API key + org id |

1. **PubMed (LLM-curated).** Claude (`claude-opus-4-8`) converts the natural-language
   question into a curated Entrez query → `esearch.fcgi` (PMIDs) → `esummary.fcgi`
   (citation cards) + `efetch.fcgi` (abstracts) → Claude synthesizes a grounded answer
   citing `[PMID:…]`. Endpoints: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`.
   Rate limits respected (3 req/s without key, 10 with). `tool`/`email` params sent as
   NCBI best practice.

2. **Consensus.** `GET https://api.consensus.app/v1/quick_search?query=…` with header
   `x-api-key`. Returns `results[]` of papers (`title`, `authors`, `abstract`, `doi`,
   `journal_name`, `publish_year`, `url`, `citation_count`). The API returns **papers, not
   a synthesized answer**, so Claude synthesizes the answer cell from the returned papers
   (clearly labeled as such). Without `CONSENSUS_API_KEY` → `not_configured` with a
   "how to apply" note (https://consensus.app/home/api/).

3. **OpenEvidence.** No public API; enterprise agreement + signed BAA required, and the
   request/response schema is not officially published. The adapter is therefore a
   **configurable template**: request path, auth header, and answer/source field mappings
   are all env-overridable, with a loud warning to verify against the official (gated)
   spec. No guessed endpoint is hard-coded as a default that would auto-fire. Without
   `OPENEVIDENCE_API_KEY` + `OPENEVIDENCE_API_BASE` → `not_configured`.

## Honesty / no-fabrication rule

A lane that is not configured returns `status="not_configured"` with a one-line
"how to enable" note. A lane that errors returns `status="error"` with the captured
message. **No lane ever invents an answer or sources.** This matches the repo's
"no mock/fallback/demo data" principle.

## Architecture

```
tools/search-compare/
├── README.md             # what it is, uv setup, how to run, how to enable each lane
├── requirements.txt      # anthropic, requests, pandas, python-dotenv, ipywidgets, jupyterlab, pytest
├── .env.example          # all key/endpoint slots
├── search_lanes.py       # the engine — pure Python, no UI, fully testable
├── test_search_lanes.py  # pytest: table shape, not_configured paths, mocked PubMed flow, error isolation
└── search_compare.ipynb  # thin interactive UI (ipywidgets) calling the engine
```

### Engine (`search_lanes.py`)

- `Source` dataclass: `title, url, year, journal, authors, identifier`.
- `SearchResult` dataclass: `method, status, answer, sources[], query_used, latency_s, error, note`.
- `pubmed_llm_search(question, *, model)` — lane 1.
- `consensus_search(question, *, model, synthesize=True)` — lane 2.
- `openevidence_search(question, *, model)` — lane 3.
- `compare(question, *, model)` — runs all three concurrently via `ThreadPoolExecutor`
  so one slow/failing lane never blocks the others; each lane is additionally wrapped so
  it can never raise out of `compare`.
- `lane_status()` — `{lane: "ready" | "needs …"}` for the notebook header.
- `results_to_dataframe(results)` — pandas table (rows = lanes; columns = Method, Status,
  Answer, Top sources, Latency).
- `results_to_html(results)` — styled HTML comparison table with clickable source links
  and status badges, for inline display in the notebook.

LLM access is isolated in `_llm_complete()` and E-utilities access in `_eutils_get()` so
tests can monkeypatch them without network.

### Notebook (`search_compare.ipynb`)

1. Markdown: title + the three lanes.
2. Setup cell: `load_dotenv()`, import engine, render `lane_status()`.
3. UI cell: `ipywidgets` Textarea (question) + retmax slider + "Run comparison" button +
   Output area. On click → `compare()` → `display(HTML(results_to_html(...)))` plus a
   per-lane `Accordion` of full citations.
4. Markdown: how to enable Consensus / OpenEvidence lanes.

## Error handling

- Every lane isolates its work in `try/except` → `status="error"`, message in `error`.
- Missing key/endpoint → `status="not_configured"` + `note`.
- NCBI requests time out (30 s) and `raise_for_status()`; client respects rate limits.
- The notebook degrades gracefully: not-configured lanes still appear as a row.

## Testing

`test_search_lanes.py` (pytest, no network):
- `results_to_dataframe` / `results_to_html` shape with hand-built results.
- Consensus & OpenEvidence return `not_configured` when keys absent.
- PubMed flow with `_build_pubmed_query`, `_pubmed_esearch`, `_pubmed_esummary`,
  `_pubmed_abstracts`, and `_llm_complete` monkeypatched → `status="ok"`, sources + answer set.
- Lane error isolation: a lane that raises internally yields `status="error"` and
  `compare()` still returns three results.

Plus a one-off **live smoke test** of lane 1 against the real NCBI API + Anthropic key to
prove the working lane end-to-end (not part of the unit suite).

## Runtime

uv: `uv venv && uv pip install -r requirements.txt && uv run jupyter lab search_compare.ipynb`.

## Out of scope

- Persisting/exporting comparison runs.
- A non-notebook (web) UI.
- Live Consensus/OpenEvidence calls in CI (keys are gated).
