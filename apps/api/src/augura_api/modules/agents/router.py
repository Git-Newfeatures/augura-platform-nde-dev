"""HTTP adapter for the agents module."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from augura_api.core.db import get_sessionmaker, set_tenant_stmt, set_user_stmt
from augura_api.core.deps import CurrentTenantDep, SettingsDep
from augura_api.core.llm.embeddings import get_embedder
from augura_api.core.llm.runtime import get_anthropic_client
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.agents import schemas
from augura_api.modules.agents.service import AgentService
from augura_api.modules.agents.streaming import stream_profiling
from augura_api.modules.corpus import search_corpus

router = APIRouter(prefix="/agents", tags=["agents"])

# Maps the E1 tool name (search_pubmed…) to a corpus source_id.
_TOOL_SOURCE = {
    "search_pubmed": "pubmed",
    "search_clinicaltrials": "clinicaltrials",
    "search_maude": "maude",
    "search_fda_guidance": "guidance",
}


def _service(settings: SettingsDep) -> AgentService:
    # LLM client built after auth (CurrentTenantDep) ⇒ 401 before 503 if no key.
    return AgentService(get_anthropic_client(settings), settings)


@router.post("/chat", response_model=schemas.ChatResponse)
async def chat(
    req: schemas.ChatRequest, tenant: CurrentTenantDep, settings: SettingsDep
) -> schemas.ChatResponse:
    """Inline assistant: Anthropic Messages gateway. Explicit 503 if no key."""
    return await _service(settings).chat(req)


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


@router.post("/profiling/stream")
async def profiling_stream(
    req: schemas.ProfilingRequest, tenant: CurrentTenantDep, settings: SettingsDep
) -> StreamingResponse:
    client = get_anthropic_client(settings)
    embedder = get_embedder(settings)
    sessionmaker = get_sessionmaker(settings)
    current: CurrentTenant = tenant

    async def retriever(tool_name: str, query: str) -> list[dict[str, Any]]:
        embedding = await embedder.embed(query)
        source = _TOOL_SOURCE.get(tool_name)
        filt = {"source_id": source} if source else {}
        async with sessionmaker() as session, session.begin():
            await session.execute(set_user_stmt(current.user_id))
            await session.execute(set_tenant_stmt(current.tenant_id))
            return await search_corpus(session, embedding, match_count=20, filter=filt)

    return StreamingResponse(
        stream_profiling(
            client,
            system=req.system,
            tools=req.tools,
            messages=req.messages,
            retriever=retriever,
            model=settings.agent_model_deep,
        ),
        media_type="application/x-ndjson",
    )
