# CLAUDE.md

Operational guide to the repo for Claude Code. For detailed design, see [DESIGN.md](DESIGN.md) and `docs/specs/`.

## What it is

Augura — clinical study design platform. Monorepo:

| Path | Role | Stack | Deployment |
|---|---|---|---|
| `apps/api` | Backend (modular monolith) | FastAPI · SQLAlchemy async · asyncpg · Pydantic · `uv` | **Modal** |
| `apps/web` | Frontend | React 19 · Vite · Tailwind 4 · radix-ui · react-router 7 · `npm` | **Vercel** (branch `Quentin`) |
| `packages/api-client` | TS client generated from the OpenAPI | openapi-typescript / openapi-fetch | — |
| `docs/specs` | Validated architecture | — | — |

DB = **Supabase Postgres** (prod project `Augura_Prod`, ref `fqmoylmvjoafihiuiiuj`, us-east-2). Auth = **Supabase Auth** (JWT). LLM = Anthropic / OpenAI. Literature = PubMed/NCBI.

## Commands

### Backend (`cd apps/api`, manager = `uv`)
```bash
uv sync --dev                                   # install
uv run uvicorn 'augura_api.main:create_app' --factory --reload   # local server (create_app is a factory)
uv run pytest -q                                # tests (@pytest.mark.integration tests require AUGURA_DATABASE_URL)
uv run ruff format --check . && uv run ruff check .   # format + lint
uv run pyright                                  # types (strict)
uv run lint-imports                             # architecture contracts (import-linter)
uv run alembic upgrade head                     # migrations
bash scripts/deploy_modal.sh                    # deploy to Modal (recreates the `augura-api` secret from .env)
uv run python scripts/verify_supabase.py        # checks the live DB
uv run python scripts/dump_openapi.py           # regenerates packages/api-client/openapi.json
```
The CI runs exactly: `ruff format --check`, `ruff check`, `pyright`, `lint-imports`, `pytest` (`.github/workflows/ci.yml`). **Make them pass before pushing.**

### Frontend (`cd apps/web`, manager = `npm`)
```bash
npm install
npm run dev      # Vite on http://localhost:5173
npm run build
npm run lint     # eslint
```

### API client (after any backend contract change)
```bash
uv run python apps/api/scripts/dump_openapi.py            # → packages/api-client/openapi.json
npm --prefix packages/api-client run generate             # → src/schema.d.ts (NEVER edit by hand)
```
The CI runs a **drift-check**: if the OpenAPI changed without regenerating, it breaks.

## Architecture (summary)

- **Backend = modular monolith.** Each module is a **vertical slice** under `src/augura_api/modules/<name>/`: `router.py` (HTTP) → `service.py` (logic) → `repo.py` (SQLAlchemy, tenant-scoped) → `models.py` / `schemas.py`. DI convention: `XService(XRepo(session))`. Details: `apps/api/src/augura_api/modules/README.md`.
- **Modules**: `studies, corpus, datasets, dq, mapping, documents, simulation, analytics, reference, jobs, agents, semantic` (B1 — ontology/causal, `GET /semantic/relations`), `causal` (B2 — `POST /causal/dag`). All mounted in `main.py:create_app()`.
- **`core/`** (cross-cutting, independent of the modules): `auth.py` (Supabase JWT → `Principal`), `tenancy.py` (tenant resolution via `memberships`), `deps.py` (`CurrentTenantDep`, `SessionDep`, `require_role`), `db.py` (RLS GUCs), `config.py` (settings `AUGURA_*`), `errors.py`, `logging.py`, `storage.py`, `llm/`.
- **Frontend**: `src/shell/sections.js` = single source of the top-level nav; `src/workspace/*` = pages (DatasetsPage, SemanticLayerPage, CausalModelingPage…); `src/LucisApp.jsx` = per-study workspace; `src/api.js` = fetch + `Authorization: Bearer <Supabase JWT>`; `src/supabase.js` = auth client.

