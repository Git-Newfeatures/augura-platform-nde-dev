import httpx

from augura_api.core.config import Settings
from augura_api.main import create_app


async def test_security_headers_present_in_prod() -> None:
    cfg = Settings(  # pyright: ignore[reportCallIssue]
        env="prod",
        cors_origins="https://app.augura.io",
        supabase_url="https://proj.supabase.co",
        supabase_service_role_key="svc",
    )
    app = create_app(cfg)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz")
    assert r.headers["strict-transport-security"].startswith("max-age=")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers


async def test_no_hsts_in_dev() -> None:
    app = create_app()  # dev
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz")
    assert "strict-transport-security" not in r.headers
