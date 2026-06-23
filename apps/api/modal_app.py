# pyright: reportUnknownMemberType=false
# Rationale (spec §9): the `modal` library decorators are partially typed
# (incomplete stubs). This file is deployment glue, outside `src/`; it is
# covered by ruff and is not in the CI's pyright `include`.
from pathlib import Path

import modal
from fastapi import FastAPI

# Runtime image: we install ALL of the project's dependencies from pyproject.toml
# (single source of truth — no duplicated list). Indispensable: create_app()
# imports the routers, which pull in sqlalchemy/asyncpg/pyjwt/anthropic…; a minimal
# image would crash at import. The application code is added separately via
# add_local_python_source (pip installs the deps, not the augura_api package itself).
_PYPROJECT = Path(__file__).parent / "pyproject.toml"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject(str(_PYPROJECT))
    .add_local_python_source("augura_api")
)

app = modal.App("augura-api")

# Prod config injected via a Modal secret (NOT a frozen image env). Must contain
# at minimum: AUGURA_ENV=prod, AUGURA_DATABASE_URL, AUGURA_CORS_ORIGINS (Vercel
# front-end origin(s)), and AUGURA_SUPABASE_JWT_SECRET or AUGURA_SUPABASE_JWKS_URL for
# JWT verification; AUGURA_ANTHROPIC_API_KEY/OPENAI/NCBI depending on enabled agents.
# Out-of-bundle creation:
#   modal secret create augura-api AUGURA_ENV=prod AUGURA_DATABASE_URL=… …
_secret = modal.Secret.from_name("augura-api")


@app.function(image=image, secrets=[_secret])
@modal.asgi_app()
def api() -> FastAPI:
    from augura_api.main import create_app

    return create_app()


# Jobs worker (long-running tasks: semantic enrichment, bootstrap, documents).
# Spawned by `jobs.runner.enqueue_job` (`run_job.spawn(...)`) FROM the ASGI container:
# runs in a dedicated container, writes its result IN THE DATABASE (never on ephemeral disk)
# and progresses via short transactions — polling `/jobs/{id}` sees it advance.
# Generous timeout: an enrichment run chains several LLM calls.
@app.function(image=image, secrets=[_secret], timeout=900)
def run_job(tenant_id: str, user_id: str, job_id: str) -> None:
    import asyncio
    from uuid import UUID

    from augura_api.core.config import get_settings
    from augura_api.core.ids import TenantId, UserId
    from augura_api.jobs.runner import execute_job

    asyncio.run(
        execute_job(
            get_settings(),
            TenantId(UUID(tenant_id)),
            UserId(UUID(user_id)),
            UUID(job_id),
        )
    )