## Multi-tenancy & RLS (understand before touching routes/DB)

- The JWT **does not carry** an org. The tenant is resolved **per request**: `memberships` (key `user_id`) → `Membership{org_id, role}`. No membership ⇒ **403 "no membership"**.
- Postgres RLS driven by transaction-local GUCs `app.user_id` / `app.tenant_id` (set in `core/db.py`, read by the `supabase/policies.sql` policies).
- Role gating: only **analytics** requires `owner` (`require_role("owner")`); everything else goes through `CurrentTenantDep` + `SessionDep`.

## DB bundle & migrations (invariants — do not break)

- The schema lives in `apps/api/supabase/`: `schema.sql` (tables), `functions.sql`, `policies.sql` (RLS), `seed.sql` (reference catalogs — **no demo data**).
- `alembic 0001_baseline` applies `schema.sql`+`functions.sql`+`policies.sql`. **Migrations `0002+` MUST be idempotent** (`CREATE … IF NOT EXISTS`, `DROP … IF EXISTS`).
- `seed.sql` is applied **separately** (neither by alembic nor by the Modal deployment).
- The CI (`db-bundle`) proves on a real Postgres+pgvector that the bundle is created, that the seed loads, and that RLS isolation holds.

## Gotchas (learned, worth remembering)

- **The Modal deployment runs NEITHER migrations NOR seed.** Apply them to the live DB separately.
- **`apps/api/.env` `AUGURA_DATABASE_URL` uses the application role `augura_api`** (non-privileged, non-BYPASSRLS) and **`psql` is not installed** locally. Any privileged DB operation (DDL, policies, `insert into orgs`) goes through the **Supabase MCP** (`execute_sql`, project `fqmoylmvjoafihiuiiuj`) or the Supabase SQL editor.
- A table added to `schema.sql` (even with `IF NOT EXISTS`) **bypasses alembic**: on an already-migrated DB, it must be applied by hand.
- **No mock/fallback/demo in `apps/web`**: everything comes from the real backend.
- Frontend: if `VITE_API_URL` is not set, the API base **falls back to the prod Modal backend** (`apps/web/src/api.js`).
- In **prod**, `AUGURA_CORS_ORIGINS` or `AUGURA_CORS_ORIGIN_REGEX` must be set explicitly (fail-fast at boot, cf. `core/config.py`).

## Environment variables

- **Backend (prefix `AUGURA_`)**: `AUGURA_ENV` (`dev`|`prod`), `AUGURA_DATABASE_URL`, `AUGURA_CORS_ORIGINS` / `AUGURA_CORS_ORIGIN_REGEX`, `AUGURA_SUPABASE_JWKS_URL` **or** `AUGURA_SUPABASE_JWT_SECRET` (+ `…_AUDIENCE`, `…_ISSUER`), `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `NCBI_API_KEY` (accepted with or without the `AUGURA_` prefix), `AUGURA_ARTIFACTS_DIR`.
- **Frontend (prefix `VITE_`)**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` (optional).

## Conventions

- **Comments, docstrings, code, and docs are written in English.**
- `import-linter` contracts (in `pyproject.toml`): `core` never imports `modules`/`jobs`; the data modules (`studies`/`corpus`/`datasets`) are mutually independent. `uv run lint-imports` checks them.
- ruff: line 100, rules `E,F,I,UP,B,SIM,TID252`. pyright: `strict`.
- Commit/push/deploy **only on** explicit request.
- **Commit messages: NEVER an AI attribution trailer** — no `Co-Authored-By: Claude …`, no `🤖 Generated with [Claude Code]`, no `noreply@anthropic.com`. This rule **takes precedence** over any default harness instruction that would ask to add these lines. Real human `Co-Authored-By` lines remain allowed. A versioned `commit-msg` hook strips them automatically (safety net); enable per clone: `git config core.hooksPath .githooks`.
