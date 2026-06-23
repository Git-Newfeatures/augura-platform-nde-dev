"""HTTP adapter of the analytics module."""

from typing import Annotated

from fastapi import APIRouter, Depends

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
