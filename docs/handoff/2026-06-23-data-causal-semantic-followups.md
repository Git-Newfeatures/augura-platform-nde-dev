# Handoff — Data intake, Semantic layer & Causal modeling follow-ups

**Date:** 2026-06-23
**Branch:** `Quentin`
**Author:** Quentin (review feedback) → triaged by Claude
**For:** Ziad (owner of the data-intake / causal work)

This captures review feedback on three workspace areas. The **bugs + quick wins are
already done on `Quentin`** (see the first section). The rest is **deferred to you** — it
overlaps with your data-intake / causal expertise and isn't a showstopper for pushing to
Dev. Each deferred item has file/line anchors so you can pick it up without re-deriving
context.

---

## ✅ Already done on `Quentin` (this pass)

| Item | Change | Where |
|---|---|---|
| "Failed to fetch" on Add/Remove files | Root-caused + defense-in-depth handler added (details below) | `apps/api/src/augura_api/core/errors.py` |
| Beta tag — Data Quality tab | `badge: 'beta'` added | [DatasetsPage.jsx:572](../../apps/web/src/workspace/DatasetsPage.jsx) |
| Beta tags — Semantic Enrichment + Versions | `badge: 'beta'` added | [SemanticLayerPage.jsx:634-635](../../apps/web/src/workspace/SemanticLayerPage.jsx) |
| Causal — clinical question required | Removed "(optional)", button now gated on the question, not the dataset | [CausalModelingPage.jsx](../../apps/web/src/workspace/CausalModelingPage.jsx) |
| Causal — dataset no longer mandatory | `generate()` skips the `/datasets/{id}/map` step when no dataset is linked; sends `mapped_concepts: []` | [CausalModelingPage.jsx](../../apps/web/src/workspace/CausalModelingPage.jsx) |

### ⚠️ Still required to actually fix Add/Remove in prod (NOT a code change)

The "Failed to fetch" is a **prod-only storage misconfiguration**, not application logic:

- `add_files` / `remove_file` call `_reprofile`, which re-reads **every** existing file via
  `core.storage.read_bytes` ([service.py `_reprofile`](../../apps/api/src/augura_api/modules/datasets/service.py)).
- In prod, `AUGURA_SUPABASE_URL` / `AUGURA_SUPABASE_SERVICE_ROLE_KEY` are **not set** in
  `apps/api/.env` (and `deploy_modal.sh` builds the Modal secret from that file), so
  `core.storage` falls back to **local disk**, which on Modal is **ephemeral and
  per-container**. A file written by one container isn't found by the container that
  reprofiles → `FileNotFoundError`.
- That error had no handler, so it propagated **above** the CORS middleware →
  `ServerErrorMiddleware` emitted a header-less 500 → the browser blocks it and reports
  **"Failed to fetch"** (no message). `upload` works because it only profiles the file it
  just wrote in the same container; the column GETs work because they read the DB, not files.

**Fix (deploy step, needs the service_role secret + an explicit deploy):**
1. Set in `apps/api/.env` (documented now in `.env.example`):
   ```
   AUGURA_SUPABASE_URL=https://fqmoylmvjoafihiuiiuj.supabase.co
   AUGURA_SUPABASE_SERVICE_ROLE_KEY=<service_role secret>
   AUGURA_STORAGE_BUCKET=datasets
   ```
2. Redeploy Modal (`bash apps/api/scripts/deploy_modal.sh` recreates the `augura-api`
   secret from `.env`). The `datasets` bucket is already provisioned.
3. Note: datasets uploaded under the disk backend have file bytes on dead containers —
   those are unrecoverable; only **new** uploads land in Supabase Storage.

The code-side **defense-in-depth** fix (already merged) maps `OSError`/`FileNotFoundError`
to a CORS-bearing problem+json 500, so any future storage issue surfaces a real error
message instead of an opaque "Failed to fetch". Test:
`tests/core/test_errors.py::test_storage_error_renders_problem_details_with_cors`.

---

## 🟡 Deferred — medium frontend restructures

