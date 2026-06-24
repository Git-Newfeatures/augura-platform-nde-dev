# ENG-187 — DAG Generation North Star: implementation plan

**Spec:** ENG-187 "DAG Generation — North Star" (pasted 2026-06-23).
**Status:** plan / gap analysis. The current causal + semantic stack already provides most of
the hard machinery; this is mostly **wiring + targeted additions**, decomposed into 3 shippable
increments.

> ⚠️ The spec references `docs/260609_semantic-layer-v3.md` for the semantic write guidelines —
> **that file does not exist in this repo.** The equivalent rules are currently embedded in
> `modules/semantic/enrich_propose.py` (system prompt) + `modules/semantic/vocab.py` (governed
> enums: layer, polarity, predicates, qualifier types, ID formats). Plan reuses those unless the
> v3 doc is provided.

---

## What already exists (reuse, don't rebuild)

**Phase 1 (parsing)** — `apps/web/src/semantic/picot-parser.js` `parsePICOT()` returns a PICOT frame
and matches taxonomy concepts via the in-memory store (`lib/semantic-store.js`). Surfaced in
`CausalModelingPage.jsx` (`PicotView` + "Parse question"). Models configured:
`agent_model_fast=claude-haiku-4-5`, `agent_model_dag=claude-sonnet-4-6`, `agent_model_deep=claude-opus-4-8`.

**Phase 2 (enrichment)** — ~80% built (B4):
- `POST /semantic/enrich/propose` (LLM proposes concepts+relations for gaps, background job)
- `GET /semantic/enrich/proposals/{job_id}`
- `POST /semantic/enrich/apply` — 4 paths incl. **`deactivate_relation`** and **`add_qualifier`**
- `EnrichmentPanel.jsx` — review-with-checkboxes UI + `resetSemanticStore()`+`initSemanticStore()` reload
- Layer 1/2 assignment + `vocab.py` governance + `apply_prechecks()`

**Phase 3 (generation)** — `modules/causal/`:
- `subgraph.py` — 2-hop bidirectional BFS, 40-relation cap (`causal_subgraph`, `cap_candidates`)
- `service.py` + `prompt.py` — single LLM call (`agent_model_dag`/Sonnet) with `filter_dag_relations`
  tool → selects/excludes relations, assigns roles, proposes concepts+relations
- `builder.py` — assembles `DagNode`/`DagEdge` (roles, polarity, strength, mechanism, evidence,
  `observed`, `source`, `adjusted`), quality score; `ProposedEdges` UI accepts proposals →
  `/semantic/enrich/apply` (direct_relations) → store reload

---

## Gaps vs North Star → 3 increments

### Increment A — Phase 1: regex + Haiku parse, side-by-side, ✓/gap markers
Backend
- New `POST /causal/parse-question` (or `/semantic/parse`): Haiku (`agent_model_fast`) structured
  call → PICOT frame **+ moderators**. Reuse `run_structured_agent`. Returns the same shape as the
  regex parser so the two can be compared.
Frontend (`CausalModelingPage.jsx`, Causal-question tab)
- Run regex parse **instantly** on >10 chars (already instant); debounce a Haiku call **700 ms**
  after typing stops.
- Per PICOT element, compute taxonomy match → `✓` vs `· gap` (extend `picot-parser.js` to mark
  matched-concept vs gap for **every** element, not just outcomes).
- Render **two columns** (regex | Haiku), each with its ✓/gap, as the audit surface.
Verify: lint+build; unit-test the parser gap-marking; manual two-column render.

### Increment B — Phase 2: gap-gated enrichment wired into the question tab
- Detect remaining `· gap` entries after the Haiku pass.
- Surface an inline proposal panel in the Causal-question tab that **reuses the existing
  `enrichPropose`/`enrichApply` flow** (Opus proposals → review checkboxes → apply → store reload).
- After apply, **re-run taxonomy enrichment** on the parse; when zero gaps → enable
  "Generate Causal Model". Add a **"Proceed with gaps"** escape hatch. Loop if gaps remain.
- Mostly reuses `EnrichmentPanel` logic; main work is embedding it in the causal flow + the gating
  state machine.

### Increment C — Phase 3: deterministic roles, two-stage Opus, feedback loop, covariates
Backend (`modules/causal/`)
- `subgraph.py`: add **orphan-branch pruning** (drop relations that don't connect through to an
  outcome).
- New `roles.py`: **deterministic topology role classification** (exposure/outcome from PICOT;
  mediator = on a directed exposure→outcome path; confounder = parent of both, off the path;
  collider = ≥2 incoming). Pass as a **dagitty-style JSON** candidate graph to the LLM; show as a
  pre-LLM structural summary.
- `service.py`/`prompt.py`: **two-stage** prompt in one call — Stage A independent derivation,
  Stage B compare-to-subgraph (keep/exclude/modify + propose). Switch contextualization to
  `agent_model_deep` (Opus).
- **Feedback loop:** surface excluded relations as **remove-vs-qualifier** proposals (reuse
  `enrich/apply` `deactivate_relation` + `add_qualifier` paths — already exist), and proposed
  additions for review; write + reload.
- **Covariates:** when a dataset is linked, mark DagNodes **measured** (concept in the dataset
  mapping → `observed=true`) vs **unmeasured** (in ontology/DAG but not in data). `DagNode.observed`
  + `source` already exist; wire from `mapped_concepts`.
Frontend
- Pre-LLM role summary; node ✓ (taxonomy) / `proposed` badges; measured/unmeasured styling;
  excluded/added review panels; quality score (already present).

---

## Open questions (need answers before/within build)
1. Provide `docs/260609_semantic-layer-v3.md`, or confirm we follow `vocab.py` + `enrich_propose` rules.
2. Phase-2 enrichment is **owner-gated** (`require_role("owner")`). Should the causal-question
   enrichment be owner-only too, or available to all members?
3. Two-stage Opus per generation ≈ higher latency/cost — acceptable, or gate behind a toggle?
4. Editable DAG ("ultimately will be editable") is out of scope for v0.1 here — confirm.

## Recommended sequencing
A (foundation, extends what just shipped) → B (reuses enrichment) → C (largest; core causal).
Each increment is independently shippable and verifiable. This is Ziad's domain — the plan is
written so he can take any increment cold.
