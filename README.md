# Augura Platform

Monorepo de production d'Augura — plateforme de conception d'études cliniques.

- `apps/api` — backend FastAPI (monolithe modulaire), déployé sur Modal
- `apps/web` — frontend React (arrive en phase 2)
- `packages/api-client` — client TS généré depuis l'OpenAPI (drift-check en CI)
- `docs/specs` — architecture validée · `docs/plans` — plans d'implémentation

Spec de référence : `docs/specs/2026-06-11-augura-backend-architecture-design.md`.
Design de livraison : `docs/specs/2026-06-13-delivery-design.md`.
