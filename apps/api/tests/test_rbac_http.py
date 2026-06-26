"""HTTP-level proof that RBAC write-gating is wired: a viewer is 403'd on a mutating route
BEFORE the endpoint body runs (the require_role('owner','member') dependency fires).

DB-free: the auth + session dependencies are overridden, so the only thing under test is
that the gated routes carry the write-gating dependency."""

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx

from augura_api.core.deps import get_current_tenant, get_session
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.main import create_app


def _viewer() -> CurrentTenant:
    return CurrentTenant(tenant_id=TenantId(uuid4()), user_id=UserId(uuid4()), role="viewer")


async def _session() -> AsyncIterator[object]:
    yield object()


async def test_viewer_blocked_on_mutating_routes() -> None:
    app = create_app()
    app.dependency_overrides[get_current_tenant] = _viewer
    app.dependency_overrides[get_session] = _session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # No-body / path-only mutating routes carrying WriteTenantDep: the role gate
        # raises 403 before any session/DB work, so a viewer cannot mutate.
        clear = await client.delete("/corpus/literature/sessions")
        delete_one = await client.request("DELETE", f"/corpus/literature/sessions/{uuid4()}")

    assert clear.status_code == 403
    assert delete_one.status_code == 403


async def test_viewer_not_blocked_on_pure_compute_causal_dag() -> None:
    """POST /causal/dag is read+compute (no persistence) — it must NOT be write-gated, so a
    viewer is not 403'd. Regression guard for the over-gating fixed after the Phase-2 audit."""
    app = create_app()
    app.dependency_overrides[get_current_tenant] = _viewer
    app.dependency_overrides[get_session] = _session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # With no role gate, a viewer passes auth; the request then fails later (422 bad body
        # or 503 no LLM key) — never 403. If /causal/dag were write-gated, a viewer would 403.
        r = await client.post("/causal/dag", json={})

    assert r.status_code != 403
