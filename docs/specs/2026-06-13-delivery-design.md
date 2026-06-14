# Augura Platform — Design de livraison (backend complet)

**Date** : 2026-06-13
**Statut** : validé (go Quentin)
**Portée** : transformer la spec d'architecture validée (`2026-06-11-augura-backend-architecture-design.md`) en un programme d'implémentation exécutable, phase par phase, jusqu'au backend de production complet + frontend migré + base exportable Supabase.
**Référence** : ce document complète la spec ; il ne la remplace pas. La spec décrit l'état final ; ce document décrit *comment on y va* et fige le schéma concret + le contrat de données.

---

## 1. Décisions de cadrage (2026-06-13)

| # | Sujet | Décision |
|---|-------|----------|
| D1 | Périmètre de la livraison | **Tout**, agents LLM compris (les 7 modules + les 4 agents) |
| D2 | Cible base de données | **Artefacts SQL/Alembic seulement** — aucune base existante touchée, aucun Docker/Postgres local lancé sur la machine de dev |
| D3 | Frontend | **Migration `lucis-dashboard` → `apps/web`** sans couche mock ; `lucis-dashboard` reste figé en démo pure |
| D4 | Auth | **Supabase Auth + vérification JWKS + RLS** bout-en-bout |

Conséquence de D1 + D2 : le backend est livré comme **code + tests**. La vérification repose sur pyright strict + ruff + import-linter + pytest (logique/contrat/agents-LLM-mockés en local ; repos+RLS branchés sur la CI GitHub Actions avec un service `postgres`, pas exécutés en local). Pas de run end-to-end live tant que l'utilisateur n'a pas créé son instance Supabase et fourni les clés LLM.

## 2. Découpage en phases (spec §12 mappée sur D1)

