# Augura Platform — Architecture backend

**Date** : 2026-06-11
**Statut** : validé (brainstorm Quentin × Claude)
**Portée** : architecture du nouveau backend de production d'Augura et du monorepo qui l'héberge. Ce document est la référence du plan d'implémentation.

---

## 1. Contexte et motivation

Augura (repo actuel `lucis-dashboard`) est une plateforme d'aide à la conception d'études cliniques : workflow multi-phases (profiling E1 → risques → outcome → DAG causal → design → simulation → résultats), agents LLM adossés à un corpus de preuves (PubMed, MAUDE, FDA Guidance, ClinicalTrials.gov) indexé en pgvector.

L'architecture actuelle est une fracture JS/Python non assumée :

- 11 fonctions serverless Vercel en JS (`api/*.js`) : agents (trace E1 en SSE, dag, gap-detection, variable-check), proxies Anthropic/OpenAI, recherche vectorielle ;
- des scripts Python offline (`simulation/run_bootstrap.py` : bootstrap N=1000, numpy/scipy/statsmodels) sans lien avec l'API ;
- limites atteintes : timeout Vercel 300 s sur `trace.js`, aucun mécanisme de jobs longs ni de cron, RLS désactivé (bug T1), état du workflow en sessionStorage navigateur, mode démo entremêlé au code de production, fixtures mock manuelles par route.

Décision : reconstruire le backend en **monolithe modulaire Python/FastAPI**, dans un **nouveau monorepo**, déployé sur **Modal**, avec **Supabase** (nouvelle instance) comme base de données et auth. Migration **big bang** outillée par des tests de caractérisation. Le repo actuel `lucis-dashboard` devient une **démo frontend pure** (mocks), sans lien avec le backend de production.

## 2. Décisions actées

| # | Sujet | Décision |
|---|-------|----------|
| 1 | Périmètre | Remplacer intégralement le backend d'Augura (fonctions Vercel + scripts Python) |
| 2 | Stratégie | Big bang dans un nouveau projet ; parité prouvée avant bascule |
| 3 | Démo | Aucun mode démo dans le backend ; la démo = frontend autonome (lucis-dashboard figé) |
| 4 | Nouvelles capacités | Simulation à la demande · corpus self-service · génération de documents · multi-études & collaboration |
| 5 | Front de production | Migré dans le monorepo (`apps/web`), débarrassé des mocks |
| 6 | Base de données | Nouvelle instance Supabase dédiée prod + environnement dev distinct, migrations versionnées dès le jour 1 |
| 7 | Accès aux données | Tout passe par FastAPI (porte unique) ; RLS conservé en défense en profondeur |
| 8 | Auth | Supabase Auth côté front ; FastAPI vérifie le JWT (JWKS) ; scoping tenant côté serveur |
| 9 | Structure interne | Monolithe modulaire en tranches verticales ; frontières vérifiées par import-linter |
| 10 | Couche données | SQLAlchemy 2.0 async (asyncpg) + Alembic |
| 11 | Runtime agents | SDK Anthropic async + runtime maison typé (port de `agents/runtime/anthropic.js`) ; ni pydantic-ai ni LangGraph |

## 3. Pourquoi Python (vs Node.js / Go)

1. **Le cœur métier est déjà en Python et il est intransportable** : estimateurs ATE/ATT/LME/IPW, bootstrap paramétrique, power analysis = scipy/statsmodels/sklearn. Aucun équivalent crédible en JS ; gonum (Go) est embryonnaire. Tout autre choix impose deux runtimes à vie.
2. **L'écosystème IA est first-class** : SDK Anthropic, validation Pydantic des sorties structurées d'agents, LangSmith, pipelines d'embeddings.
3. **Le contrat de types** : Pydantic v2 → OpenAPI → client TypeScript généré. Validation runtime + documentation + génération en un geste.
4. **La « lenteur » de Python est hors sujet ici** : backend I/O-bound (latence dominée par les LLM et la DB) → asyncio suffit largement ; compute-bound vectorisé numpy (C sous le capot). Go ne gagnerait que sur du throughput HTTP massif CPU-light, qui n'est pas le profil d'Augura (B2B, faible volume).
5. **Modal est Python-natif** : API ASGI en une décoration, jobs longs sans Celery/Redis, cron intégré, GPU accessible.