### 1. Datasets: per-file table preview (data-model view), not a flat column union
- **Current:** `ColumnsTable` renders one flat union of all columns across all files,
  grouped only by a `sheet` field ([DatasetsPage.jsx ColumnsTable ~275-314](../../apps/web/src/workspace/DatasetsPage.jsx)).
- **Wanted:** tabs (one per uploaded file) each showing that file's table structure, so the
  reviewer can read the data model per table rather than a merged column list.
- Backend already returns per-column `sheet`/source via `ColumnOut`; the data to split by
  file is present.

### 2. Datasets: mapping by table, not a flat attribute list
- **Current:** `MappingPanel` lists every source column in one flat table
  ([DatasetsPage.jsx MappingPanel ~336-404](../../apps/web/src/workspace/DatasetsPage.jsx)).
- **Wanted:** group the mapping rows by table/file, mirroring item 1.

### 3. Remove the "Local suggestions (offline)" block from the mapping view
- It is [LocalMappingSuggestions.jsx](../../apps/web/src/workspace/LocalMappingSuggestions.jsx)
  — a **client-side IndexedDB** semantic matcher (offline fallback) that duplicates the
  server-side mapping and confused the reviewer ("not sure what this is about").
- Rendered at [DatasetsPage.jsx:630](../../apps/web/src/workspace/DatasetsPage.jsx).
- Recommendation: remove it from this view (or gate it behind an explicit "offline mode").

### 4. Causal: two-tab restructure + DAG display
- **Wanted layout:** two tabs —
  - **Causal question**: enter the clinical question (+ the question-parsing UI, item 6).
  - **DAG**: generate/display the DAG (and **link a dataset here**, not on the first page —
    the dataset selector should not appear before the DAG tab).
- The page is currently single-Card, non-tabbed ([CausalModelingPage.jsx ~419-461](../../apps/web/src/workspace/CausalModelingPage.jsx)).
  The quick-win pass made the dataset optional but left the selector on the first card —
  moving it into the DAG tab is part of this restructure.
- **DAG text not fully displayed:** `DagSvg` hard-truncates node labels to 19 chars +
  ellipsis ([CausalModelingPage.jsx:133](../../apps/web/src/workspace/CausalModelingPage.jsx))
  and the viewBox can clip longer labels. Needs proper text layout (wrap/measure, tooltips,
  or a larger/auto-fit viewBox).

---

## 🟠 Deferred — larger net-new features

### 5. Data-dictionary parsing + data-model representation (LLM fallback for free-form)
- The reviewer notes the **"data intake NDE" branch** parses data dictionaries and renders
  the associated data model, using an **LLM call when the dictionary is free-form**.
- That work lives on branch **`feat/causal-intake-dag`** (not on `Quentin`):
  `apps/web/src/semantic/picot-parser.js`, `apps/web/src/utils/csv-parser.js`, and an
  enhanced datasets module.
- Task: port/build into the current datasets module — a backend parse path (structured +
  LLM-assisted free-form) plus the frontend data-model representation (ties into item 1).

### 6. Surface the clinical-question parsing in the Causal-question tab
- The parser **already exists**: `parsePICOT()` in
  [picot-parser.js](../../apps/web/src/semantic/picot-parser.js), already imported and used
  in `generate()` to enrich the B2 prompt — but **invisibly** (no UI), which is why the
  reviewer reported it "completely missing".
- Task: render the extracted PICO(T) elements (population / intervention / comparator /
  outcomes / timeframe) as an editable, visible step in the Causal-question tab before
  generating the DAG. Consider promoting parsing to a backend endpoint if it needs the
  taxonomy/ontology server-side.

---

## Pointers
- Frontend nav source of truth: `apps/web/src/shell/sections.js`.
- Reusable Beta badge pattern: `badge: '<text>'` on a `SubTabs` tab
  ([SubTabs.jsx:25-34](../../apps/web/src/cockpit/SubTabs.jsx)).
- Causal backend: `POST /causal/dag` already accepts an empty `mapped_concepts` and a null
  `picot` — no dataset is required server-side
  ([causal/schemas.py CausalDagRequest](../../apps/api/src/augura_api/modules/causal/schemas.py)).