| Phase | Contenu | Livrable de fin |
|---|---|---|
| **P1 — Scaffold** | `apps/api` (uv, src layout), CI (ruff/pyright strict/import-linter/pytest), `core/` (config fail-fast, logging structlog, errors RFC 9457), `modal_app.py` | `pytest` vert, verrous qualité verts, healthcheck servable |
| **P2 — Socle data + auth + studies + web boot** | `core/db` (engine async, `SET LOCAL app.tenant_id`), `core/auth` (JWKS), `core/tenancy`, **Alembic = schéma complet + RLS**, module `studies` (CRUD + `study_state` versionné), client TS généré, migration `lucis-dashboard`→`apps/web` sans mocks, **bundle SQL Supabase** | front migré boote (login Supabase, liste d'études via API) ; `supabase/*.sql` exporté |
| **P3 — datasets + corpus** | `datasets` (upload, profiling colonnes, mapping), tables cohorte + seed, `corpus` (documents/chunks, feed, coverage, sources, `match_chunks` pgvector) | endpoints data du front servis sur Postgres seedé |
| **P4 — agents** | runtime Anthropic async typé ; `dag`, `gap-detection`, `variable-check` (forced-tool, Pydantic + retry réparation, `agent_cache`, `agent_runs`) ; `trace` E1 multi-tour SSE/NDJSON en dernier | golden tests de caractérisation verts contre les handlers JS |
| **P5 — simulation + jobs** | infra `jobs` (idempotence), bootstrap à la demande (port `run_bootstrap.py`), power analytique calibré par outcome (fix T4) | simulation à la demande + lecture résultats |
| **P6 — documents + analytics** | génération protocole/rapport (WeasyPrint/python-docx), `usage_events`, `outbox` audit, `admin-stats`, vues coûts tokens | dossiers exportables ; admin alimenté |
| **P7 — parité + bascule** | golden + e2e Playwright verts, tests d'isolation RLS, `lucis-dashboard` figé en démo pure | critère de bascule atteint |

Chaque phase reçoit son propre plan écrit (skill `writing-plans`) juste avant exécution, puis est exécutée en TDD avec commits atomiques (sans trailer co-author, préférence Quentin). Rapport à chaque frontière de phase.

## 3. Schéma de données complet (19 tables)

Toutes les tables tenant-scopées portent une policy RLS fondée sur `current_setting('app.tenant_id')`. `documents`/`chunks` ont `org_id` **nullable** ⇒ corpus global lisible par tous les tenants.

### Tenancy
- **orgs** — `id, name, slug, cesl_profile jsonb, created_at`. Sert `/api/tenant`.
- **memberships** — `id, org_id→orgs, user_id (auth.users), role(owner|member|viewer), created_at`.

### Studies
- **studies** — `id, org_id, name, slug, tagline, category, framework, n_subjects, lead, status, created_by, created_at, updated_at`. Remplace `cockpitData` + `augura_new_studies`.
- **study_members** — `id, study_id, user_id, role`.
- **study_state** — `id, study_id, version, state jsonb, created_by, created_at`. Remplace le `sessionStorage augura_session_v3_*` (profileReady, e1Profile, studyType, selectedEstimators, lockedEstimator, selectedOutcome, simResults, uploadedData, variableMappings, variableCheckResult, dagCache, cqExposure, cqPopulation…).

### Datasets
- **datasets** — `id, org_id, study_id?, name, storage_path, row_count, status, created_at`.
- **dataset_columns** — `id, dataset_id, sheet, name, value_kind, n_total, n_non_null, null_pct, n_distinct, min, max, top_values jsonb, proposed_role, proposed_group, proposed_canonical_id, confidence, rationale, user_decision(pending|confirmed|rejected), final_role, final_canonical_id`.
- **cohort_members** (= `validation_members`) — `id, org_id, dataset_id, cohort_name, member_id, age, sex, bmi, engagement_group, country`.
- **cohort_biomarkers** (= `validation_biomarkers`) — `id, org_id, dataset_id, cohort_name, member_id, timepoint_months, hba1c_pct, ldl_mgdl, hs_crp_mgl, adherence_pct`.

### Corpus
- **documents** — `id, org_id?, source_id, evidence_type, jurisdiction, lifecycle, title, summary, url, published_at, ingested_at, priority_score, is_new`. Sert `pulse-feed`, `coverage-map`, `corpus-sources`.
- **chunks** — `id, document_id, org_id?, content, embedding vector(1536), token_count`. Index **HNSW** sur `embedding`. Sert `match_chunks`.

### Agents
- **agent_runs** — `id, org_id, study_id?, agent_type, model, status, duration_ms, input_tokens, output_tokens, cost_usd, created_at`.
- **agent_cache** — `id, agent_type, input_hash unique, response jsonb, created_at` (fix U2 : agents déterministes servis depuis le cache).

### Simulation
- **simulation_runs** — `id, org_id, study_id, params jsonb, job_id?, status, results jsonb, created_at`. Bootstrap à la demande.
- **simulation_results** — `id, org_id, cohort_name, scenario, estimator, effect_size, ci_lower, ci_upper, power, p_value`. Read-model seedé pour le mode VALIDATED du front (3 scénarios × 4 estimateurs = 12 lignes).

### Jobs
- **jobs** — `id, org_id, type, status(queued|running|succeeded|failed), progress, payload jsonb, result_ref, error, idempotency_key unique, modal_call_id, created_at, updated_at`.

### Documents générés
- **generated_documents** — `id, org_id, study_id, type(protocol|report), storage_path, status, created_at`.

### Analytics / observabilité
- **usage_events** — `id, user_id?, org_id?, event_type, route, metadata jsonb, created_at`. Sert `admin-stats`.
- **outbox_events** — `id, aggregate_type, aggregate_id, event_type, payload jsonb, created_at, processed_at`. Audit trail.

### Fonctions / vues
- `match_chunks(query_embedding vector(1536), match_count int, filter jsonb)` — recherche pgvector.
- `coverage_map` — vue/agrégat (jurisdiction × evidence_type → doc_count, gap_score, gap_severity), incluant les cellules à zéro.

## 4. Contrat front → backend → table

| Front (mock actuel) | Endpoint FastAPI | Table(s) |
|---|---|---|
| `GET /api/tenant?projectId=` | `GET /orgs/{slug}` | `orgs.cesl_profile` |
| `GET /api/pulse-feed` | `GET /corpus/feed` (keyset) | `documents` |
| `GET /api/coverage-map` · `/api/corpus-sources` | `GET /corpus/coverage` · `/corpus/sources` | `documents` (agrégé) |
| `GET /api/study-designs` · `/api/cesl-sources` | `GET /catalogs/*` | catalogues statiques |
| `POST /api/dag` · `/gap-detection` · `/variable-check` | `POST /agents/{dag,gaps,variable-check}` | `agent_runs`, `agent_cache`, `study_state` |
| `POST /api/trace` (SSE) | `POST /agents/profiling/stream` (SSE NDJSON) | `agent_runs`, `study_state` |
| `POST /api/supabase` (match_chunks) | `POST /corpus/search` | `chunks` |
| `POST /api/anthropic` · `/api/openai` | internalisés (plus de proxy générique exposé au navigateur) | — |
| Supabase REST `validation_members/biomarkers` | `GET /datasets/{id}/cohort` | `cohort_*` |
| `simulation_results` (VALIDATED) | `GET /simulations/results` | `simulation_results` |
| `POST /simulations` (à la demande) | `POST /simulations` → `202 {job_id}` | `simulation_runs`, `jobs` |
| `sessionStorage augura_session_v3` | `GET/PUT /studies/{id}/state` | `study_state` |
| `GET /api/admin-stats` | `GET /analytics/admin` | `usage_events` |

## 5. Livrable Supabase (D2)

Alembic = source de vérité. Un bundle dérivé, prêt à coller dans un nouveau projet Supabase, est généré sous `apps/api/supabase/` :
- `schema.sql` — extensions (`pgvector`, `pgcrypto`), tables, index HNSW.
- `policies.sql` — policies RLS + rôle de connexion non exempt.
- `functions.sql` — `match_chunks`, vue `coverage_map`.
- `seed.sql` — corpus + cohorte + `simulation_results`, dérivés des données locales existantes.

Aucune base existante n'est touchée. Aucun Docker n'est lancé sur la machine de dev.

## 6. Stratégie de vérification (sous contraintes D1+D2)

- **Local** : pyright strict, ruff, import-linter, pytest (logique métier, validation Pydantic, agents à LLM mocké, parsing DDL).
- **CI (GitHub Actions)** : service `postgres` 16 + pgvector → tests repos + isolation RLS dédiés (un tenant ne lit jamais l'autre) ; application du bundle `supabase/*.sql` sur ce Postgres pour prouver qu'il est valide.
- **Caractérisation** : `src/mocks/apiFixtures.js` → golden files ; le FastAPI doit répondre la même chose que les routes JS (écarts listés et assumés).
- **Agents** : clés `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` requises pour un run live ; absentes du `.env.local` actuel ⇒ validés structurellement jusqu'à fourniture.

## 7. Hors périmètre de cette livraison

Inchangé par rapport à la spec §13. En plus : pas de déploiement Modal live tant que l'utilisateur n'a pas authentifié Modal (le `modal_app.py` est livré et prêt).
