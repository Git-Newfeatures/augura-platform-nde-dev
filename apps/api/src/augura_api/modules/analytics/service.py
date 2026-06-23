"""Analytics module logic."""

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

    async def activity(
        self, tenant: CurrentTenant, *, limit: int = 30, study_id: str | None = None
    ) -> list[schemas.ActivityEvent]:
        rows = await AnalyticsRepo(self.session).recent_activity(
            tenant.tenant_id, limit=max(1, min(100, limit)), study_id=study_id
        )
        return [
            schemas.ActivityEvent(
                id=e.id,
                event_type=e.event_type,
                route=e.route,
                created_at=e.created_at,
                metadata=e.metadata_,
            )
            for e in rows
        ]

    async def artifacts(
        self, tenant: CurrentTenant, *, limit: int = 50, study_id: str | None = None
    ) -> list[schemas.ArtifactOut]:
        rows = await AnalyticsRepo(self.session).list_artifacts(
            tenant.tenant_id, limit=max(1, min(100, limit)), study_id=study_id
        )
        return [
            schemas.ArtifactOut(
                id=a.id,
                kind=a.kind,
                version=a.version,
                sha256=a.sha256,
                study_id=a.study_id,
                storage_ref=a.storage_ref,
                provenance=a.provenance,
                locked=a.locked,
                created_at=a.created_at,
            )
            for a in rows
        ]

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
