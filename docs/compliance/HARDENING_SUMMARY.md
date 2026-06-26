# Compliance hardening — HIPAA / GDPR / SOC2 (Phases 0–4)

Hardens the existing stack (no rewrite) across data minimization, transport, access
control, auditability, data-subject rights, and observability. **31 commits · 73 files ·
+6,384 / −136.** No behavioral change for well-formed authenticated requests; the new
gates fail closed in prod and are no-ops in dev/CI.

## Phase 0 — Data minimization & tamper-evidence
- Make `usage_events` / `outbox_events` **append-only**; drop the forgeable authenticated insert path.
- Record login events via an **attributed backend endpoint** (real actor, not client-asserted).
- **Stop sending raw dataset cell values to the LLM** (PHI minimization).
- Remove unbacked "Pseudonymised" / "SECURE" claims from the UI.

## Phase 1 — Transport, boot & secret hardening
- **Enforce verified TLS to Postgres** + fail-fast prod boot guard.
- **Forbid HS256 JWT secrets in prod** (JWKS-only).
- **Require the Supabase Storage backend in prod** — no plaintext-disk fallback.
- Org-prefix guard on object reads (defense in depth).
- Prod **security-headers middleware** (HSTS / nosniff / CSP).
- Stop leaking auth internals / ids in error responses (prod).
- Provision the datasets storage bucket **private + reproducibly**.
- Server-side **PII gate on dataset ingestion** (reject direct identifiers).
- **Redact PHI/PII-ish fields** from structured logs.
- Dependency **SCA** (pip-audit / npm audit) + Dependabot; bump `pydantic-settings` 2.14.2 (GHSA-4xgf-cpjx-pc3j).
- Add **CODEOWNERS** (branch protection enabled via GitHub settings).
- `SUBPROCESSORS.md` — sub-processor inventory + **GDPR Art 30** register.

## Phase 2 — Access control
- **RBAC write-gating** — `viewer` is read-only on all mutating endpoints.
- Flag-gated **MFA (aal2) enforcement** on authenticated routes.
- **JWKS hardening** — require `kid`, cache with TTL + refresh-on-miss.

## Phase 3 — Audit trail & data-subject rights
- Append-only **`audit_events`** change log via DB triggers.
- Storage `delete_bytes` + dataset **erasure & export** (GDPR Art 17 / 15 / 20).
- **Durable GDPR erasure** — object deletes happen post-commit via a dedicated committed session (FastAPI runs bg tasks pre-commit).
- Dataset **`retention_until`** column + purge-expired primitive.
- **PHI read-access logging** on cohort / dataset reads.

## Phase 4 — Observability & ops
- **Sentry** error tracking — no-op without a DSN.
- Runbooks: **incident response, backup/DR, deployment**.
- Env-gate engine TLS (don't force on non-TLS dev/CI) + ungate the read-only `/causal/dag`.

## Notes
- Spec & per-phase plans are committed under `docs/` (HIPAA/GDPR/SOC2 hardening spec + Phase 0–4 plans).
- Part 11 e-signatures deferred; de-identification + direct-LLM path retained per the program decision.
