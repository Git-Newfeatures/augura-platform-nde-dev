"""HTTP adapter of the analytics module."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from augura_api.core.deps import CurrentTenantDep, SessionDep, require_role
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.analytics import schemas
from augura_api.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

# `/admin` exposes org-wide stats (including other users' ids):
# restricted to the `owner` role (a `viewer`/`member` gets 403).
OwnerTenantDep = Annotated[CurrentTenant, Depends(require_role("owner"))]


@router.get("/admin", response_model=schemas.AdminStats)
async def admin(tenant: OwnerTenantDep, session: SessionDep) -> schemas.AdminStats:
    return await AnalyticsService(session).admin_stats(tenant)


@router.get("/activity", response_model=list[schemas.ActivityEvent])
async def activity(
    tenant: CurrentTenantDep,
    session: SessionDep,
    limit: int = 30,
    study_id: str | None = None,
) -> list[schemas.ActivityEvent]:
    """Tenant activity feed (audit trail) — accessible to any member, filterable
    by study. Feeds the History tab and the frontend notifications."""
    return await AnalyticsService(session).activity(tenant, limit=limit, study_id=study_id)


@router.get("/artifacts", response_model=list[schemas.ArtifactOut])
async def artifacts(
    tenant: CurrentTenantDep,
    session: SessionDep,
    limit: int = 50,
    study_id: str | None = None,
) -> list[schemas.ArtifactOut]:
    """Tenant's versioned & hashed artifacts (provenance/reproducibility) —
    feeds the Lineage tab."""
    return await AnalyticsService(session).artifacts(tenant, limit=limit, study_id=study_id)


@router.post("/events/login", status_code=status.HTTP_204_NO_CONTENT)
async def login_event(
    body: schemas.LoginEventIn,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> None:
    """Record an attributed login event. user_id/org_id come from the verified
    JWT + resolved tenant (core/deps), not the client — the audit row is
    trustworthy (Part 11 attributability).

    Lazy-imports log_usage to avoid a circular import with analytics/__init__.py,
    which imports this router before defining log_usage."""
    from augura_api.modules.analytics import log_usage  # noqa: PLC0415 — circular-safe lazy import

    await log_usage(
        session,
        tenant_id=tenant.tenant_id,
        user_id=tenant.user_id,
        event_type="login",
        route=body.route,
        metadata={"source": "web"},
    )
