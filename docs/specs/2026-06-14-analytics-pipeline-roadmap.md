# Augura Analytics Pipeline — implementation plan mapped to the code

**Status:** work plan — 2026-06-14. Translates the "Augura Analytics
Pipeline/Roadmap (June 2026)" draft into concrete, sequenced workstreams, anchored in the
existing code (`augura-platform`). Settled decisions: **Phase 6 engine in Python** (not R),
**plan first** (this document) before any build.

Refs: product spec (draft provided); backend architecture
[2026-06-11](2026-06-11-augura-backend-architecture-design.md);
delivery [2026-06-13](2026-06-13-delivery-design.md).

---

## 1. North star (the 3 properties) — and how we hold them in Python

The spec imposes three properties on **every** phase:

- **Functional** — each phase produces an artifact consumable by the next one + a
  concrete acceptance criterion.
- **Auditable** — each transformation / suggestion / human decision is logged
  (user, timestamp, rationale). **This is THE regulatory differentiator.** Built from
  day 1.
- **Reproducible** — reproducibility comes from **versioned + hashed artifacts**, never from
  re-running a stochastic process. **The LLM is never on the critical path of a
  scientific decision**: it drafts, retrieves, explains; deterministic rules
  or logged human decisions are what decide.

> **Why Python breaks nothing.** The spec's reproducibility does NOT depend on R:
> it comes from the **hashed artifacts + the run manifest + the pinned environment**. In
> Python we hold exactly the same guarantee via `uv.lock` (frozen dependencies) + container
> image digest + RNG seed + manifest. The R/Python choice is a choice of
> *causal-inference libraries*, not a choice of rigor. See §5 (engine decision).

---

## 2. The backbone: audit/provenance + pre-specification lock (cross-cutting, built FIRST)

This is the heart of the spec and what is most missing today. Everything else hangs off it.

### 2.1 Versioned & hashed artifact model (new)

New `artifacts` table (org-scoped, RLS) — source of truth for every
reproducible object (dataset snapshot, QC report, mapped dictionary, DAG, SAP, run):

```
artifacts(
  id uuid pk,
  org_id uuid not null,                      -- RLS tenant
  study_id uuid references studies(id),
  kind text not null,                        -- 'dataset_snapshot'|'qc_report'|'mapping'|'dag'|'sap'|'run_manifest'
  version int not null,                       -- v0 = machine-proposed, v1 = human-approved…
  sha256 text not null,                       -- hash of the canonical content (sorted JSON / text)
  content jsonb,                              -- inline body (DAGitty, SAP YAML→json, edge list…)
  storage_ref text,                           -- or Supabase Storage pointer if large (raw CSV)
  provenance jsonb not null,                  -- {source:'llm'|'human'|'rule', prompt_hash, model_id, ts, parent_version, diff}
  locked bool not null default false,         -- frozen artifact (approved SAP/DAG)
  created_by uuid, created_at timestamptz,
  unique(study_id, kind, version)
)
```

- **Canonical hash**: `sha256(canonical_json(content))` — JSON with sorted keys, or normalized
  DAGitty text. Deterministic, independent of the LLM engine.
- **Lock**: `locked=true` + writing the hash into the SAP. Any post-lock edit creates a
  **new version** and forces a SAP amendment (the pre-specification guarantee).

### 2.2 Provenance log (reuses the existing one)

- `outbox_events` (already in the database: `aggregate_type/aggregate_id/event_type/payload/created_at`)
  → **audit event log**. Each transformation/decision emits an event
  (`artifact.created`, `dag.edge.accepted`, `sap.locked`, `qc.fix.rejected`…) with
  user/ts/rationale in `payload`. Today the table exists, the "backend session" RLS gate
  is in place; **we just need to start writing into it**.
- `agent_runs` (already in the database, unused — cf. `log_agent_run`) → LLM provenance
  (model, tokens, cost, duration). To be wired into `run_structured_agent`.
- `study_state` (already versioned) → stays the workflow state; the **SAP lock** is a
  distinct `kind='sap', locked=true` artifact.

**Spine acceptance:** create a dataset → a hashed `dataset_snapshot` artifact + an `outbox`
event; replay ⇒ same hash; every DAG/SAP edit logged with rationale.

---

