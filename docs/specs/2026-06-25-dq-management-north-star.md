# Data Quality Management — North Star

This document describes the intended end-to-end workflow for turning a submitted dataset into an auditable, explainable set of data-quality findings. It is the reference for what the system should do, not what it currently does. Structural detail — how the taxonomy, unit and range profiles, archetypes, and DQ constraints are modelled — lives in `docs/specs/2026-06-25-augura-semantic-layer-v3.md`; this North Star describes how that information is leveraged.

---

## Overview

The workflow has four clearly separated responsibilities:

1. **Mapping** — identify what each column means, what dimensions modify it, and what each table and row represent
2. **Planning and checking** — let declarative constraints select which checks apply, then run them deterministically at every level of the data
3. **Remediation** — resolve what can be resolved deterministically, suggest a fix where the answer depends on context, and escalate the critical decisions to a human assisted by an agent
4. **The clean dataset and the bundle** — produce a traceable cleaned dataset alongside evidence-backed findings, scores, and an auditable record, sealed into a reviewable bundle

These phases are sequential: checking is only meaningful once mapping has established what the data is, a finding is only trustworthy once it carries the evidence that produced it, and a fix is only acceptable once it is recorded against the finding it resolves.

The guiding stance throughout is **declare first, execute second**: reviewed semantic artifacts decide *what* should be true, deterministic code decides *whether* it is, and contextual reasoning (an LLM) is used only to resolve genuine ambiguity — never to declare a defect or finalize policy on its own. Given the same data and the same semantic release, the result should be reproducible.

---

## The Semantic Layer

Data quality is grounded in the same **Semantic Layer** that powers causal modeling. The taxonomy gives each source element a stable identity across three roles: **structural** concepts that describe what a column does in the shape of a dataset (identifiers, timestamps, value/unit/code columns), **standard clinical** concepts that carry recognised medical meaning and standard codes, and **Augura-specific** extensions for device, digital-health, or derived concepts that no standard concept captures.

Each concept carries the intrinsic quality metadata the engine relies on — expected units, plausible ranges, valid value sets, and the structural roles and table archetypes that describe how rows are shaped. The DQ engine **consumes** this metadata; it does not define it. Quality policy itself is expressed as a separate, **constraint-based** DQ contract: reusable constraints that reference concepts, roles, or archetypes, each bound to one deterministic check. A causal relation may motivate a quality concern, but it is never used directly as a validation rule.

---

## Phase 1 — Mapping the dataset

Quality begins with mapping, because every later check depends on correctly identifying what each column means, which table it belongs to, and what one row represents.

### Step 1.1 — Deterministic identification

The engine first normalises each column label, expands abbreviations, and matches against governed synonyms, using observed data profiles (type, distribution, missingness) as corroborating evidence. Where exact synonyms fall short, a semantic-similarity pass connects source labels to the closest concepts and produces ranked candidates with explicit confidence. This stage is fully deterministic and reproducible.

### Step 1.2 — Affixes become dimensions, not new concepts

`HbA1c`, `HbA1c_baseline`, and `HbA1c_6months` are the **same** clinical concept, distinguished only by a temporality dimension. The engine carves recognised prefixes and suffixes off the label so the residual maps to a single base concept and the affix is recorded as a **dimension** on the mapping.

This matters because it keeps unit, range, and vocabulary policy defined **once** on the base concept and reused across every variant — the platform must never mint a new taxonomy concept per concept-and-context combination. Temporality is the first such dimension; the model anticipates others: relative-to-event timing (pre-/post-operative, pre-/post-dose), laterality, method or assay, specimen, body position, derived statistic, rater, and more. The affix grammar is governed declaratively, not hard-coded per concept.

Affix recognition is governed and evidence-ranked, exactly like grain: a decomposition is accepted only when the residual maps to a known concept and sibling columns share the pattern, with an LLM consulted only for unfamiliar affixes. And a modifier is treated as a dimension only while it keeps values **comparable** along that axis (timepoints, sides); when it changes *what is actually measured* — a different specimen or assay whose values are not interchangeable — it forks into a distinct concept instead. The full catalogue of dimension kinds and the recognition rules live in the semantic layer (`…augura-semantic-layer-v3.md`, §2.7).

### Step 1.3 — Reconciling affixes with table grain

The same fact can be encoded two ways. A **wide** table carries the timepoint in the column name (`HbA1c_6months`, `HbA1c_12months`); a **long** table carries it as a value in a time column with one row per measurement. These are semantically equivalent — the difference is the table's grain. Mapping must therefore recognise the table format and reconcile the affix-derived dimension with the grain-derived one to the same underlying statement, so that grain, duplicate detection, and longitudinal checks behave correctly regardless of layout.

### Step 1.4 — Contextual finalization (advisory)

A bounded LLM may review the deterministic candidates, the column profiles, and the study context to propose resolutions for genuine ambiguity — an uncertain mapping, an unfamiliar affix, a contested archetype. Its proposals are **advisory**: deterministic candidates and their confidence are preserved, low-confidence mappings are surfaced for human review, and nothing is silently overridden.

---

## Phase 2 — Planning and running the checks

