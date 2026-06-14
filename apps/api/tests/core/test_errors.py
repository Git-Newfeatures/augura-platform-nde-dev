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
