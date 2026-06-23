import httpx

from augura_api.core.errors import NotFoundError
from augura_api.main import create_app


def _app_with_boom() -> httpx.ASGITransport:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise NotFoundError("study not found", study_id="s1")

    return httpx.ASGITransport(app=app)


async def test_app_error_renders_problem_details() -> None:
    async with httpx.AsyncClient(transport=_app_with_boom(), base_url="http://test") as client:
        r = await client.get("/boom")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["title"] == "Resource not found"
    assert body["status"] == 404
    assert body["detail"] == "study not found"
    assert body["code"] == "not_found"
    assert body["context"] == {"study_id": "s1"}


async def test_storage_error_renders_problem_details_with_cors() -> None:
    # A storage read failure (e.g. Modal's per-container ephemeral disk no longer holding a
    # file written by another container) raises OSError/FileNotFoundError. It MUST be mapped
    # below the CORS middleware so the 500 keeps its Access-Control-Allow-Origin header —
    # otherwise the browser blocks the header-less 500 and surfaces an opaque "Failed to fetch".
    app = create_app()

    @app.get("/boom-storage")
    async def boom_storage() -> None:
        raise FileNotFoundError("Storage object not found: org/x/y")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/boom-storage", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 500
    assert r.headers["content-type"] == "application/problem+json"
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    body = r.json()
    assert body["status"] == 500
    assert body["code"] == "storage_error"