## 3. Gap analysis (spec ↔ current code)

| Spec | Today | State |
|---|---|---|
| **Audit/provenance** (cross-cutting) | `usage_events`/`outbox_events`/`agent_runs` exist, ~unused; no artifact hash | ❌ to build (§2) |
| **Pre-spec lock (SAP)** | `study_state` versioned, without hash or lock | ❌ |
| **P1 Ingestion** | `datasets` module, `ExcelUpload`, `storage_path` field | 🟡 model yes; real upload + snapshot/hash + row/col reconciliation no |
| **P2 Cleaning/QC** | `DatasetVerification` + `variable-check` agent (profiling) | 🟡 no QC report as artifact, no accept/reject audit |
| **P3 Mapping/roles** | `dataset_columns.proposed_role` + variable-check agent | 🟡 no CDM, no confidence/answer-key |
| **P4 DAG** | `/agents/dag` (LLM→JSON) + `CausalModel` editor | 🟡→❌ no spec rigor (constraints, dagitty, hash, provenance, adjustment sets) |
| **P5 Estimands/estimators** | `SimulationEngine` estimator configs | ❌ no ICH E9(R1) decision tables, no SAP stub |
| **P6 Engine** | `simulation/run_bootstrap.py` (Python) + `power.py` | 🟡 Python base; no manifest, no gated diagnostics, no Quarto/report |
| **§3.4 evidence-grounded DAG (PubMed)** | **PubMed literature agent** (commit 306fbdc) | 🟢 foundation laid; missing per-edge query + freeze (query_string, retrieval_date) |

---

## 4. Settled decisions

1. **Phase 6 engine = Python** (cf. §5). Reproducibility held by hashed artifacts +
   manifest + pinned env, not by R.
2. **DAG = code, not drawing.** Canonical = **JSON edge list** (`{from,to,rationale,confidence,citation}`),
   with **DAGitty** export (text) for `dagitty`/R-free validation on the Python side.
3. **SHA-256 hashed artifacts**, versioned, lockable (§2.1).
4. **LLM off the critical path** everywhere: it proposes (temp 0, versioned prompt, structured
   JSON output), **deterministic rules** validate and **the human** approves (logged).
5. **Candidate edges** (low confidence) = explicit acceptance task, never auto-accepted.

---

## 5. Engine decision: Python (with guardrails)

The spec names R (`tmle3`/`lmtp`/`WeightIt`/`survival`). We stay Python. Consequences and
mitigations:

**Reproducibility (fully preserved):** container image with a frozen digest,
`uv.lock` (pinned dependencies), RNG seed, **run manifest** (dataset hash + SAP + DAG +
image digest + seed + code version + user + ts). Identical to the spec's R guarantee.

**Mapping of R → Python estimators:**

| Spec (R) | Python equivalent | Maturity |
|---|---|---|
| IPTW / IPW | `scikit-learn` propensity + weighting (`statsmodels`) | ✅ solid |
| g-computation | `statsmodels`/`sklearn` (outcome model + standardization) | ✅ |
| Weighted Cox / MSM | `lifelines` (CoxPHFitter weights) / `statsmodels` PHReg | ✅ |
| Mixed models (clustering) | `statsmodels` MixedLM | ✅ |
| TMLE | `zepid` (TMLE) or in-house cross-fitting | 🟡 less mature than `tmle3` |
| LMTP (longitudinal treatment policies) | **no direct equivalent** | 🔴 real gap |
| E-value (sensitivity) | trivial to implement | ✅ |
| Diagnostics (positivity/balance/weights) | implementable | ✅ |

