"""Simulation module logic: analytical power (LIVE), VALIDATED results,
on-demand bootstrap (job creation)."""

from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.errors import BadRequestError
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules import analytics
from augura_api.modules.jobs import create_job
from augura_api.modules.simulation import calibration, power, schemas
from augura_api.modules.simulation.repo import SimulationRepo


def compute_power_response(req: schemas.PowerRequest) -> schemas.PowerResponse:
    """LIVE mode — synchronous, no database or scientific dependency."""
    sigma = calibration.sigma_for(sigma=req.sigma, outcome=req.outcome)
    n = req.n or calibration.COHORT_N
    try:
        rows = power.compute_power(
            n=n,
            dropout=req.dropout,
            effect=req.effect,
            sigma=sigma,
            estimators=req.estimators,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc
    return schemas.PowerResponse(
        n=n,
        dropout=req.dropout,
        effect=req.effect,
        sigma=sigma,
        power_threshold=calibration.POWER_THRESHOLD,
        estimators=[schemas.EstimatorPowerOut(**asdict(r)) for r in rows],
    )


class SimulationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_results(
        self, tenant: CurrentTenant, cohort_name: str | None
    ) -> list[schemas.SimulationResultOut]:
        rows = await SimulationRepo(self.session).list_results(tenant.tenant_id, cohort_name)
        return [schemas.SimulationResultOut.model_validate(r) for r in rows]

    async def list_runs(self, tenant: CurrentTenant) -> list[schemas.SimulationRunOut]:
        runs = await SimulationRepo(self.session).list_runs(tenant.tenant_id)
        out: list[schemas.SimulationRunOut] = []
        for r in runs:
            results = r.results
            summary = results.get("summary") if isinstance(results, dict) else None
            out.append(
                schemas.SimulationRunOut(
                    id=r.id,
                    study_id=r.study_id,
                    job_id=r.job_id,
                    status=r.status,
                    created_at=r.created_at,
                    summary=summary,
                )
            )
        return out

    async def create_simulation(
        self, tenant: CurrentTenant, req: schemas.SimulationRequest
    ) -> schemas.SimulationRunCreated:
        # Idempotence: a duplicate POST with the same key returns the same job.
        job = await create_job(
            self.session,
            tenant.tenant_id,
            type="bootstrap",
            payload=req.params,
            idempotency_key=req.idempotency_key,
        )
        run = await SimulationRepo(self.session).create_run(
            tenant.tenant_id, study_id=req.study_id, params=req.params, job_id=job.id
        )
        await analytics.log_usage(
            self.session,
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            event_type="simulation.requested",
            route="/simulations",
            metadata={"job_id": str(job.id), "run_id": str(run.id)},
        )
        # The worker (jobs.runner.enqueue_job, scheduled by the router) runs the
        # bootstrap after the response — local fallback for the Modal worker.
        return schemas.SimulationRunCreated(job_id=job.id, run_id=run.id, status=job.status)
