# pyright: reportUnknownMemberType=false
# Justification (spec §9) : les décorateurs de la lib `modal` sont partiellement typés
# (stubs incomplets). Ce fichier est de la glue de déploiement, hors `src/` ; il est
# couvert par ruff et n'est pas dans l'`include` pyright de la CI.
import modal
from fastapi import FastAPI

# Phase 1 : deps runtime listées explicitement (3 paquets).
# Phase 2+ : basculer sur la synchro uv.lock quand la liste grossit.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi", "pydantic-settings", "structlog")
    .env({"AUGURA_ENV": "dev"})  # en prod : modal.Secret, pas une env d'image
    .add_local_python_source("augura_api")
)

app = modal.App("augura-api")


@app.function(image=image)
@modal.asgi_app()
def api() -> FastAPI:
    from augura_api.main import create_app

    return create_app()
