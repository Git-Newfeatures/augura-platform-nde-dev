# CLAUDE.md

Guide opérationnel du repo pour Claude Code. Pour la conception détaillée, voir [DESIGN.md](DESIGN.md) et `docs/specs/`.

## C'est quoi

Augura — plateforme de conception d'études cliniques. Monorepo :

| Chemin | Rôle | Stack | Déploiement |
|---|---|---|---|
| `apps/api` | Backend (monolithe modulaire) | FastAPI · SQLAlchemy async · asyncpg · Pydantic · `uv` | **Modal** |
| `apps/web` | Frontend | React 19 · Vite · Tailwind 4 · radix-ui · react-router 7 · `npm` | **Vercel** (branche `Quentin`) |
| `packages/api-client` | Client TS généré depuis l'OpenAPI | openapi-typescript / openapi-fetch | — |
| `docs/specs` | Architecture validée | — | — |

DB = **Supabase Postgres** (projet prod `Augura_Prod`, ref `fqmoylmvjoafihiuiiuj`, us-east-2). Auth = **Supabase Auth** (JWT). LLM = Anthropic / OpenAI. Littérature = PubMed/NCBI.

## Commandes

### Backend (`cd apps/api`, gestionnaire = `uv`)
```bash
uv sync --dev                                   # install
uv run uvicorn 'augura_api.main:create_app' --factory --reload   # serveur local (create_app est une factory)
uv run pytest -q                                # tests (les tests @pytest.mark.integration exigent AUGURA_DATABASE_URL)
uv run ruff format --check . && uv run ruff check .   # format + lint
uv run pyright                                  # types (strict)
uv run lint-imports                             # contrats d'architecture (import-linter)
uv run alembic upgrade head                     # migrations
bash scripts/deploy_modal.sh                    # déploie sur Modal (recrée le secret `augura-api` depuis .env)
uv run python scripts/verify_supabase.py        # vérifie la DB live
uv run python scripts/dump_openapi.py           # régénère packages/api-client/openapi.json
```
La CI lance exactement : `ruff format --check`, `ruff check`, `pyright`, `lint-imports`, `pytest` (`.github/workflows/ci.yml`). **Fais-les passer avant de pousser.**

### Frontend (`cd apps/web`, gestionnaire = `npm`)
```bash
npm install
npm run dev      # Vite sur http://localhost:5173
npm run build
npm run lint     # eslint
```

### Client API (après tout changement de contrat backend)
```bash
uv run python apps/api/scripts/dump_openapi.py            # → packages/api-client/openapi.json
npm --prefix packages/api-client run generate             # → src/schema.d.ts (NE JAMAIS éditer à la main)
```
La CI fait un **drift-check** : si l'OpenAPI a changé sans régénérer, elle casse.

## Architecture (résumé)

- **Backend = monolithe modulaire.** Chaque module est une **tranche verticale** sous `src/augura_api/modules/<nom>/` : `router.py` (HTTP) → `service.py` (logique) → `repo.py` (SQLAlchemy, scopé tenant) → `models.py` / `schemas.py`. Convention DI : `XService(XRepo(session))`. Détails : `apps/api/src/augura_api/modules/README.md`.
- **Modules** : `studies, corpus, datasets, dq, mapping, documents, simulation, analytics, reference, jobs, agents, semantic` (B1 — ontologie/causal, `GET /semantic/relations`), `causal` (B2 — `POST /causal/dag`). Tous montés dans `main.py:create_app()`.
- **`core/`** (transverse, indépendant des modules) : `auth.py` (JWT Supabase → `Principal`), `tenancy.py` (résolution tenant via `memberships`), `deps.py` (`CurrentTenantDep`, `SessionDep`, `require_role`), `db.py` (GUCs RLS), `config.py` (settings `AUGURA_*`), `errors.py`, `logging.py`, `storage.py`, `llm/`.
- **Frontend** : `src/shell/sections.js` = source unique de la nav top-level ; `src/workspace/*` = pages (DatasetsPage, SemanticLayerPage, CausalModelingPage…) ; `src/LucisApp.jsx` = workspace par étude ; `src/api.js` = fetch + `Authorization: Bearer <JWT Supabase>` ; `src/supabase.js` = client auth.

