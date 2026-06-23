"""Local gap-detection + variable-check tests — mocked LLM.

Covers the happy path and graceful degradations (gap → empty list;
dataset-questions → None) without any key.
"""

from typing import Any

from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from augura_api.core.config import Settings
from augura_api.modules.agents import schemas
from augura_api.modules.agents.service import AgentService


def _msg(tool_name: str, tool_input: dict[str, Any]) -> Message:
    content: list[ContentBlock] = [
        ToolUseBlock(type="tool_use", id="tu_1", name=tool_name, input=tool_input)
    ]
    return Message(
        id="m",
        content=content,
        model="claude-haiku-4-5",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=Usage(input_tokens=5, output_tokens=3),
    )


class _FakeMessages:
    def __init__(self, responses: list[Message]) -> None:
        self._responses = responses
        self.calls = 0

    async def create(self, **_kwargs: Any) -> Message:
        self.calls += 1
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, *responses: Message) -> None:
        self.messages = _FakeMessages(list(responses))


def _settings() -> Settings:
    return Settings(env="dev")  # pyright: ignore[reportCallIssue] -- env fields


GAP_OK: dict[str, Any] = {
    "missing_variables": [
        {
            "name": "Statin initiation during follow-up",
            "role": "unmeasured_confounder",
            "category": "user",
            "rationale": "Statins independently lower LDL.",
            "severity": "critical",
        }
    ]
}


async def test_detect_gaps_happy_path() -> None:
    svc = AgentService(_FakeClient(_msg("identify_data_gaps", GAP_OK)), _settings())
    out = await svc.detect_gaps(schemas.GapRequest(intervention="x", outcome="LDL"))
    assert len(out.missing_variables) == 1
    assert out.missing_variables[0].severity == "critical"


async def test_detect_gaps_degrades_to_empty() -> None:
    # Two invalid outputs → AgentInvalidOutput → degradation to empty list.
    bad = _msg("identify_data_gaps", {"missing_variables": "oops"})
    bad2 = _msg("identify_data_gaps", {"missing_variables": "still bad"})
    svc = AgentService(_FakeClient(bad, bad2), _settings())
    out = await svc.detect_gaps(schemas.GapRequest(intervention="x", outcome="y"))
    assert out.missing_variables == []


CLASSIFY_OK: dict[str, Any] = {
    "columns": [
        {
            "sheet": "cohort",
            "column": "hba1c_12m",
            "proposed_role": "outcome",
            "proposed_group": "outcomes",
            "proposed_canonical_id": "hba1c_12m",
            "confidence": 0.97,
            "rationale": "Follow-up biomarker.",
        }
    ]
}
DQ_OK: dict[str, Any] = {
    "questions": [
        {
            "question_code": "study_type",
            "answer": "Retrospective",
            "rationale": "No prospective arm.",
            "confidence": 0.8,
        }
    ]
}


def _req() -> schemas.VariableCheckRequest:
    return schemas.VariableCheckRequest(
        product_description="App for prediabetes",
        sheets=[
            schemas.Sheet(
                name="cohort",
                headers=["hba1c_12m"],
                column_stats=[schemas.ColumnStat(column="hba1c_12m", value_kind="numeric")],
            )
        ],
    )


async def test_classify_variables_happy_path() -> None:
    client = _FakeClient(
        _msg("classify_columns", CLASSIFY_OK), _msg("answer_dataset_questions", DQ_OK)
    )
    out = await AgentService(client, _settings()).classify_variables(_req())
    assert out.matches[0].column == "hba1c_12m"
    assert out.dataset_questions is not None
    assert out.dataset_questions[0].question_code == "study_type"
    assert client.messages.calls == 2


async def test_classify_variables_dataset_questions_degrade() -> None:
    # classify OK, but both dataset-questions attempts fail → None.
    client = _FakeClient(
        _msg("classify_columns", CLASSIFY_OK),
        _msg("answer_dataset_questions", {"questions": "bad"}),
        _msg("answer_dataset_questions", {"questions": "still bad"}),
    )
    out = await AgentService(client, _settings()).classify_variables(_req())
    assert out.matches[0].column == "hba1c_12m"
    assert out.dataset_questions is None
