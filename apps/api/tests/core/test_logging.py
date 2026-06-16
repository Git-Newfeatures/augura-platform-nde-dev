import httpx

from augura_api.main import create_app


async def _get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_response_carries_generated_request_id() -> None:
    r = await _get("/healthz")
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) == 32  # uuid4().hex


async def test_incoming_request_id_is_preserved() -> None:
    r = await _get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