## Multi-tenancy & RLS (à comprendre avant de toucher aux routes/DB)

- Le JWT **ne porte pas** d'org. Le tenant est résolu **par requête** : `memberships` (clé `user_id`) → `Membership{org_id, role}`. Pas de membership ⇒ **403 « aucune appartenance »**.
- RLS Postgres pilotée par GUCs transaction-local `app.user_id` / `app.tenant_id` (posés dans `core/db.py`, lus par les policies `supabase/policies.sql`).
- Gating par rôle : seul **analytics** exige `owner` (`require_role("owner")`) ; tout le reste passe par `CurrentTenantDep` + `SessionDep`.

## Bundle DB & migrations (invariants — ne pas casser)

- Le schéma vit dans `apps/api/supabase/` : `schema.sql` (tables), `functions.sql`, `policies.sql` (RLS), `seed.sql` (catalogues de référence — **aucune donnée de démo**).
- `alembic 0001_baseline` applique `schema.sql`+`functions.sql`+`policies.sql`. **Les migrations `0002+` DOIVENT être idempotentes** (`CREATE … IF NOT EXISTS`, `DROP … IF EXISTS`).
- `seed.sql` est appliqué **séparément** (ni par alembic, ni par le déploiement Modal).
- La CI (`db-bundle`) prouve sur un vrai Postgres+pgvector que le bundle se crée, que le seed entre, et que l'isolation RLS tient.

## Pièges (vécus, à retenir)

- **Le déploiement Modal ne lance NI migrations NI seed.** Applique-les à la DB live à part.
- **`apps/api/.env` `AUGURA_DATABASE_URL` utilise le rôle applicatif `augura_api`** (non-privilégié, non-BYPASSRLS) et **`psql` n'est pas installé** localement. Toute opération DB privilégiée (DDL, policies, `insert into orgs`) passe par le **MCP Supabase** (`execute_sql`, project `fqmoylmvjoafihiuiiuj`) ou le SQL editor Supabase.
- Une table ajoutée à `schema.sql` (même en `IF NOT EXISTS`) **contourne alembic** : sur une DB déjà migrée, il faut l'appliquer à la main.
- **Pas de mock/fallback/démo dans `apps/web`** : tout vient du backend réel.
- Front : si `VITE_API_URL` n'est pas défini, l'API base **retombe sur le backend Modal de prod** (`apps/web/src/api.js`).
- En **prod**, `AUGURA_CORS_ORIGINS` ou `AUGURA_CORS_ORIGIN_REGEX` doit être défini explicitement (fail-fast au boot, cf. `core/config.py`).

## Variables d'environnement

- **Backend (préfixe `AUGURA_`)** : `AUGURA_ENV` (`dev`|`prod`), `AUGURA_DATABASE_URL`, `AUGURA_CORS_ORIGINS` / `AUGURA_CORS_ORIGIN_REGEX`, `AUGURA_SUPABASE_JWKS_URL` **ou** `AUGURA_SUPABASE_JWT_SECRET` (+ `…_AUDIENCE`, `…_ISSUER`), `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `NCBI_API_KEY` (acceptés avec ou sans préfixe `AUGURA_`), `AUGURA_ARTIFACTS_DIR`.
- **Frontend (préfixe `VITE_`)** : `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` (optionnel).

## Conventions

- **Commentaires et docstrings en français** (suis le style existant).
- Contrats `import-linter` (dans `pyproject.toml`) : `core` n'importe jamais `modules`/`jobs` ; les modules de données (`studies`/`corpus`/`datasets`) sont mutuellement indépendants. `uv run lint-imports` les vérifie.
- ruff : ligne 100, règles `E,F,I,UP,B,SIM,TID252`. pyright : `strict`.
- Ne commit/push/déploie **que sur demande** explicite.
