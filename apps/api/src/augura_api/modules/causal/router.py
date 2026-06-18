"""Adaptateur HTTP du module causal."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep
from augura_api.core.llm.runtime import get_anthropic_client
from augura_api.modules.causal import schemas
from augura_api.modules.causal.service import CausalService
from augura_api.modules.semantic.repo import SemanticRepo

router = APIRouter(prefix="/causal", tags=["causal"])


@router.post("/dag", response_model=schemas.CausalDagResponse)
async def dag(
    req: schemas.CausalDagRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> schemas.CausalDagResponse:
    """DAG causal ancré dans l'ontologie B1, contextualisé par LLM (port de Nico)."""
    # Client LLM construit après l'auth ⇒ 401 avant 503 si la clé manque.
    service = CausalService(SemanticRepo(session), get_anthropic_client(settings), settings)
    return await service.generate(req)
