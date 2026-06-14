"""Résolution du tenant courant à partir de l'utilisateur authentifié (spec §7).

`resolve_tenant` mappe un `Principal` (issu de `core.auth`) vers le `CurrentTenant`
via la table `memberships`. La recherche est injectée (`MembershipLookup`) pour
rester testable sans base ; le câblage en dépendance FastAPI arrive avec les routes.
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


# (user, org demandé optionnel) → appartenance, ou None si l'utilisateur n'a pas accès.
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
            "aucune appartenance pour cet utilisateur",
            user_id=str(principal.user_id),
            requested_org=str(requested_org) if requested_org else None,
        )
    return CurrentTenant(
        tenant_id=membership.org_id,
        user_id=principal.user_id,
        role=membership.role,
    )
