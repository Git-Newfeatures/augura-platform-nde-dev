from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from augura_api.core.config import Settings, get_settings
from augura_api.core.errors import register_error_handlers
from augura_api.core.logging import RequestIdMiddleware, configure_logging
from augura_api.modules.agents import router as agents_router
from augura_api.modules.analytics import router as analytics_router
from augura_api.modules.corpus import router as corpus_router
from augura_api.modules.datasets import router as datasets_router
from augura_api.modules.documents import router as documents_router
from augura_api.modules.dq import router as dq_router
from augura_api.modules.jobs import router as jobs_router
from augura_api.modules.mapping import router as mapping_router
from augura_api.modules.reference import router as reference_router
from augura_api.modules.semantic import router as semantic_router
from augura_api.modules.simulation import router as simulation_router
from augura_api.modules.studies import router as studies_router


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(title=cfg.app_name, version=cfg.version)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.env, "version": cfg.version}

    app.include_router(studies_router)
    app.include_router(corpus_router)
    app.include_router(datasets_router)
    app.include_router(agents_router)
    app.include_router(simulation_router)
    app.include_router(jobs_router)
    app.include_router(mapping_router)
    app.include_router(documents_router)
    app.include_router(dq_router)
    app.include_router(analytics_router)
    app.include_router(reference_router)
    app.include_router(semantic_router)

    return app
