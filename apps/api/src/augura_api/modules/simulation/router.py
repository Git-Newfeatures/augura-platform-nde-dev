"""Adaptateur HTTP du module simulation."""

from fastapi import APIRouter, status

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.simulation import schemas
from augura_api.modules.simulation.service import SimulationService, compute_power_response

router = APIRouter(prefix="/simulations", tags=["simulation"])


@router.post("/power", response_model=schemas.PowerResponse)
async def power(req: schemas.PowerRequest, tenant: CurrentTenantDep) -> schemas.PowerResponse:
    # Mode LIVE — pur calcul, pas de session.
    return compute_power_response(req)


@router.get("/results", response_model=list[schemas.SimulationResultOut])
async def results(
    tenant: CurrentTenantDep, session: SessionDep, cohort_name: str | None = None
) -> list[schemas.SimulationResultOut]:
    return await SimulationService(session).list_results(tenant, cohort_name)


@router.post("", response_model=schemas.SimulationRunCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_simulation(
    req: schemas.SimulationRequest, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.SimulationRunCreated:
    return await SimulationService(session).create_simulation(tenant, req)
