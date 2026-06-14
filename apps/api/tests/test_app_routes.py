"""Câblage du module studies dans l'app (sans base : auth échoue avant la DB)."""

import httpx

from augura_api.main import create_app


def test_openapi_exposes_routes() -> None:
    paths = create_app().openapi()["paths"]
    for path in (
        "/studies",
        "/studies/{study_id}",
        "/studies/{study_id}/state",
        "/corpus/feed",
        "/corpus/coverage",
        "/corpus/sources",
        "/corpus/search",
    ):
        assert path in paths, path


async def test_protected_routes_require_auth() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/studies", "/corpus/feed", "/corpus/coverage", "/corpus/sources"):
            r = await client.get(path)
            assert r.status_code == 401, path
            assert r.headers["content-type"] == "application/problem+json"
            assert r.json()["code"] == "unauthorized"
