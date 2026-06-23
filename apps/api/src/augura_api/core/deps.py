"""FastAPI dependencies: from the Authorization header to the tenant and scoped session.

Chain: Bearer → `authenticate` (JWT) → `Principal` → `memberships` resolution
(user-scoped session, bootstrap RLS) → `CurrentTenant` → request session
(user_id + tenant_id set, full RLS active).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.auth import Principal, authenticate
from augura_api.core.config import Settings, get_settings
from augura_api.core.db import (
    get_sessionmaker,
    set_tenant_stmt,
    set_user_stmt,
)
from augura_api.core.errors import ForbiddenError, UnauthorizedError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant, Membership, resolve_tenant

SettingsDep = Annotated[Settings, Depends(get_settings)]


def membership_lookup_stmt(requested_org: TenantId | None) -> TextClause:
    """`memberships` query scoped to the current user (RLS), optionally filtered
    on a requested org. The `cast(:org as uuid)` is mandatory: `:org::uuid` is poorly
    parsed by `text()` (the `::` hides the bound parameter → `ArgumentError`)."""
    return text(
        "select org_id, role from memberships "
        "where (cast(:org as uuid) is null or org_id = cast(:org as uuid)) "
        "order by created_at asc limit 1"
    ).bindparams(org=str(requested_org) if requested_org else None)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("missing Bearer token")
    return token.strip()


async def get_principal(request: Request, settings: SettingsDep) -> Principal:
    return await authenticate(_bearer_token(request), settings)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


async def get_current_tenant(principal: PrincipalDep, settings: SettingsDep) -> CurrentTenant:
    sessionmaker = get_sessionmaker(settings)

    async def lookup(user_id: UserId, requested_org: TenantId | None) -> Membership | None:
        async with sessionmaker() as session, session.begin():
            await session.execute(set_user_stmt(user_id))
            res = await session.execute(membership_lookup_stmt(requested_org))
            row = res.first()
            if row is None:
                return None
            return Membership(org_id=TenantId(row.org_id), role=str(row.role))

    return await resolve_tenant(principal, lookup=lookup)


CurrentTenantDep = Annotated[CurrentTenant, Depends(get_current_tenant)]


def require_role(*allowed: str) -> Callable[[CurrentTenant], Awaitable[CurrentTenant]]:
    """Authorization dependency: requires the current tenant's role to be in
    `allowed`, otherwise 403. Used to gate sensitive routes (e.g. analytics)."""

    async def _require(tenant: CurrentTenantDep) -> CurrentTenant:
        if tenant.role not in allowed:
            raise ForbiddenError(
                "insufficient role for this resource",
                required=list(allowed),
                role=tenant.role,
            )
        return tenant

    return _require


async def get_session(
    tenant: CurrentTenantDep, settings: SettingsDep
) -> AsyncIterator[AsyncSession]:
    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session, session.begin():
        await session.execute(set_user_stmt(tenant.user_id))
        await session.execute(set_tenant_stmt(tenant.tenant_id))
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
