"""Logique du module agents. Sorties validées Pydantic + 1 retry réparation (runtime)."""

from augura_api.core.config import Settings
from augura_api.core.errors import BadRequestError
from augura_api.core.llm.runtime import AgentResult, LLMClient, run_structured_agent
from augura_api.modules.agents import schemas
from augura_api.modules.agents.tools import (
    DAG_SYSTEM_PROMPT,
    DAG_TOOL,
    build_dag_user_message,
)


class AgentService:
    def __init__(self, client: LLMClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def build_dag(self, req: schemas.DagRequest) -> schemas.DagResponse:
        if not req.intervention or not req.outcome:
            raise BadRequestError("intervention et outcome sont requis")
        result: AgentResult[schemas.DagResponse] = await run_structured_agent(
            self.client,
            model=self.settings.agent_model_dag,
            system=DAG_SYSTEM_PROMPT,
            tool=DAG_TOOL,
            messages=[{"role": "user", "content": build_dag_user_message(req)}],
            output_model=schemas.DagResponse,
            max_tokens=2000,
        )
        return result.output
