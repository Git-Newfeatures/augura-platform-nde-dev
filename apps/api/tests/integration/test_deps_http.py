"""HTTP regression guard for the full dependency chain, on a real Postgres.

Skipped if AUGURA_DATABASE_URL is not set. We only stub out JWT verification
(`get_principal`) to inject a user; everything else — `memberships` resolution,
RLS-scoped session, repo — runs for real. This is exactly the path that returned
500 when the membership query did not compile. The database is no longer seeded:
we check that the chain returns 200 (an empty list is acceptable), not a specific
demo payload.
"""

import os
from uuid import UUID

import httpx
import pytest

from augura_api.core.auth import Principal
from augura_api.core.deps import get_principal
from augura_api.core.ids import UserId
from augura_api.main import create_app

pytestmark = pytest.mark.integration

TEST_USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


async def test_authenticated_studies_runs_full_deps_chain() -> None:
    if not os.environ.get("AUGURA_DATABASE_URL"):
        pytest.skip("AUGURA_DATABASE_URL not set — integration test skipped")

    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=TEST_USER, email="test@augura.test", claims={}
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/studies")

    # 500 = deps-chain regression. The body may be an empty list.
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
