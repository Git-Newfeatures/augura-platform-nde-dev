# DAG Generation — North Star

This document describes the intended end-to-end workflow for turning a free-text clinical question into a validated causal DAG. It is the reference for what the system should do, not what it currently does.

---

## Overview

The workflow has two clearly separated responsibilities:

1. **Semantic preparation** — parse the causal question, identify taxonomy and ontology gaps, and expand the Semantic Layer when needed
2. **DAG generation** — generate a deterministic candidate subgraph, refine it with LLM contextualization, and expose an editable causal graph

These two phases are sequential. The DAG generation button is only enabled once the semantic preparation phase confirms zero unresolved taxonomy gaps, unless the user explicitly chooses to proceed with known gaps.

---

## The Semantic Layer

DAG generation is grounded in a **Semantic Layer** made of two components. The **taxonomy** is a curated library of medical concepts — drugs, devices, conditions, measurements, procedures — each carrying synonyms for text matching, standard codes (LOINC, SNOMED, RxNorm) for interoperability, and a layer classification that distinguishes internationally standardised concepts from study-specific ones. The **causal ontology** links those concepts with directed causal relations: each relation records the predicate, polarity, strength, mechanism, supporting evidence, and optional qualifiers that restrict when the relation holds. Together they give the system a machine-readable understanding of a clinical domain that can be matched against free text, traversed as a graph, and grown over time as new questions are asked.

In Augura Platform, the Semantic Layer is stored in Supabase as a set of tables in the `public` schema, and the backend exposes it through the semantic module in `apps/api/src/augura_api/modules/semantic`. The browser loads the full Semantic Layer bundle at session startup and uses it exclusively for all concept matching, subgraph retrieval, and label resolution — no live database queries are expected during normal DAG generation.

**Any write to the Semantic Layer must be immediately followed by a full reload of the in-memory store from the database.** This is not optional. Every point in this workflow where data is written to Supabase — enrichment apply, relation deactivation, qualifier addition, DAG proposal apply — must end with a synchronous reload before control returns to the user.

The long-term authoring model is agent-assisted semantic governance. Instead of relying on manual review as the main safeguard, a semantic consistency agent evaluates proposed taxonomy and causal ontology expansions before they are applied. Its job is to prevent duplicate, overlapping, misleading, confusing, or contradictory concepts and relations while still allowing the Semantic Layer to grow as coverage gaps are discovered.

---

## Phase 1 — Parsing the causal question

### Step 1.1 — deterministic parse (instant)

The moment the user types more than 10 characters, a deterministic parser runs in the browser with no network call. It scans the in-memory taxonomy index for matching concepts and produces a structured PICOT/PECO frame: therapeutic area, population, intervention, comparator, outcomes, and time horizon. Moderators cannot be detected at this step.

This result is displayed immediately as a table below the text input, with a `✓` next to each element that matched a taxonomy concept and a `· gap` next to each one that did not. The user can read this table to audit the quality of the rule-based parse.

### Step 1.2 — Haiku improvement (automatic, 700 ms after typing stops)

A small, fast LLM model (Haiku) receives the question text and the regex result. Its job is to validate what the regex found, complete what it missed, and add moderators — effect modifiers and subgroup variables that rule-based parsing cannot infer.

When Haiku responds, the PICOT table expands to two columns: one showing the regex parse result with its taxonomy matches and gaps, one showing the Haiku result with its taxonomy matches and gaps. The user can read both columns side by side to see exactly what the deterministic parser found on its own, what Haiku corrected or added, and where each version still shows a gap. This comparison is the audit surface for understanding the limits of the rule-based approach and the value Haiku adds.

---

## Phase 2 — Semantic enrichment (resolving gaps)

If the table still shows `· gap` entries after the Haiku improvement, the user is shown a proposal panel. This panel is the gateway to fixing the ontology coverage before generating the DAG.

### Step 2.1 — Opus proposes taxonomy and causal ontology expansion

A larger, more capable LLM (Opus) receives the full list of unresolved gaps — PICOT elements that have no taxonomy concept match. For each gap, Opus proposes:

- A new taxonomy concept with the correct layer assignment:
  - Layer 1 if a recognised standard code exists (LOINC, SNOMED, RxNorm, ICD-10)
  - Layer 2 if no standard code exists, with an explanation of why
- Synonyms that will allow future questions to match this concept automatically
- The most common causal relations connecting the new concept to other existing concepts in the ontology, including any intermediate mediator concepts needed to complete the chain

The semantic layer update proposal should follow the strict semantic guidelines in `docs/specs/2026-06-25-augura-semantic-layer-v3.md`.

### Step 2.2 — Semantic consistency review

