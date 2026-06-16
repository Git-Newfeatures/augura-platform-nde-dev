"""Accès base du module simulation — chaque méthode exige un TenantId."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.simulation.models import SimulationResult, SimulationRun


class SimulationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_results(
        self, tenant_id: TenantId, cohort_name: str | None = None
    ) -> list[SimulationResult]:
        stmt = select(SimulationResult).where(SimulationResult.org_id == tenant_id)
        if cohort_name:
            stmt = stmt.where(SimulationResult.cohort_name == cohort_name)
        res = await self.session.execute(
            stmt.order_by(SimulationResult.scenario, SimulationResult.estimator)
        )
        return list(res.scalars().all())

    async def create_run(
        self,
        tenant_id: TenantId,
        *,
        study_id: UUID | None,
        params: dict[str, Any],
        job_id: UUID,
    ) -> SimulationRun:
        run = SimulationRun(org_id=tenant_id, study_id=study_id, params=params, job_id=job_id)
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run
