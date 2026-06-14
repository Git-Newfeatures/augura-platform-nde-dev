from uuid import uuid4

import pytest

from augura_api.core.auth import Principal
from augura_api.core.errors import ForbiddenError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import Membership, resolve_tenant


def _principal() -> Principal:
    return Principal(user_id=UserId(uuid4()), email="u@augura.dev", claims={})


async def test_resolve_tenant_returns_membership_org() -> None:
    org = TenantId(uuid4())

    async def lookup(_user: UserId, _org: TenantId | None) -> Membership:
        return Membership(org_id=org, role="owner")

    tenant = await resolve_tenant(_principal(), lookup=lookup)
    assert tenant.tenant_id == org
    assert tenant.role == "owner"


async def test_resolve_tenant_forbidden_without_membership() -> None:
    async def lookup(_user: UserId, _org: TenantId | None) -> None:
        return None

    with pytest.raises(ForbiddenError):
        await resolve_tenant(_principal(), lookup=lookup)
