# pyright: reportUnknownMemberType=false
# Justification (spec §9) : les décorateurs de la lib `modal` sont partiellement typés
# (stubs incomplets). Ce fichier est de la glue de déploiement, hors `src/` ; il est
# couvert par ruff et n'est pas dans l'`include` pyright de la CI.
from pathlib import Path

import modal
from fastapi import FastAPI

# Image runtime : on installe TOUTES les dépendances du projet depuis pyproject.toml
# (source de vérité unique — pas de liste dupliquée). Indispensable : create_app()
# importe les routers qui tirent sqlalchemy/asyncpg/pyjwt/anthropic… ; une image
# minimale planterait à l'import. Le code applicatif est ajouté à part via
# add_local_python_source (pip installe les deps, pas le package augura_api lui-même).
_PYPROJECT = Path(__file__).parent / "pyproject.toml"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject(str(_PYPROJECT))
    .add_local_python_source("augura_api")
)

app = modal.App("augura-api")

# Config prod injectée par un secret Modal (PAS une env d'image figée). Doit contenir
# au minimum : AUGURA_ENV=prod, AUGURA_DATABASE_URL, AUGURA_CORS_ORIGINS (origine(s)
# du front Vercel), et AUGURA_SUPABASE_JWT_SECRET ou AUGURA_SUPABASE_JWKS_URL pour la
# vérif JWT ; AUGURA_ANTHROPIC_API_KEY/OPENAI/NCBI selon les agents activés.
# Création hors-bundle :
#   modal secret create augura-api AUGURA_ENV=prod AUGURA_DATABASE_URL=… …
_secret = modal.Secret.from_name("augura-api")


@app.function(image=image, secrets=[_secret])
@modal.asgi_app()
def api() -> FastAPI:
    from augura_api.main import create_app

    return create_app()


# Worker de jobs (traitements longs : enrichissement sémantique, bootstrap, dossiers).
# Spawné par `jobs.runner.enqueue_job` (`run_job.spawn(...)`) DEPUIS le conteneur ASGI :
# tourne dans un conteneur dédié, écrit son résultat EN BASE (jamais sur disque éphémère)
# et progresse par transactions courtes — le polling `/jobs/{id}` le voit avancer.
# timeout généreux : un run d'enrichissement enchaîne plusieurs appels LLM.
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
