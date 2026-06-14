"""Adaptateur HTTP du module agents."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SettingsDep
from augura_api.core.llm.runtime import get_anthropic_client
from augura_api.modules.agents import schemas
from augura_api.modules.agents.service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/dag", response_model=schemas.DagResponse)
async def dag(
    req: schemas.DagRequest, tenant: CurrentTenantDep, settings: SettingsDep
) -> schemas.DagResponse:
    # Client LLM construit après l'auth (CurrentTenantDep) ⇒ 401 avant 503 si pas de clé.
    service = AgentService(get_anthropic_client(settings), settings)
    return await service.build_dag(req)
