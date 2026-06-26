"""require_role('owner','member') rejects a viewer (RBAC write-gating)."""

from uuid import uuid4

import pytest

from augura_api.core.deps import require_role
from augura_api.core.errors import ForbiddenError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant


def _tenant(role: str) -> CurrentTenant:
    return CurrentTenant(tenant_id=TenantId(uuid4()), user_id=UserId(uuid4()), role=role)


async def test_viewer_blocked_from_write() -> None:
    dep = require_role("owner", "member")
    with pytest.raises(ForbiddenError):
        await dep(_tenant("viewer"))


async def test_member_allowed_write() -> None:
    dep = require_role("owner", "member")
    out = await dep(_tenant("member"))
    assert out.role == "member"


async def test_owner_allowed_write() -> None:
    dep = require_role("owner", "member")
    out = await dep(_tenant("owner"))
    assert out.role == "owner"
