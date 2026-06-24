"""POST /analytics/events/login records an attributed login event.

The endpoint derives user_id + org_id from the authenticated context (never the
client), and best-effort accepts an optional route. We assert it reaches
analytics.log_usage with server-trusted identity by overriding the auth + session
dependencies (no real DB needed).

Note: router.py uses a lazy import of log_usage (inside the handler) to avoid a
circular import with analytics/__init__.py. The monkeypatch therefore targets the
function at its definition site (augura_api.modules.analytics.log_usage)."""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

import httpx
import pytest

import augura_api.modules.analytics as analytics_mod
from augura_api.core.deps import get_current_tenant, get_session
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.main import create_app

TENANT = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


async def test_login_event_is_attributed(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    async def fake_log_usage(  # pyright: ignore[reportUnusedFunction]
        session: object,
        *,
        tenant_id: TenantId,
        user_id: UserId | None,
        event_type: str,
        route: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        recorded["tenant_id"] = tenant_id
        recorded["user_id"] = user_id
        recorded["event_type"] = event_type
        recorded["route"] = route

    # The router lazily imports log_usage from augura_api.modules.analytics at call
    # time — patch it at the definition site so both the lazy import and this patch
    # resolve to the same name.
    monkeypatch.setattr(analytics_mod, "log_usage", fake_log_usage, raising=True)

    app = create_app()

    async def _tenant() -> CurrentTenant:
        return CurrentTenant(tenant_id=TENANT, user_id=USER, role="member")

    async def _session() -> AsyncGenerator[object, None]:
        yield object()

    app.dependency_overrides[get_current_tenant] = _tenant
    app.dependency_overrides[get_session] = _session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/analytics/events/login", json={"route": "/studies"})

    assert r.status_code == 204
    assert recorded["event_type"] == "login"
    assert recorded["user_id"] == USER
    assert recorded["tenant_id"] == TENANT
    assert recorded["route"] == "/studies"


async def test_login_event_rejects_spoofed_identity_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client cannot smuggle user_id/event_type into the audit trail: the schema
    forbids extra fields, so a spoofed body is rejected (422) before log_usage runs."""
    called = False

    async def fake_log_usage(  # pyright: ignore[reportUnusedFunction]
        session: object, **_kwargs: Any
    ) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(analytics_mod, "log_usage", fake_log_usage, raising=True)

    app = create_app()

    async def _tenant() -> CurrentTenant:
        return CurrentTenant(tenant_id=TENANT, user_id=USER, role="member")

    async def _session() -> AsyncGenerator[object, None]:
        yield object()

    app.dependency_overrides[get_current_tenant] = _tenant
    app.dependency_overrides[get_session] = _session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/analytics/events/login",
            json={
                "route": "/x",
                "user_id": "00000000-0000-4000-8000-000000000000",
                "event_type": "admin",
            },
        )

    assert r.status_code == 422
    assert called is False