**Honest trade-off:** we lose the "published/validated `tmle3`/`lmtp` packages" argument
toward the FDA, and **LMTP has no Python equivalent** (longitudinal time-varying estimands
will be limited or custom in v1). **Mitigation:** (a) characterization tests on simulated
data with a known answer (= the spec's step 5 "fake-data test"); (b) keep the
architecture **language-agnostic** (SAP→code compile, container digest in the
manifest) so that a dedicated `tmle3`/`lmtp` **R sidecar** can be added later if a sponsor
requires it, without rewriting anything. Decision: **Python for v1; door open to an R sidecar
as a premium option.**

---

## 6. Sequenced roadmap (milestones)

Each milestone = artifact + acceptance criterion (taken from the spec).

**M0 — Audit/repro spine (cross-cutting, prerequisite).** `artifacts` table + canonical-hash
helper + `outbox_events` writes + wiring `log_agent_run` into
`run_structured_agent`. *Accept:* create a dataset/DAG ⇒ hashed artifact + logged event;
re-hash identical.

**M1 — Phase 1 real ingestion.** Upload → Supabase Storage, **locked** raw snapshot,
schema detection (names/types/missingness), **file fingerprint** + row/col reconciliation
vs declared, dedup by hash. *Accept:* upload → variable inventory < 30 s;
failure if counts ≠ declared or file already loaded.

**M2 — Phase 2 cleaning/QC.** Deterministic QC report (missingness, outliers, impossible
values, duplicates, units) as an **artifact**; suggested fixes accept/reject **one-click,
logged**; idempotent cleaning recipe. *Accept:* cleaned dataset + exportable QC
report; failure if a value changes without a logged rationale.

**M3 — Phase 4 DAG to spec** (high priority, the most differentiating; detail §7). *Accept:*
`dagitty`-validated DAG → minimal adjustment set exported; hashed/versioned DAGitty artifact.

**M4 — Phase 3 hardened mapping.** Mapping to slim CDM + roles, LLM confidence, **answer-key**
hand-checked + agreement metric. *Accept:* analysis-ready labeled dataset; failure if
columns unlabeled or answer-key disagreement.

**M5 — Phase 5 estimands/estimators** (detail §8). Versioned decision tables
(ICH E9(R1)) → estimand → estimator + assumptions checklist → signable, lockable **SAP stub**
YAML. *Accept:* user chooses the estimand → SAP stub auto-generated.

**M6 — Phase 6 Python engine + manifest** (detail §9). SAP→script via templates;
**gated** diagnostics (positivity/balance/missingness); **run manifest**; report
(Quarto-like; in Python: `quarto` with a jupyter kernel, or an in-house HTML/PDF report).
*Accept:* end-to-end run (upload→estimate) with a complete audit trail; re-run of the
manifest ⇒ identical numbers.

> Suggested order: **M0 → M3 (DAG) → M5 (estimands) → M6 (engine)**, interleaving
> M1/M2/M4 (ingestion/QC/mapping) along the way. Rationale: M3+M5+M6 form the
> differentiating chain (hashed DAG → locked SAP → reproducible run); M1/M2/M4 harden the
> upstream that is already half present.

---

## 7. Phase 4 — Reproducible DAG (detailed design)

Adapts §3 of the spec to the code (`modules/agents` + `CausalModel.jsx`).

1. **Deterministic inputs**: only the Phase 3 mapped dictionary (names, labels,
   exposure/outcome/covariate/mediator-candidate roles, timing). Structured versioned
   file — no free prompt.
2. **Constraint layer (rule-based, BEFORE the LLM)**: no edge from time-posterior →
   time-prior; if randomized, no incoming edge on the exposure except
   randomization; the outcome has no outgoing edge. Deterministic + **unit tests**.
   → new `modules/agents/dag_constraints.py`.
3. **LLM proposal under repro control**: versioned prompt template, pinned model,
   **temp 0**, JSON output (1 edge = `{from,to,rationale,confidence,citation}`).
   `prompt_hash`+`model_id`+`ts` in the artifact's provenance. (The existing `/agents/dag`
   is the starting point; we harden the output and pin it.)
4. **Formal validation**: pipe the edge list into a `dagitty`-type validation —
   acyclicity, orphan nodes, **minimal (backdoor) adjustment set derivation**,
   colliders/mediators NOT to adjust for. In Python (no R): implement the backdoor
   criterion on the graph (networkx) or port the `dagitty` logic. Failure ⇒ back to step 3
   with the violation injected.
5. **Artifact = source of truth**: DAGitty (text) + JSON edge-list, **SHA-256**, v0 =
   machine. Anyone with the file reproduces the DAG and its adjustment sets, forever.
6. **Investigator editing with provenance**: visual editor (`CausalModel.jsx`);
   add/delete/reverse ⇒ mandatory rationale + log (user, ts, before/after); each save =
   new version; on approval **lock** + hash written into the SAP.
