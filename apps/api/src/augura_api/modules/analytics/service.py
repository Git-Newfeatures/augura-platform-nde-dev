"""Logique du module analytics."""

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.analytics import schemas
from augura_api.modules.analytics.models import UsageEvent
from augura_api.modules.analytics.repo import AnalyticsRepo


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def admin_stats(
        self, tenant: CurrentTenant, *, window_days: int = 7
    ) -> schemas.AdminStats:
        since = datetime.now(UTC) - timedelta(days=window_days)
        data = await AnalyticsRepo(self.session).admin_stats(tenant.tenant_id, since)
        recent = cast("list[UsageEvent]", data["recent"])
        return schemas.AdminStats(
            window_days=window_days,
            total_events=cast("int", data["total"]),
            unique_users=cast("int", data["unique_users"]),
            by_type=cast("dict[str, int]", data["by_type"]),
            recent=[
                schemas.RecentEvent(
                    user_id=e.user_id,
                    event_type=e.event_type,
                    route=e.route,
                    created_at=e.created_at,
                )
                for e in recent
            ],
        )
