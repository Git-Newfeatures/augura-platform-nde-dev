"""Analytics module data access — usage aggregates, tenant-scoped."""

from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.analytics.models import Artifact, UsageEvent


class AnalyticsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def admin_stats(self, tenant_id: TenantId, since: datetime) -> dict[str, object]:
        scope = (UsageEvent.org_id == tenant_id, UsageEvent.created_at >= since)
        total = await self.session.scalar(
            select(func.count()).select_from(UsageEvent).where(*scope)
        )
        unique_users = await self.session.scalar(
            select(func.count(distinct(UsageEvent.user_id))).where(*scope)
        )
        by_type_rows = (
            await self.session.execute(
                select(UsageEvent.event_type, func.count())
                .where(*scope)
                .group_by(UsageEvent.event_type)
            )
        ).all()
        recent = (
            (
                await self.session.execute(
                    select(UsageEvent)
                    .where(*scope)
                    .order_by(UsageEvent.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        return {
            "total": int(total or 0),
            "unique_users": int(unique_users or 0),
            "by_type": {str(t): int(n) for t, n in by_type_rows},
            "recent": list(recent),
        }

    async def recent_activity(
        self, tenant_id: TenantId, *, limit: int = 30, study_id: str | None = None
    ) -> list[UsageEvent]:
        """Tenant activity feed (audit trail), most recent first. Optional filter
        on metadata->>'study_id' when a study_id is provided."""
        stmt = select(UsageEvent).where(UsageEvent.org_id == tenant_id)
        if study_id:
            stmt = stmt.where(UsageEvent.metadata_["study_id"].astext == study_id)
        stmt = stmt.order_by(UsageEvent.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_artifacts(
        self, tenant_id: TenantId, *, limit: int = 50, study_id: str | None = None
    ) -> list[Artifact]:
        """Tenant's versioned & hashed artifacts (provenance), most recent first."""
        stmt = select(Artifact).where(Artifact.org_id == tenant_id)
        if study_id:
            stmt = stmt.where(Artifact.study_id == study_id)
        stmt = stmt.order_by(Artifact.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
