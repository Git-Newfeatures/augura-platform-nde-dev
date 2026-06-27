# North Star — Semantic Admin tool

**Date:** 2026-06-26
**Status:** North star (intent, not implementation)
**Related:** `docs/specs/2026-06-25-augura-semantic-layer-v3.md`,
`docs/specs/2026-06-25-dq-management-north-star.md`,
`docs/plans/2026-06-26-semantic-admin-affix-dq-views-plan.md`

---

## 1. What it is

A **single read-only window onto the governed semantic layer** — the declarative content of the
`semantic` schema in Supabase. One workspace (`/semantic`) where a user can *see, audit, and
understand* the concepts that drive the platform, the relationships between them, and the rules that
qualify them. It does not author or mutate anything; enrichment/authoring stays elsewhere.

It answers one question: **"what does the platform currently believe, and why?"**

## 2. Principles

- **Read-only.** Inspect and audit, never edit. (Consistent with the existing Taxonomy/Causal tabs.)
- **One source of truth.** A view onto the `semantic` schema — everything shown is real, governed data.
- **The UI mirrors the data model.** Navigation *is* the schema's shape: a concept opens to its
  synonyms, codes, and relations; a relation opens to its evidence and qualifiers; an archetype opens
  to its values and aliases. Drilling down teaches the model.
- **Progressive disclosure.** Top-level tabs for the big domains → row tables → detail modal →
  sub-tabs inside the modal for the linked sub-entities. The user never sees raw joins, but the joins
  are walkable.

## 3. The three domains (top-level tabs)

### 3.1 Taxonomy — *what the concepts are*
The vocabulary: concepts and everything attached to them.
- Browse/filter concepts; open one to audit its **synonyms** (synonym → value → concept linkage),
  **standard codes**, **therapeutic areas**, and **measurement units / conversions**.
- Surface the quality-relevant attributes a concept carries: **unit**, **valid range / value sets**,
  expected type — the inputs DQ checks rely on.

### 3.2 Causal ontology — *how concepts relate*
The directed relationships between concepts.
- Browse relations (predicate, subject → object); open one to audit its **evidence** and
  **qualifiers** — *why* the relationship is asserted and under what conditions it holds.

### 3.3 Data quality — *what makes a value valid*
The governance rules that constrain the data.
- **Constraints** (`dq_constraints`) and the **predicates** they bind, with scope and severity.
- **Valid value sets** and **ranges** per concept (`taxonomy_dq_valid_values`).
- **Table archetypes** — the shapes/roles a dataset table can take, with their key selectors and
  semantic score, so the user can see *what an archetype is* and what it expects.

## 4. The cross-cutting layer — Dimensions & affixes
The dimension grammar (`dimension_kinds`, `affix_archetypes`, values, aliases) that explains how
concepts are decomposed and labelled. An archetype opens to its **canonical values** and the **token
aliases/synonyms** that map onto them — the same drill-down pattern, applied to the grammar itself.

## 5. The interaction model (the spine of the UX)

```
Tab (domain)  →  filterable table of rows  →  detail modal  →  sub-tabs (linked sub-entities)
   Taxonomy           concepts                 a concept        Synonyms · Codes · Relations · Units
   Causal             relations                a relation       Evidence · Qualifiers
   Data quality       constraints / archetypes a constraint     Predicate · Scope · Valid values
   Dimensions         archetypes               an archetype     Values · Aliases
```

Each downward step is a real foreign-key edge in `semantic`. The chain
**synonym → value → concept → relation → constraint** is the thing the tool makes legible: every
pop-up and sub-tab exists to render one hop of that chain.

## 6. Out of scope (for now)

- Editing, proposing, or approving changes (authoring/enrichment lives outside this tool).
- Anything that writes to `semantic` or `public`.
- Versioning/release management beyond *viewing* the current release.

## 7. Success looks like

A reviewer opens `/semantic`, picks any concept, and can trace — without leaving the page — its
synonyms, its codes, the relationships it participates in (with the evidence behind them), the units
and ranges that qualify it, the constraints that police it, and the archetype it belongs to. They
finish understanding both *the data* and *the data model* underneath it.
