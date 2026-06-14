from fastapi import FastAPI

from augura_api.core.config import Settings, get_settings
from augura_api.core.errors import register_error_handlers
from augura_api.core.logging import RequestIdMiddleware, configure_logging
from augura_api.modules.corpus import router as corpus_router
from augura_api.modules.studies import router as studies_router


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(title=cfg.app_name, version=cfg.version)
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.env, "version": cfg.version}

    app.include_router(studies_router)
    app.include_router(corpus_router)

    return app
