"""Adaptateur HTTP du module agents."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SettingsDep
from augura_api.core.llm.runtime import get_anthropic_client
from augura_api.modules.agents import schemas
from augura_api.modules.agents.service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


def _service(settings: SettingsDep) -> AgentService:
    # Client LLM construit après l'auth (CurrentTenantDep) ⇒ 401 avant 503 si pas de clé.
    return AgentService(get_anthropic_client(settings), settings)


@router.post("/dag", response_model=schemas.DagResponse)
async def dag(
    req: schemas.DagRequest, tenant: CurrentTenantDep, settings: SettingsDep
) -> schemas.DagResponse:
    return await _service(settings).build_dag(req)


@router.post("/gaps", response_model=schemas.GapResponse)
async def gaps(
    req: schemas.GapRequest, tenant: CurrentTenantDep, settings: SettingsDep
) -> schemas.GapResponse:
    return await _service(settings).detect_gaps(req)


@router.post("/variable-check", response_model=schemas.VariableCheckResponse)
async def variable_check(
    req: schemas.VariableCheckRequest, tenant: CurrentTenantDep, settings: SettingsDep
) -> schemas.VariableCheckResponse:
    return await _service(settings).classify_variables(req)
