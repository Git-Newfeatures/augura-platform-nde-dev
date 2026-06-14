"""Adaptateur HTTP du module analytics."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.analytics import schemas
from augura_api.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/admin", response_model=schemas.AdminStats)
async def admin(tenant: CurrentTenantDep, session: SessionDep) -> schemas.AdminStats:
    return await AnalyticsService(session).admin_stats(tenant)