A semantic consistency agent reviews every proposed concept and relation before apply. It checks for semantic equivalence with existing taxonomy concepts, near-duplicate synonyms, conflicting definitions, inappropriate layer assignment, overlapping relation predicates, polarity contradictions, missing qualifiers, weak evidence, and violations of the semantic authoring rules.

Only proposals that pass this review are eligible to apply automatically. Flagged proposals remain visible with the reason they were blocked and can be revised or explicitly escalated.

### Step 2.3 — Semantic layer update and verification

Approved proposals are written to the database. The in-memory taxonomy and ontology indexes are reloaded from the database. The PICOT table re-runs taxonomy enrichment on the Haiku result. If every `· gap` entry has now resolved to `✓`, the table goes fully green and the "Generate Causal Model" button becomes active.

There should not be any gaps left in theory. If gaps remain after applying the first round of proposals, the system offers to repeat the cycle. There is also a "Proceed with gaps" option if the user decides the remaining gaps are acceptable.

---

## Phase 3 — Causal model generation

### Step 3.1 — Deterministic subgraph generation

The generator collects every resolved taxonomy concept from the PICOT frame and walks the causal ontology outward from those concepts, forward or backward depending on the need. It retrieves direct and second-degree relations, caps the result at a manageable size, and assembles a candidate subgraph. A deterministic cleanup step removes unsupported orphan branches that do not connect back to the exposure, comparator, mediator chain, or outcome.

### Step 3.2 — Deterministic node role classification

Before any LLM call, the generator classifies every concept in the candidate set with a structural DAG role using graph topology and the PICOT frame:

- **Exposure** — the intervention or exposure concept from the PICOT frame
- **Outcome** — the outcome concepts from the PICOT frame
- **Mediator** — concepts that lie on a directed path from the exposure toward an outcome
- **Confounder** — concepts that have causal paths into both the exposure and the outcome, but are not on the exposure-to-outcome path
- **Collider** — concepts that receive incoming edges from two or more other concepts

This classification is shown to the user as a pre-LLM structural summary, and is passed to the LLM as context. We need to make sure that the structure of what will get passed to the LLM is optimized to be best digested. The candidate DAG should be in dagitty-like JSON format.

### Step 3.3 — LLM contextualization

A large, capable LLM (Opus) takes over. The prompt is structured in two stages within the same call:

**Stage A — Independent derivation.** Opus is asked to reason through the causal question on its own, using only its medical knowledge, without seeing the subgraph. It writes out the causal chain it would expect: which variables should be on the path, which are confounders, which are mediators, and what the key mechanisms are.

**Stage B — Subgraph comparison.** Opus is then shown the deterministic subgraph alongside its own independent model. It decides, for each candidate relation:
- Keep it — it aligns with the independent model
- Exclude it — it does not fit the clinical context
- Modify it — add a qualifier to narrow its applicability

For relations that are missing from the subgraph but present in its independent model, Opus proposes new edges.

### Step 3.4 — Feedback to the semantic layer

After Opus completes its review, two categories of changes are surfaced to the semantic consistency agent:

**Excluded relations.** For each relation Opus removed from the DAG, Opus has already decided whether to:
- Propose removing the relation from the ontology entirely (it was wrong or misleading in general)
- Propose adding a qualifier (it is true in general but not applicable to this specific context)

The semantic consistency agent reviews these proposals before anything is written.

**Proposed additions.** For each new edge Opus added that was not in the candidate set, the underlying taxonomy concepts and causal relation are proposed as additions to the Semantic Layer and reviewed by the same consistency agent.

The semantic layer update proposal should follow the strict semantic guidelines in `docs/specs/2026-06-25-augura-semantic-layer-v3.md`.

Once approved changes are written to the database, the semantic layer reloads, and the final DAG is shown.

### Step 3.5 — Editable DAG

The final DAG remains editable. The user can add or remove nodes and edges, adjust DAG roles, edit labels, and attach qualifiers or notes. Edits that only affect the working DAG stay local to the model. Edits that imply a reusable taxonomy concept or causal ontology relation are routed back through the semantic expansion and consistency-review flow before they can become part of the Semantic Layer.

---

## What the DAG represents at the end

Every node in the DAG has a role: exposure, outcome, mediator, confounder, collider. Edges carry their predicate, polarity, strength, mechanism summary, and evidence citations. Nodes whose concepts resolved from the taxonomy carry the `✓` mark. Nodes that were LLM-proposed carry a `proposed` badge.

The quality score at the top reflects whether the exposure and outcome are both present, whether confounders were identified, and what fraction of edges came from the curated ontology versus LLM proposals.

Proper graphic representations rules are used for DAG clarity.
