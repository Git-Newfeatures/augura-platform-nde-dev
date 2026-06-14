from fastapi import FastAPI

from augura_api.core.config import Settings, get_settings
from augura_api.core.logging import RequestIdMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(title=cfg.app_name, version=cfg.version)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.env, "version": cfg.version}

    return app
