"""Accès base du module analytics — agrégats d'usage, scopés tenant."""

from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.analytics.models import UsageEvent


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
        """Fil d'activité tenant (audit trail), le plus récent d'abord. Filtre optionnel
        sur metadata->>'study_id' quand un study_id est fourni."""
        stmt = select(UsageEvent).where(UsageEvent.org_id == tenant_id)
        if study_id:
            stmt = stmt.where(UsageEvent.metadata_["study_id"].astext == study_id)
        stmt = stmt.order_by(UsageEvent.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