Concessions reconnues : Node aurait donné le partage de types sans génération et des cold starts plus courts ; Go un binaire statique et une RAM minime. Aucun ne compense le point 1.

## 4. Monorepo

```
augura-platform/
├── apps/
│   ├── api/                          # monolithe FastAPI
│   │   ├── src/augura_api/
│   │   │   ├── core/                 # socle technique, zéro logique métier
│   │   │   │   ├── config.py         # pydantic-settings, fail-fast au boot
│   │   │   │   ├── db.py             # engine async, session/requête, SET LOCAL tenant
│   │   │   │   ├── auth.py           # vérification JWT Supabase (JWKS)
│   │   │   │   ├── tenancy.py        # dépendance CurrentTenant
│   │   │   │   ├── errors.py         # hiérarchie AppError + handlers RFC 9457
│   │   │   │   ├── logging.py        # structlog JSON + request_id
│   │   │   │   ├── llm/              # client Anthropic/OpenAI, runtime agents, SSE
│   │   │   │   └── events.py         # événements de domaine → outbox
│   │   │   ├── modules/
│   │   │   │   ├── studies/  datasets/  corpus/  agents/
│   │   │   │   ├── simulation/  documents/  analytics/
│   │   │   │   └── (chaque module : __init__.py · router.py · service.py
│   │   │   │        · schemas.py · repo.py · models.py)
│   │   │   ├── jobs/                 # entrypoints Modal Functions (adaptateurs fins)
│   │   │   └── main.py               # composition root
│   │   ├── alembic/                  # migrations versionnées (schéma + policies RLS)
│   │   ├── tests/
│   │   ├── modal_app.py              # ASGI app + Functions + Cron
│   │   └── pyproject.toml            # uv ; pyright strict ; ruff
│   └── web/                          # front React 19 + Vite migré, sans mock layer
├── packages/
│   └── api-client/                   # TS généré depuis l'OpenAPI — jamais édité à la main
└── .github/workflows/                # CI : lint, typecheck, tests, drift check, deploy
```

### Règles de frontières (ce qui rend le monolithe « modulable »)

- Un module n'importe que `core` et l'interface publique (`__init__.py`) des autres modules — jamais leurs internals. `import-linter` casse la CI en cas de violation.
- `core` n'importe aucun module.
- `router.py` et `jobs/*` sont des adaptateurs fins (HTTP / Modal) ; la logique vit dans `service.py`.
- `repo.py` est l'unique point d'accès DB du module ; chaque méthode exige un `TenantId`.
- Les modèles SQLAlchemy ne sortent jamais d'un module ; les frontières échangent des schemas Pydantic.
- Un module devenu trop gros est extractible en service séparé sans réécriture : son contrat public existe déjà.

## 5. Modules et responsabilités

| Module | Responsabilité | Notes |
|--------|----------------|-------|
| `studies` | Cycle de vie des études, état du workflow persisté et versionné, membres/rôles par étude | Remplace le sessionStorage ; débloque multi-appareils et collaboration |
| `datasets` | Upload cohortes (Supabase Storage), parsing/validation pandas hors event loop, profil de colonnes, mapping variables | |
| `corpus` | Ingestion self-service (PDF → extraction → chunking → embeddings → pgvector), retrieval SQL direct, corpus global partagé + corpus privé par tenant | `match_chunks` devient une requête SQLAlchemy/pgvector |
| `agents` | E1 profiling (SSE multi-tour), DAG, gap-detection, variable-check sur un runtime commun | Sorties validées Pydantic + 1 retry « réparation » ; protocole NDJSON identique à l'actuel |
| `simulation` | Bootstrap à la demande (job Modal), approximation analytique synchrone calibrée **par outcome** (fix T4), lecture des résultats | Port de `run_bootstrap.py` |
| `documents` | Génération protocole/rapport : état d'étude → LLM + template → PDF (WeasyPrint) / Word (python-docx) → Storage → URL signée | Asynchrone (job) |
| `analytics` | Usage events authentifiés, audit trail via outbox, stats admin, coûts tokens par run d'agent | Remplace le soft-auth |

