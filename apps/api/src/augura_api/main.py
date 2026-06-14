from fastapi import FastAPI

from augura_api.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings if settings is not None else get_settings()
    app = FastAPI(title=cfg.app_name, version=cfg.version)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.env, "version": cfg.version}

    return app
