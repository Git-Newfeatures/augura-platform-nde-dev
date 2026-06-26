# Incident Response, Backup & Disaster Recovery Runbook

Date: 2026-06-25 · Owner: Augura engineering · Review: quarterly · Frameworks: HIPAA §164.308(a)(6)/(7), GDPR Art 32–34, SOC 2 CC7/A1.

This runbook covers (1) security/privacy incident response, (2) backup & restore, and (3) the
deployment/monitoring controls. It is part of the compliance hardening program
([spec](../superpowers/specs/2026-06-24-compliance-hardening-design.md)).

> **Status legend:** ✅ implemented · ⚙️ config/verify (owner) · 📝 documented-only (follow-up).

## 1. Monitoring & alerting

| Control | Status | Notes |
|---|---|---|
| Error tracking (Sentry) | ✅ code / ⚙️ DSN | `sentry_sdk` initialized in `create_app` ONLY when `AUGURA_SENTRY_DSN` is set (no-op otherwise). Set the DSN in the Modal `augura-api` secret to activate. |
| Structured logs | ✅ | JSON via structlog; PHI-redacted (`core/log_redaction.py`). Ship Modal logs to a retained drain (⚙️). |
| Alerting (500-rate / auth-failures / job-failures) | ⚙️ | Configure in Sentry + the log drain once the DSN is live. |
| Uptime monitor on `/healthz` | ⚙️ | Add an external uptime check (e.g. Better Uptime / Pingdom) against the Modal URL. |

## 2. Backup & disaster recovery

**Database:** Supabase-managed Postgres, project `Augura_Prod` (`fqmoylmvjoafihiuiiuj`), region `us-east-2`.

| Item | Status | Action |
|---|---|---|
| Daily backups | ⚙️ verify | Confirm in Supabase dashboard → Database → Backups. |
| Point-in-Time Recovery (PITR) | ⚙️ verify/enable | Enable PITR for the prod project (paid add-on). Without it, recovery granularity is the daily backup. |
| Object storage (`datasets` bucket) | ⚙️ verify | Supabase Storage durability is provider-managed; confirm there is no separate lifecycle expiry that would delete clinical bytes prematurely. |
| **RPO (recommended)** | 📝 | ≤ 24h with daily backups; ≤ 5 min with PITR. **Target: PITR, RPO ≤ 5 min.** |
| **RTO (recommended)** | 📝 | ≤ 4h (restore a backup/PITR snapshot to a new project + repoint `AUGURA_DATABASE_URL`). |
| Restore drill | 📝 quarterly | Restore the latest backup into a throwaway project, run `apps/api/scripts/verify_supabase.py`, confirm row counts + RLS isolation. Record the drill in the compliance evidence store. |

**Restore procedure (outline):** Supabase dashboard → Backups → restore to a new project (or PITR to a timestamp) → update the Modal `augura-api` secret's `AUGURA_DATABASE_URL` to the restored host (keep `?sslmode=require`) → redeploy → smoke-test `/healthz` + a tenant read.

## 3. Deployment controls (change management — SOC 2 CC8)

| Control | Status | Notes |
|---|---|---|
| CI gate (ruff/pyright/lint-imports/pytest/db-bundle/client-drift/web/security) | ✅ | `.github/workflows/ci.yml`. |
| Branch protection on `main`/`Quentin` | ⚙️ | Enable required-checks + code-owner review (CODEOWNERS shipped). Commands in the deploy runbook. |
| Migrate-then-deploy coupling | 📝 | The Modal deploy runs NEITHER migrations NOR seed. Apply alembic migrations to prod (via Supabase MCP / a privileged role) BEFORE/with each deploy. Prefer a deploy script that runs `alembic upgrade head` then `modal deploy`, failing closed on migration error. |
| Deploy-from-CI | 📝 (deliberately not auto-wired) | An auto-deploy on push would fail-boot prod if the Modal env lacks `?sslmode=require` / Supabase Storage vars / no HS256 (the Phase 0 boot guards). Wire it only after those env invariants are codified + a `MODAL_TOKEN` secret is added; until then deploy manually via `bash apps/api/scripts/deploy_modal.sh`. |

## 4. Security / privacy incident response (HIPAA §164.308(a)(6), GDPR Art 33/34)

**Detect → Contain → Assess → Notify → Remediate → Record.**

1. **Detect:** Sentry alert, log anomaly, the append-only `audit_events` trail (who/what/when on regulated records), or a report.
2. **Contain:** revoke the implicated credential (Supabase JWT signing key rotation, Modal secret rotation, disable the affected membership), and if needed put the API in maintenance.
3. **Assess scope (use the audit trail):**
   - Record changes: `select * from audit_events where org_id = :org and occurred_at >= :t order by occurred_at;`
   - PHI access/exports: `select * from usage_events where event_type in ('dataset.read','cohort.read','cohort.biomarkers.read','dataset.files.read','dataset.exported') and org_id = :org and created_at >= :t;`
   - Logins: `usage_events where event_type='login'`.
4. **Notify:** GDPR — controller notifies the supervisory authority within **72h** of becoming aware of a personal-data breach (Art 33), and affected subjects without undue delay if high risk (Art 34). HIPAA — breach notification per §164.404–410. Maintain the sub-processor contacts in [SUBPROCESSORS.md](SUBPROCESSORS.md).
5. **Remediate:** patch, rotate, and add a regression test/control.
6. **Record:** log the incident, timeline, scope, and actions in the compliance evidence store; feed lessons back into the hardening program.

**Key facts for responders:** tenant isolation = forced Postgres RLS under non-BYPASSRLS `augura_app`; audit trail is append-only (`augura_app` cannot UPDATE/DELETE `audit_events`/`usage_events`); PHI does not reach LLM sub-processors (only column statistics); secrets live in the Modal `augura-api` secret + Supabase.
