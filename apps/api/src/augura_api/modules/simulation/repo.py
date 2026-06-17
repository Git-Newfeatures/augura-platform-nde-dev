"""Accès base du module simulation — chaque méthode exige un TenantId."""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
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

    async def get_run(self, tenant_id: TenantId, run_id: UUID) -> SimulationRun | None:
        res = await self.session.execute(
            select(SimulationRun).where(
                SimulationRun.org_id == tenant_id, SimulationRun.id == run_id
            )
        )
        return res.scalar_one_or_none()

    async def list_runs(self, tenant_id: TenantId, limit: int = 50) -> list[SimulationRun]:
        res = await self.session.execute(
            select(SimulationRun)
            .where(SimulationRun.org_id == tenant_id)
            .order_by(SimulationRun.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())

    async def get_run_by_job(self, tenant_id: TenantId, job_id: UUID) -> SimulationRun | None:
        res = await self.session.execute(
            select(SimulationRun).where(
                SimulationRun.org_id == tenant_id, SimulationRun.job_id == job_id
            )
        )
        return res.scalar_one_or_none()

    async def finalize_run(
        self,
        tenant_id: TenantId,
        run_id: UUID,
        *,
        status: str,
        results: dict[str, Any] | None,
    ) -> None:
        await self.session.execute(
            update(SimulationRun)
            .where(SimulationRun.org_id == tenant_id, SimulationRun.id == run_id)
            .values(status=status, results=results)
        )
        await self.session.flush()

    async def replace_results(
        self,
        tenant_id: TenantId,
        cohort_name: str,
        rows: list[dict[str, Any]],
    ) -> None:
        """Remplace le read-model VALIDATED pour (tenant, cohort) — delete puis insert
        en masse, pour qu'un re-run du bootstrap ne duplique pas les lignes."""
        await self.session.execute(
            delete(SimulationResult).where(
                SimulationResult.org_id == tenant_id,
                SimulationResult.cohort_name == cohort_name,
            )
        )
        for r in rows:
            self.session.add(
                SimulationResult(
                    org_id=tenant_id,
                    cohort_name=cohort_name,
                    scenario=r["scenario"],
                    estimator=r["estimator"],
                    effect_size=r.get("effect_size"),
                    ci_lower=r.get("ci_lower"),
                    ci_upper=r.get("ci_upper"),
                    power=r.get("power"),
                    p_value=r.get("p_value"),
                )
            )
        await self.session.flush()
