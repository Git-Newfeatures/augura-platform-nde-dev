# Sub-processors & GDPR Article 30 Record of Processing

Date: 2026-06-24 · Owner: Augura (controller/processor) · Review cadence: quarterly or on any sub-processor change.

This document is the authoritative inventory of third parties that process data on Augura's
behalf, plus the GDPR Art 30 record of processing activities. It is referenced by the
compliance hardening program (`docs/superpowers/specs/2026-06-24-compliance-hardening-design.md`).

> **Data-flow note (post Phase 0):** raw cohort cell values are **no longer transmitted to LLM
> sub-processors** — only column *statistics* (kind, null%, ranges, n_distinct) and
> study-design free-text (PICOT, product description) cross that boundary
> (see `apps/api/src/augura_api/modules/agents/tools.py`). PHI minimization at the LLM
> boundary is therefore enforced in code, not just by contract.

## Sub-processor inventory

| Sub-processor | Service | Data it may receive | Region | Transfer basis (for EU data) | DPA/BAA status |
|---|---|---|---|---|---|
| **Supabase** | Postgres DB, Auth (JWT), Storage (dataset bytes) | All tenant data incl. cohort/biomarker rows (PHI), auth identifiers | `us-east-2` (Augura_Prod `fqmoylmvjoafihiuiiuj`) | SCCs / DPF — **confirm in Supabase DPA** | DPA: **confirm executed** |
| **Modal** | Backend compute (FastAPI) | Transient processing of all request data (no persistent store) | US | SCCs / DPF — **confirm** | DPA: **confirm executed** |
| **Vercel** | Frontend hosting (branch `Quentin`) | No server-side PHI (SPA talks to the API with the user's JWT); request metadata only | US (edge) | SCCs / DPF — **confirm** | DPA: **confirm executed** |
| **Anthropic** | LLM (Claude) — agents, causal, semantic | Column **statistics** + study-design free-text. **No raw cohort rows** (enforced). | US | SCCs / DPF — **confirm** | DPA: **confirm executed**; default API tier is no-train per commercial terms |
| **OpenAI** | Embeddings (`text-embedding-3-small`) — corpus retrieval | Document/query text for retrieval; **no cohort PHI** | US | SCCs / DPF — **confirm** | DPA: **confirm executed**; API data not used for training by default |
| **NCBI / PubMed** | Literature search (E-utilities) | **Search terms only** (study concepts) — no tenant PHI | US | Public API; no personal data sent | Terms of use (not a processor of personal data) |
| **ClinicalTrials.gov** (+ optional relay) | Trial registry search | Search terms only — no tenant PHI | US | Public API | Terms of use; document the relay operator if used |

**Action items (owner):** confirm and file the executed DPA (and, where PHI is involved, BAA) for
Supabase, Modal, Vercel, Anthropic, and OpenAI; record the international-transfer mechanism
(SCCs or EU-US Data Privacy Framework participation) for each; complete a Transfer Impact
Assessment for EU tenants. Track signed copies in the compliance evidence store.

## GDPR Article 30 — Record of Processing Activities

**Controller / processor:** Augura operates as a processor for its customers (the controllers
of the clinical study data) and as a controller for account/auth data.

| Field | Detail |
|---|---|
| **Purposes of processing** | Clinical study design support: dataset ingestion & data-quality, cohort/biomarker analysis, causal model (DAG) generation, literature retrieval, document/dossier generation. |
| **Categories of data subjects** | Study participants/patients (via uploaded cohort datasets); platform users (clinical/research staff). |
| **Categories of personal data** | Special-category health data — biomarkers (HbA1c, LDL, hs-CRP, BMI), demographic fields in cohort rows. Account data — email, auth identifiers. Direct identifiers are screened at ingestion (PII gate, Phase 1). |
| **Recipients / sub-processors** | As listed in the inventory above. |
| **International transfers** | Data resides in US (`us-east-2`). Sub-processors are US-based; rely on SCCs / DPF per the inventory. |
| **Retention** | Per the data-retention schedule (Phase 3 deliverable: `retention_until` + scheduled purge). Until then, retained for the study lifecycle. |
| **Security measures** | Multi-tenant isolation via forced Postgres RLS under a non-BYPASSRLS role; verified TLS in transit; encryption at rest (Supabase-managed); append-only audit trail; RBAC; security headers; dependency scanning. See the hardening spec. |
| **Lawful basis (Art 6) / special-category condition (Art 9)** | Recorded per customer/controller — **see Phase 3 consent/lawful-basis register** (not yet implemented). |

## Per-tenant LLM egress (planned — Phase 1b)

A future change will add a per-org egress policy (`external_llm_enabled`, `allowed_subprocessors`)
resolved alongside tenancy and checked before any LLM client is constructed, so a tenant can
opt out of external-LLM processing entirely. Until then, LLM calls are governed by the global
de-identification boundary above and the DPAs in the inventory.
