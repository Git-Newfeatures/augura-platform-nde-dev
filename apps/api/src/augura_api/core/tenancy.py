"""Resolution of the current tenant from the authenticated user (spec §7).

`resolve_tenant` maps a `Principal` (from `core.auth`) to the `CurrentTenant`
via the `memberships` table. The lookup is injected (`MembershipLookup`) to
stay testable without a database; the FastAPI dependency wiring comes with the routes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from augura_api.core.auth import Principal
from augura_api.core.errors import ForbiddenError
from augura_api.core.ids import TenantId, UserId


@dataclass(frozen=True)
class Membership:
    org_id: TenantId
    role: str


@dataclass(frozen=True)
class CurrentTenant:
    tenant_id: TenantId
    user_id: UserId
    role: str


# (user, optional requested org) → membership, or None if the user has no access.
MembershipLookup = Callable[[UserId, TenantId | None], Awaitable[Membership | None]]


async def resolve_tenant(
    principal: Principal,
    *,
    lookup: MembershipLookup,
    requested_org: TenantId | None = None,
) -> CurrentTenant:
    membership = await lookup(principal.user_id, requested_org)
    if membership is None:
        raise ForbiddenError(
            "no membership for this user",
            user_id=str(principal.user_id),
            requested_org=str(requested_org) if requested_org else None,
        )
    return CurrentTenant(
        tenant_id=membership.org_id,
        user_id=principal.user_id,
        role=membership.role,
    )
