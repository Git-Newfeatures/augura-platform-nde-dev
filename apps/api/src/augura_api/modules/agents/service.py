"""Agents module logic. Pydantic-validated outputs + 1 repair retry (runtime)."""

from augura_api.core.config import Settings
from augura_api.core.errors import BadRequestError
from augura_api.core.llm.runtime import (
    AgentInvalidOutput,
    AgentResult,
    AgentUpstreamError,
    LLMClient,
    run_chat,
    run_structured_agent,
)
from augura_api.modules.agents import schemas
from augura_api.modules.agents.tools import (
    DAG_SYSTEM_PROMPT,
    DAG_TOOL,
    DATASET_QUESTIONS_SYSTEM_PROMPT,
    DATASET_QUESTIONS_TOOL,
    GAP_SYSTEM_PROMPT,
    GAP_TOOL,
    VARCHECK_SYSTEM_PROMPT,
    VARIABLE_CHECK_TOOL,
    build_dag_user_message,
    build_dataset_questions_user_message,
    build_gap_user_message,
    build_varcheck_user_message,
)

_AGENT_FAILURES = (AgentUpstreamError, AgentInvalidOutput)


class AgentService:
    def __init__(self, client: LLMClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    _DEFAULT_CHAT_SYSTEM = (
        "You are Augura's scientific assistant, a clinical-evidence platform "
        "(RWE studies, DiGA, causal design). Respond concisely, rigorously, and "
        "actionably, drawing on the provided context. If information is missing, "
        "say so explicitly rather than inventing it."
    )

    async def chat(self, req: schemas.ChatRequest) -> schemas.ChatResponse:
        if not req.messages:
            raise BadRequestError("messages is required and must not be empty")
        result = await run_chat(
            self.client,
            model=req.model or self.settings.agent_model_dag,
            system=req.system or self._DEFAULT_CHAT_SYSTEM,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            max_tokens=1500,
        )
        return schemas.ChatResponse(text=result.text, model=result.model)

    async def build_dag(self, req: schemas.DagRequest) -> schemas.DagResponse:
        if not req.intervention or not req.outcome:
            raise BadRequestError("intervention and outcome are required")
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

    async def detect_gaps(self, req: schemas.GapRequest) -> schemas.GapResponse:
        if not req.intervention or not req.outcome:
            raise BadRequestError("intervention and outcome are required")
        user = build_gap_user_message(
            intervention=req.intervention,
            outcome=req.outcome,
            population=req.population,
            selected_outcome=req.selected_outcome,
            measured=[(m.column, m.role) for m in req.measured_variables],
        )
        try:
            result = await run_structured_agent(
                self.client,
                model=self.settings.agent_model_fast,
                system=GAP_SYSTEM_PROMPT,
                tool=GAP_TOOL,
                messages=[{"role": "user", "content": user}],
                output_model=schemas.GapResponse,
                max_tokens=1500,
            )
        except _AGENT_FAILURES:
            # Parity with api/gap-detection.js: degrade to empty so as not to
            # block the downstream DAG flow.
            return schemas.GapResponse(missing_variables=[])
        return result.output

    async def classify_variables(
        self, req: schemas.VariableCheckRequest
    ) -> schemas.VariableCheckResponse:
        if not req.sheets:
            raise BadRequestError("sheets is required and must not be empty")
        sheets = [s.model_dump() for s in req.sheets]
        classify: AgentResult[schemas.ClassifyColumnsResponse] = await run_structured_agent(
            self.client,
            model=self.settings.agent_model_fast,
            system=VARCHECK_SYSTEM_PROMPT,
            tool=VARIABLE_CHECK_TOOL,
            messages=[
                {
                    "role": "user",
                    "content": build_varcheck_user_message(
                        product_description=req.product_description, sheets=sheets
                    ),
                }
            ],
            output_model=schemas.ClassifyColumnsResponse,
            max_tokens=16000,
        )
        matches = classify.output.columns

        # Dataset questions = best-effort: any failure degrades to None.
        questions: list[schemas.DatasetQuestion] | None = None
        try:
            dq = await run_structured_agent(
                self.client,
                model=self.settings.agent_model_fast,
                system=DATASET_QUESTIONS_SYSTEM_PROMPT,
                tool=DATASET_QUESTIONS_TOOL,
                messages=[
                    {
                        "role": "user",
                        "content": build_dataset_questions_user_message(
                            product_description=req.product_description,
                            matches=[(m.sheet, m.column, m.proposed_role) for m in matches],
                        ),
                    }
                ],
                output_model=schemas.DatasetQuestionsResponse,
                max_tokens=2000,
            )
            questions = dq.output.questions
        except _AGENT_FAILURES:
            questions = None

        return schemas.VariableCheckResponse(
            clinical_domain=None, matches=matches, dataset_questions=questions
        )
