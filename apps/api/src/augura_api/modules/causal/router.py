"""HTTP adapter for the causal module."""

from fastapi import APIRouter

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep
from augura_api.core.llm.runtime import get_anthropic_client
from augura_api.modules.causal import schemas
from augura_api.modules.causal.parse import parse_question
from augura_api.modules.causal.service import CausalService
from augura_api.modules.semantic.repo import SemanticRepo

router = APIRouter(prefix="/causal", tags=["causal"])


@router.post("/parse-question", response_model=schemas.ParseQuestionResponse)
async def parse_question_route(
    req: schemas.ParseQuestionRequest,
    tenant: CurrentTenantDep,
    settings: SettingsDep,
) -> schemas.ParseQuestionResponse:
    """Phase 1: Haiku structured parse of a clinical question into a PICOT frame (+ moderators),
    shown side by side with the browser's regex parser."""
    # LLM client built after auth ⇒ 401 before 503 if the key is missing.
    client = get_anthropic_client(settings)
    return await parse_question(client, model=settings.agent_model_fast, question=req.question)


@router.post("/dag", response_model=schemas.CausalDagResponse)
async def dag(
    req: schemas.CausalDagRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
) -> schemas.CausalDagResponse:
    """Causal DAG anchored in the B1 ontology, contextualized by the LLM (port of Nico)."""
    # LLM client built after auth ⇒ 401 before 503 if the key is missing.
    service = CausalService(SemanticRepo(session), get_anthropic_client(settings), settings)
    return await service.generate(req)
