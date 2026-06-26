"""HTTP adapter of the simulation module."""

from fastapi import APIRouter, BackgroundTasks, status

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep, WriteTenantDep
from augura_api.jobs.runner import enqueue_job
from augura_api.modules.simulation import schemas
from augura_api.modules.simulation.service import SimulationService, compute_power_response

router = APIRouter(prefix="/simulations", tags=["simulation"])


@router.post("/power", response_model=schemas.PowerResponse)
async def power(req: schemas.PowerRequest, tenant: CurrentTenantDep) -> schemas.PowerResponse:
    # LIVE mode — pure computation, no session.
    return compute_power_response(req)


@router.get("/results", response_model=list[schemas.SimulationResultOut])
async def results(
    tenant: CurrentTenantDep, session: SessionDep, cohort_name: str | None = None
) -> list[schemas.SimulationResultOut]:
    return await SimulationService(session).list_results(tenant, cohort_name)


@router.get("/runs", response_model=list[schemas.SimulationRunOut])
async def list_runs(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.SimulationRunOut]:
    return await SimulationService(session).list_runs(tenant)


@router.post("", response_model=schemas.SimulationRunCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_simulation(
    req: schemas.SimulationRequest,
    tenant: WriteTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> schemas.SimulationRunCreated:
    created = await SimulationService(session).create_simulation(tenant, req)
    # The job runs after the response (the request session is committed by then):
    # real bootstrap → simulation_runs.results + read-model simulation_results.
    enqueue_job(background_tasks, tenant, created.job_id, settings=settings)
    return created