## 6. Modèle de données (tables principales)

- **Tenancy** : `orgs`, `memberships` (user ↔ org, rôle owner/member/viewer)
- **Études** : `studies`, `study_members`, `study_state` (workflow versionné, JSONB)
- **Données** : `datasets`, `dataset_columns`
- **Corpus** : `documents`, `chunks` (embedding pgvector, index HNSW ; `tenant_id` nullable → corpus global)
- **Jobs** : `jobs` (type, status queued/running/succeeded/failed, progress, payload, result_ref, error, `idempotency_key`, `modal_call_id`)
- **Simulation** : `simulation_runs` (params JSONB, lien job, résultats)
- **Documents générés** : `generated_documents` (type, storage_path, statut)
- **Observabilité métier** : `usage_events`, `outbox_events`, `agent_runs` (durée, tokens, coût)

Toutes les tables tenant-scopées portent une policy RLS fondée sur `current_setting('app.tenant_id')`.

### Migration des données existantes

- Corpus (`documents` + `chunks` + embeddings) : dump/restore vers la nouvelle instance — **pas de ré-embedding**.
- Cohortes et données de validation : ré-upload via les scripts existants adaptés.
- `simulation_results` précalculés : non migrés (remplacés par la simulation à la demande) ; la démo conserve les siens en fixtures.

## 7. Auth et tenancy

1. Le front utilise Supabase Auth (login, session, refresh) et envoie le JWT en `Authorization: Bearer`.
2. `core/auth.py` vérifie signature (JWKS Supabase, cache), expiration, audience → `UserId`.
3. `core/tenancy.py` résout l'appartenance (`memberships`) → `CurrentTenant` injecté dans les routes.
4. `core/db.py` exécute `SET LOCAL app.tenant_id = :tid` à l'ouverture de chaque transaction ; les policies RLS s'y adossent. L'API se connecte avec un rôle Postgres dédié **non exempt de RLS** (pas le service_role).
5. Résultat : le scoping est appliqué deux fois (repos + RLS). L'oubli d'un filtre dans un service ne peut pas fuiter des données inter-tenants.

## 8. Flux clés

**Requête standard** — client généré → JWT → tenant → service → repo → Pydantic response. Budget p95 < 300 ms hors LLM.

**Agent E1 (SSE)** — `POST /agents/profiling/stream` → boucle tool-use (l'outil retrieval appelle l'interface publique de `corpus`) → events NDJSON streamés (heartbeats ; fin systématique par `done` ou `error`) → résultat persisté dans `study_state`. Plus de plafond 300 s. Premier token < 2 s.

**Job (simulation, ingestion, export)** — `POST /simulations` → insert `jobs` + `Function.spawn(job_id)` → `202 {job_id}` → le worker met à jour `progress` → suivi par polling `GET /jobs/{id}` (SSE possible plus tard). Idempotency key obligatoire sur les POST de jobs : un double-clic ne lance pas deux bootstraps.

## 9. Règles de robustesse

### Typage
- pyright **strict** en CI ; ruff (lint + format).
- Pydantic v2 à toutes les frontières : requêtes, réponses, settings, payloads de jobs, sorties d'agents.
- `NewType` pour `TenantId`, `StudyId`, `UserId`, `JobId`.
- `Any` et `type: ignore` interdits sauf commentaire justificatif.
- Client TS généré depuis l'OpenAPI (`openapi-typescript`) ; la CI échoue si le client commité a dérivé du contrat (drift check). Le front n'écrit jamais un appel à la main.

### Exécution
- Async de bout en bout (httpx, SDK Anthropic async, asyncpg). L'event loop ne fait que de l'I/O.
- Tout calcul > ~100 ms sort de l'API : thread (`anyio.to_thread`) pour le parsing Excel, job Modal pour le bootstrap et l'ingestion.
- Cache des réponses d'agents déterministes (mêmes inputs → réponse servie depuis la table cache ; fix U2).
- Pagination keyset ; index pgvector HNSW.

