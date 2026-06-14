"""Adaptateur HTTP du module analytics."""

from typing import Annotated

from fastapi import APIRouter, Depends

from augura_api.core.deps import SessionDep, require_role
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.analytics import schemas
from augura_api.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

# `/admin` expose des stats à l'échelle de l'org (ids d'autres utilisateurs inclus) :
# réservé au rôle `owner` (un `viewer`/`member` reçoit 403).
OwnerTenantDep = Annotated[CurrentTenant, Depends(require_role("owner"))]


@router.get("/admin", response_model=schemas.AdminStats)
async def admin(tenant: OwnerTenantDep, session: SessionDep) -> schemas.AdminStats:
    return await AnalyticsService(session).admin_stats(tenant)
