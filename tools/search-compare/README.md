# search-compare

An interactive Jupyter notebook that runs one clinical question through **three literature-search
lanes** and renders a side-by-side comparison table of their answers and sources.

| Lane | What it does | Works out of the box? |
|------|--------------|------------------------|
| **PubMed (LLM-curated)** | Claude turns your question into a curated PubMed/Entrez query, runs NCBI E-utilities, then synthesizes a grounded answer citing `[PMID:…]`. | ✅ Yes — needs only `ANTHROPIC_API_KEY` (PubMed itself needs no key). |
| **Consensus** | Calls the Consensus `/v1/quick_search` API for ranked papers, then Claude synthesizes an answer from them. | 🔒 Needs `CONSENSUS_API_KEY` (access is application-gated). |
| **OpenEvidence** | Configurable adapter for OpenEvidence's enterprise API. | 🔒 Needs enterprise access + BAA. |

A lane that isn't configured shows a `not_configured` row explaining how to enable it —
it never fabricates an answer.

## Setup (uv)

```bash
cd tools/search-compare
uv venv
uv pip install -r requirements.txt

cp .env.example .env      # then fill in at least ANTHROPIC_API_KEY
uv run jupyter lab search_compare.ipynb
```

Run **Cell → Run All**, type a clinical question, and click **Run comparison**.

> No `.env`? You can also export the keys in your shell. The PubMed lane just needs
> `ANTHROPIC_API_KEY`.

## Running the tests

```bash
cd tools/search-compare
uv run pytest -q
```

The suite is fully mocked (no network, no API keys required).

## Enabling the gated lanes

### Consensus
1. Apply for API access at <https://consensus.app/home/api/>.
2. Put the issued key in `.env` as `CONSENSUS_API_KEY`.
3. The lane calls `GET https://api.consensus.app/v1/quick_search` with header `x-api-key`.
   That API returns ranked papers (not a written answer), so the answer cell is synthesized
   by Claude from those papers and labeled accordingly.

### OpenEvidence
OpenEvidence has **no public/self-serve API** — access requires an enterprise agreement and
a signed BAA (contact <sales@openevidence.com> / <https://www.openevidence.com/product/api>).
Its request/response schema is not officially published, so the adapter is fully
configurable via env vars (see `.env.example`):

- `OPENEVIDENCE_API_BASE`, `OPENEVIDENCE_API_KEY`, `OPENEVIDENCE_ORG_ID`
- `OPENEVIDENCE_SEARCH_PATH` (default `/analysis` — **unverified, confirm it**)
- `OPENEVIDENCE_ANSWER_FIELD` (default `answer`), `OPENEVIDENCE_SOURCES_FIELD` (default `references`)

Set these to match the real spec you receive. Until `BASE` + `KEY` are both set, the lane
stays disabled.

## Files

| File | Role |
|------|------|
| `search_lanes.py` | The engine — pure Python, no UI, fully testable. |
| `test_search_lanes.py` | Unit tests (mocked, no network). |
| `search_compare.ipynb` | The interactive notebook UI. |
| `.env.example` | All key/endpoint slots. |

## Notes

- Lanes run **concurrently**; one slow or failing lane never blocks the others.
- NCBI rate limits are respected (3 req/s without a key, 10 with one). Add `NCBI_API_KEY`
  + `NCBI_EMAIL` to `.env` for the higher limit.
- The LLM is told to answer **only** from retrieved sources and not to invent citations.
