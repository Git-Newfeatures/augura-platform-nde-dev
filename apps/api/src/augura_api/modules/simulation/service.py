"""Logique du module simulation : power analytique (LIVE), résultats VALIDATED,
bootstrap à la demande (création de job)."""

from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.errors import BadRequestError
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.jobs import create_job
from augura_api.modules.simulation import calibration, power, schemas
from augura_api.modules.simulation.repo import SimulationRepo


def compute_power_response(req: schemas.PowerRequest) -> schemas.PowerResponse:
    """Mode LIVE — synchrone, sans base ni dépendance scientifique."""
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

    async def create_simulation(
        self, tenant: CurrentTenant, req: schemas.SimulationRequest
    ) -> schemas.SimulationRunCreated:
        # Idempotence : un double POST avec la même clé renvoie le même job.
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
        # En prod : modal.Function.spawn(job.id) lance le worker bootstrap
        # (jobs/ entrypoint, image scientifique) — non câblé en local.
        return schemas.SimulationRunCreated(job_id=job.id, run_id=run.id, status=job.status)