### Erreurs
- Hiérarchie `AppError(code, http_status, message, details)` → handler global → réponses **Problem Details (RFC 9457)** uniformes.
- LLM : retries du SDK + timeout par appel ; indisponibilité amont → 503 explicite, jamais d'attente infinie.
- Sorties structurées invalides : 1 retry « réparation » avec l'erreur de validation injectée, puis échec franc.
- Jobs : statut `failed` + erreur détaillée + alerte Sentry ; relance manuelle.

## 10. Déploiement (Modal) et observabilité

- `modal_app.py` : l'API en `@modal.asgi_app()` (image légère uv) ; les jobs en `modal.Function` avec image scientifique séparée (numpy/scipy/statsmodels — l'image API reste fine) ; `modal.Cron` pour le récurrent (ex. rafraîchissement du corpus public).
- Environnements Modal `dev` / `prod` : secrets distincts (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `SUPABASE_JWT_*`), instances Supabase distinctes.
- Prod : `min_containers=1` (pas de cold start utilisateur) ; dev : scale-to-zero.
- CI GitHub Actions : ruff + pyright + pytest + import-linter + drift check → `modal deploy` sur `main`. Front : Vercel (statique), `VITE_API_URL` → domaine custom Modal.
- Observabilité : structlog JSON + request_id, Sentry (erreurs), LangSmith (traces agents), `agent_runs` (coûts/latences en DB).

## 11. Stratégie de test — le filet du big bang

1. **Caractérisation** : les fixtures actuelles (`src/mocks/apiFixtures.js`) deviennent des golden files ; le FastAPI doit répondre la même chose que les routes JS, à schéma près. Les écarts sont listés et assumés, jamais accidentels.
2. **Repos + RLS** : pytest + Postgres éphémère ; les policies RLS sont testées explicitement (un tenant ne lit jamais l'autre).
3. **Contrat** : le client TS généré compile contre `apps/web` ; drift check en CI.
4. **Métier neuf en TDD** : calibration par outcome, power analytique, idempotence des jobs.
5. **E2E** : le Playwright existant rebranché sur le nouveau backend.
6. **Critère de bascule** : golden tests + e2e verts, RLS vérifié. Tant que ce n'est pas vert, l'ancien backend reste en service.

## 12. Séquencement

1. Scaffold monorepo + CI + hello world Modal (la tuyauterie d'abord)
2. `core` + auth + tenancy + `studies` minimal + client généré → le front migré boote (login, liste d'études)
3. `datasets` + `corpus` + transfert du corpus existant
4. `agents` (caractérisation d'abord ; E1 SSE en dernier des quatre)
5. `simulation` + infra jobs
6. `documents` + `analytics`
7. Parité prouvée → bascule du front de prod → `lucis-dashboard` figé en démo pure

## 13. Hors périmètre (non-objectifs)

- Pas de microservices, pas de message broker, pas de Kubernetes : le monolithe modulaire + Modal Functions couvrent les besoins ; l'extraction d'un module restera possible grâce aux frontières.
- Pas de mode démo, soft-auth ou fixtures dans le backend.
- Pas de réécriture du design system front (déjà fait sur `quentin-workspace`).
- Pas de SSE sur le suivi de jobs en v1 (polling suffit ; l'upgrade est locale au module).
- L'app iOS/Apple Health n'est pas dans ce périmètre ; si elle arrive, elle consommera la même API (le contrat OpenAPI est déjà la porte unique).

## 14. Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| Big bang qui s'éternise | Séquencement par modules livrables ; l'ancien backend reste en service jusqu'au critère de bascule |
| Dérive du protocole SSE (le front actuel dépend du NDJSON existant) | Caractérisation du flux `trace.js` event par event avant le port |
| Cold starts / latence Modal | `min_containers=1` en prod ; image API minimale (uv, sans deps scientifiques) |
| Coûts LLM invisibles | `agent_runs` trace tokens et coût par run ; vue admin dans `analytics` |
| RLS mal configuré | Policies écrites dans les migrations Alembic + tests d'isolation dédiés ; rôle de connexion non exempt |
| Embeddings à re-payer | Dump/restore du corpus, jamais de ré-embedding |
