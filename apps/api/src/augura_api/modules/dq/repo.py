"""Accès base du module dq."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.dq.models import DqBundle


class DqRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_bundle(
        self,
        tenant_id: TenantId,
        *,
        dataset_id: UUID,
        score_profile: str,
        overall_score: float | None,
        status: str,
        requires_resolution: bool,
        bundle: dict[str, Any],
    ) -> DqBundle:
        row = DqBundle(
            org_id=tenant_id,
            dataset_id=dataset_id,
            score_profile=score_profile,
            overall_score=overall_score,
            status=status,
            requires_resolution=requires_resolution,
            bundle=bundle,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def latest_for_dataset(self, tenant_id: TenantId, dataset_id: UUID) -> DqBundle | None:
        res = await self.session.execute(
            select(DqBundle)
            .where(DqBundle.org_id == tenant_id, DqBundle.dataset_id == dataset_id)
            .order_by(DqBundle.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()
