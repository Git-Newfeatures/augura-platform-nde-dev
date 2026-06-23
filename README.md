# Augura Platform

Augura production monorepo — clinical study design platform.

- `apps/api` — FastAPI backend (modular monolith), deployed on Modal
- `apps/web` — React frontend (arriving in phase 2)
- `packages/api-client` — TS client generated from the OpenAPI (drift-check in CI)
- `docs/specs` — validated architecture · `docs/plans` — implementation plans

Reference spec: `docs/specs/2026-06-11-augura-backend-architecture-design.md`.
Delivery design: `docs/specs/2026-06-13-delivery-design.md`.