7. **Candidate edges** (low confidence) = dashed edges to accept/reject
   explicitly.
8. **§3.4 evidence-grounding (optional, premium)**: for each edge, a templated PubMed query
   via **the literature agent already built** (E-utilities) → supporting/
   contradicting PMIDs; **freeze** into the artifact (PMID, title, `query_string`, `retrieval_date`).
   Ship v1 without it; add as "evidence-grounded DAG".

---

## 8. Phase 5 — Estimands & estimators (detailed design)

**Rule-based** selection, not LLM (the LLM only drafts the plain-language justification).

- **Inputs**: locked v1 DAG (by hash), design metadata (randomized/observational,
  cluster, crossover), dictionary (outcome type, censoring, time-varying treatment).
- **Estimand derivation**: deterministic design+DAG decision table → estimands framed
  ICH E9(R1) (population, contrast, endpoint, intercurrent-event strategy, summary).
  Time-varying confounding detected in the DAG ⇒ flag longitudinal estimands (⚠ LMTP =
  Python gap, cf. §5).
- **Estimator matching**: 2nd estimand+data table → estimator (among the Python
  mapping §5) + **assumptions checklist** (positivity, exchangeability given the adjustment
  set, censoring) + known failure modes.
- **SAP stub artifact** (YAML/JSON): estimand, adjustment set **inherited from the locked DAG**,
  primary estimator, pre-specified sensitivity analyses (E-value, alt estimator, alt DAG
  on uncertain edges). Review → logged edit → signature → **lock + hash**.
- The **decision tables are versioned** (we know which rule produced which
  suggestion). → new `modules/<estimands>/decision_tables/` (versioned YAML).

---

## 9. Phase 6 — Python analysis engine (detailed design)

- **Pinned env**: container image (Modal) with a frozen digest + `uv.lock` (numpy/scipy/
  statsmodels/lifelines/scikit-learn/zepid + report). The digest is part of every run.
- **SAP → code**: the SAP YAML compiles **deterministically** into a Python script via templates;
  the mapping's variable roles fill the arguments. **No analysis code written by
  hand** ⇒ nothing to deviate from the SAP.
- **Gated execution**: before estimation, diagnostics that **block** — positivity
  (propensity overlap), covariate balance, missingness reconciled vs the Phase 2 QC
  report. Violation ⇒ logged investigator override.
- **Run manifest** (artifact `kind='run_manifest'`): dataset hash + SAP + DAG + container
  digest + RNG seed + code version + user + ts. *The repro sentence to the regulator.*
- **Outputs**: estimates + CI, diagnostic plots (balance, positivity, weights), auto-generated
  report (Quarto via Python kernel, or in-house report) whose first page prints the
  manifest. Extends `simulation/run_bootstrap.py` (Modal worker, already planned as a follow-up).

---

## 10. Risks & open questions

- **LMTP / longitudinal estimands**: no mature Python equivalent → either custom, or out of
  v1, or an R sidecar later. To be settled when a client case demands it.
- **Python TMLE** (`zepid`) less battle-tested than `tmle3` → validate via fake-data tests.
- **Quarto** is R/Python-agnostic but adds a dependency; alternative: in-house
  HTML/PDF report (WeasyPrint, already considered for generated documents).
- **Supabase Storage** (raw uploads, reports) not yet wired — M1 prerequisite.
- **LLM keys** (`ANTHROPIC`/`OPENAI`) required for the LLM layers (DAG proposal,
  justifications, embeddings); all the rule-based + repro works without them.
- **CDM/OMOP**: the spec says "OMOP later" → v1 = in-house slim CDM.

---

## 11. Immediate next steps

1. **M0 — spine**: `artifacts` table + migration + canonical-hash helper + first `outbox`
   events + wiring `log_agent_run`. (Small, cross-cutting, unblocks everything.)
2. **M3 — Phase 4 DAG to spec**: `dag_constraints.py` (rule-based + tests) → harden
   `/agents/dag` (temp 0, versioned prompt, JSON+provenance) → backdoor validation
   (networkx) → hashed DAGitty artifact → editing provenance in `CausalModel.jsx`.
3. Reuse the **PubMed agent** for §3.4 (evidence-grounded) once M3 is in place.

> To validate with Quentin before coding M0/M3.