Once mapping resolves a column's base concept, its dimensions, its structural role, and its table grain, the dataset is ready to be checked.

### Step 2.1 — A visible check plan

Declarative constraints select which checks apply, based on the mapped concepts, structural roles, inferred grain, and cross-table relationships. Before anything runs, the engine assembles an inspectable plan that states which checks were selected, why each one applies, what it requires, and which prerequisites are satisfied or missing. The plan makes DQ behavior predictable and reviewable *before* findings exist. No check ever runs without an explicit implementation behind it.

### Step 2.2 — Deterministic execution at every level

Programmed functions profile the data and execute the selected checks across the levels at which quality can fail:

- **Within a column** — type integrity, missingness, unit evidence, and value-range plausibility, drawing on the concept's intrinsic unit and range metadata. Range checks are suppressed when unit evidence is missing or ambiguous, rather than guessing.
- **Across columns in a row** — internal consistency, temporal order, and unit-value agreement.
- **Within a table** — grain and candidate keys, duplicate records, and the longitudinal trajectory of a concept across its dimension variants.
- **Across tables** — foreign-key integrity, person/table alignment, and cross-table coherence.

Which constraints apply depends on *what the element is*: a structural role enables grain, key, and integrity checks; a clinical concept enables unit, range, and vocabulary checks; a dimension enables cross-variant coherence.

### Step 2.3 — Record what was not checked

When a unit is unknown, a concept is unsupported, a grain is unresolved, or a planned check could not run, that is itself a finding — surfaced with its reason, never silently dropped. Semantic uncertainty (unmapped or low-confidence columns) is reported as a quality concern in its own right.

---

## Phase 3 — Remediation

Identifying a problem is the first principle; deciding what to do about it is the second. The engine does not treat every finding the same way — it triages each one by how unambiguous the fix is and how critical the issue is to the analysis, and routes it to one of three handling tiers. Across all three, the source data is never silently altered: every change is recorded against the finding it resolves.

### Step 3.1 — Deterministic correction (applied and tracked)

Some errors have a single, unambiguous, reproducible fix — normalising a recognised unit to its canonical form, standardising a date format, stripping a known sentinel, resolving a coded value through a governed vocabulary. These are corrected automatically. The original value is preserved, and the correction, the rule behind it, and its rationale are recorded so the change is fully auditable and reversible. No human decision is required, but nothing is silent.

### Step 3.2 — Suggested correction (context- and volume-dependent)

Other errors have no single right answer — the appropriate fix depends on the clinical context, the volume affected, or the intended analysis. Here the engine does not act on its own. It produces a **suggestion** with its reasoning and trade-offs and leaves the decision pending for review. It never forces a choice it cannot justify deterministically.

### Step 3.3 — Critical decisions with a human in the loop

The most critical issues — high severity, high affected volume, or material analytical consequence — are prioritised and presented to the user for an explicit decision. To assist, a **data-quality management agent** proposes the most appropriate fix for each one, grounded in the specific context of the finding: the concept, its dimensions, the table grain, and the downstream analysis.

Crucially, the user is not limited to accepting or rejecting. They can **challenge the agent's suggestion and converse with it** — questioning its rationale, supplying context it lacked, or asking for a different approach — and arrive together at the remediation that is actually applied. The agent assists the decision; it never makes it unilaterally, and every accepted fix is recorded with who decided it and why.

---

## Phase 4 — The clean dataset, findings, and the bundle

Remediation yields two linked outputs from the original submission: a **clean version of the dataset** and the **findings** that explain it. The clean dataset is never a silent rewrite of the source — every value it changes traces back through the deterministic correction, accepted suggestion, or human decision that produced it, and the original is preserved alongside.

Every material finding links back to the input data, the rule that triggered it, and the evidence that produced it, and carries its severity, the count and proportion of records affected, the remediation applied (if any), and — crucially — its **analytical consequence**: whether it affects inclusion in the analysis, whether it needs review, whether it can be waived, and whether it should be surfaced in publication statements.

This lets a finding tell a clear story, for example:

> HbA1c unit information was missing for 12% of records, so unit-dependent range validation could not be performed.

> Three percent of biomarker records did not resolve to a patient and were excluded from the analysis population.

Findings roll up into dimension scores (completeness, validity, consistency, coherence, labelling, and an overall score), weighted differently for exploratory versus regulatory contexts. The plan, the findings, the scores, the full remediation log, the provenance, and the source fingerprint — together with the cleaned dataset — are sealed into a single versioned, tenant-scoped **DQ bundle** that can be reviewed, dispositioned (resolved or waived, with reason), and exported.

---

## What the DQ bundle represents at the end

The bundle is the auditable record of what the data was and what was done with it. Every finding names the data it concerns, the rule it came from, and the evidence behind it; every check that was skipped explains why; every concept whose quality could not be assessed says so; and every correction — automatic, suggested, or human-decided — is recorded against the finding it resolves, so the cleaned dataset can be reconstructed from the source and its remediation log. The scores summarise the dataset without discarding the detail beneath them, and the provenance log preserves enough to reconstruct, later, how and why each issue was handled.

The aim is a system where data-quality findings are not mysterious outputs but explained, reviewable inputs to every analysis that follows.
