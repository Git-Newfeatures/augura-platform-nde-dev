# North Star — Semantic Layer Expansion (dataset-driven)

**Date:** 2026-06-26
**Status:** North star (intent, not implementation)
**Related:** `docs/specs/2026-06-26-semantic-admin-north-star.md` (the read-only *viewer*; this doc is the
*grow* side), `docs/specs/2026-06-25-augura-semantic-layer-v3.md`,
`docs/specs/2026-06-25-dq-management-north-star.md`,
`docs/specs/2026-06-25-dag-generation-north-star.md`

---

## 1. What it is

A **staged way to grow the governed semantic layer from a real dataset.** Point the process at a
dataset, compare it against what the platform already knows, and surface what is *missing* — new
concepts, synonyms, affix matches, then causal links, then data-quality rules — as a reviewable
proposal that lands through the existing governed release path.

It answers: **"given this dataset, what should the semantic layer learn next?"**

This is the complement to the Semantic Admin tool: that one *reads* the layer, this one *expands* it.

## 2. Principles

- **Dataset-driven.** Every expansion starts from a concrete dataset (columns, sample values, and a
  data dictionary when available), not from abstract curation.
- **LLM one-shot is acceptable now.** The taxonomy-mapping functionality is not yet stabilized, so for
  this work we deliberately use a one-shot LLM pass (dataset + current taxonomy → proposal) rather than
  depend on mapping. Mapping is a *future drop-in* at the same seam.
- **Web-grounded enrichment is a quality lever, not a convenience.** Claude Code runs Opus 4.8 with a
  built-in agentic web-search/web-fetch loop (multi-round search → fetch → cross-check → synthesize).
  That grounds enrichment in real sources — clinical terminology and standard codes (Stage 1),
  literature/citations for causal evidence (Stage 2), published reference ranges/value sets (Stage 3) —
  instead of model-invented facts. A bare backend call has *no* web access until that whole agentic
  loop is rebuilt server-side; the Messages API exposes `web_search`/`web_fetch` only as raw primitives.
  This tilts the strategy toward the Claude-Code-driven options and makes the productized endpoint
  (Option C) more expensive than it first appears.
- **Human-in-the-loop.** The process *proposes*; a reviewer approves. Nothing auto-writes the governed
  layer.
- **One governed write path.** Approved proposals land through the existing release mechanism
  (`upsert_semantic_release` / the `semantic` schema per the consolidation plan), never via side doors.
- **Reusable pieces accrete.** Favour an approach where the deterministic, reusable parts (taxonomy
  dump, proposal schema, affix matcher) harden over time into the building blocks of a future backend
  capability — without a rewrite.

## 3. The stages

Sequential; each builds on the prior and reuses the same dump → propose → review → apply spine.

### 3.1 Stage 1 — Taxonomy concepts (+ affix recognition)
Grow the vocabulary itself.
- Propose **new concepts** (with domain, value type, unit, range) and **synonyms** for dataset columns
  that don't map to an existing concept.
- **Affix recognition:** decompose column names against the dimension grammar
  (`affix_archetypes` + `affix_archetype_aliases`) — recognise prefixes/suffixes (laterality, timing,
  method, …), match known tokens, and flag residual/unknown tokens for review.

### 3.2 Stage 2 — Causal taxonomy enrichment
Once the concepts exist, propose **directed relations** between them
(`ontology_relations`: subject → predicate → object, polarity, strength), each with a **mechanism
summary** and candidate **evidence**, for review against the causal ontology.

### 3.3 Stage 3 — Data-quality taxonomy enrichment
Propose the rules that qualify the new concepts: **valid value sets / ranges**
(`taxonomy_dq_valid_values`), **constraints** (`dq_constraints` + bound `dq_predicates`), and
**table-archetype** fit — so the DQ engine can police the newly-learned data.

## 4. The shared spine

```
dataset  →  dump current taxonomy  →  LLM proposes (per stage)  →  reviewer approves  →  governed release
```

Every stage reuses the same four moves; only the *target tables* and the *prompt* change per stage.

## 5. Strategy (to be selected)

The implementation approach is a deliberate trade-off between simplicity, leaning on Claude Code for
the compute, and reusability. Four options were brainstormed (2026-06-26):

- **A — Claude Code as ad-hoc analyst** (max simplicity, zero reuse).
- **B — reusable Claude Code script / skill** (one-shot, rerunnable dev tool).
- **C — backend enrichment endpoint** (productized, governed, heaviest now — and to match Claude Code's
  enrichment quality it must *also* rebuild the agentic web-search loop server-side, not just call the LLM).
- **D — hybrid: Claude Code drives now, reusable pieces (taxonomy dump, proposal schema, affix matcher)
  accrete toward C.** ← *leaning recommendation.*

> **Web-search consideration (2026-06-26):** A key differentiator surfaced — Claude Code (Opus 4.8) has a
> built-in agentic web-search loop that grounds enrichment in real sources; a bare API endpoint has none
> until that loop is rebuilt. This argues for staying in Claude Code (A/B/D) longer and, if C is ever
> built, requiring it to declare `web_search`/`web_fetch` and run its own agentic loop so the productized
> version isn't *weaker* at enrichment than the Claude Code version it replaces.

> **Decision:** _pending._ Default lean: start at **A** for the first dataset to calibrate the proposal
> format, then adopt **D**'s three reusable pieces. Mapping plugs in later at the proposal seam.

## 6. Out of scope (for now)

- Depending on the (not-yet-stabilized) taxonomy-mapping functionality.
- Auto-applying proposals without human review.
- A dedicated UI (the early stages are Claude Code / script-driven; a panel comes only if Stage→C lands).
- Versioning/release mechanics beyond the existing governed write path.

## 7. Success looks like

A user points the process at a new dataset and gets, stage by stage, a clean reviewable proposal: the
concepts and affixes it should add, then the causal links between them, then the DQ rules that qualify
them — each approvable into the governed layer with no hand-written SQL, and each rerun consistent with
the last.
