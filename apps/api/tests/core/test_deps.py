"""Regression guard on the dependency chain (Bearer → tenant → session).

The membership query lived inline in `get_current_tenant` with no coverage at all:
a `:org::uuid` mis-parsed by `text()` crashed *every* authenticated request with a
500, a bug invisible to the tests (which stopped at the 401). Here we pin the query
compilation, without a database.
"""

from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from augura_api.core.deps import membership_lookup_stmt, require_role
from augura_api.core.errors import ForbiddenError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant

_T = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
_U = UserId(UUID("11111111-1111-4111-8111-111111111111"))


def _tenant(role: str) -> CurrentTenant:
    return CurrentTenant(tenant_id=_T, user_id=_U, role=role)


@pytest.mark.parametrize(
    "requested_org",
    [None, TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))],
    ids=["no-org", "with-org"],
)
def test_membership_lookup_stmt_compiles(requested_org: TenantId | None) -> None:
    """With or without a requested org, the query compiles under the PostgreSQL dialect
    and properly declares the bound parameter `org` (the regression raised ArgumentError)."""
    stmt = membership_lookup_stmt(requested_org)
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcaststring": True}
    )
    sql = str(compiled)
    assert "cast(" in sql.lower()  # cast(:org as uuid), not :org::uuid
    assert "org" in compiled.params
    expected = str(requested_org) if requested_org else None
    assert compiled.params["org"] == expected


async def test_require_role_allows_listed_role() -> None:
    """The allowed role passes through the dependency (the tenant is returned as-is)."""
    dep = require_role("owner")
    out = await dep(_tenant("owner"))
    assert out.role == "owner"


@pytest.mark.parametrize("role", ["member", "viewer"])
async def test_require_role_forbids_other_roles(role: str) -> None:
    """An unlisted role (member/viewer) is rejected with 403 — guard on /analytics/admin."""
    dep = require_role("owner")
    with pytest.raises(ForbiddenError):
        await dep(_tenant(role))
