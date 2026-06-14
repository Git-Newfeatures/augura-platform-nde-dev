"""Câblage du module studies dans l'app (sans base : auth échoue avant la DB)."""

import httpx

from augura_api.main import create_app


def test_openapi_exposes_studies_routes() -> None:
    paths = create_app().openapi()["paths"]
    assert "/studies" in paths
    assert "/studies/{study_id}" in paths
    assert "/studies/{study_id}/state" in paths


async def test_studies_requires_auth() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/studies")
    assert r.status_code == 401
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "unauthorized"
