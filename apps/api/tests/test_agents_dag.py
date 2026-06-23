"""Local tests for the DAG agent — mocked LLM (no key required).

Covers the happy path, the "repair" retry on invalid output, hard failure
after repair, and input validation.
"""

from typing import Any

import pytest
from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from augura_api.core.config import Settings
from augura_api.core.errors import BadRequestError
from augura_api.core.llm.runtime import AgentInvalidOutput, AgentUpstreamError, get_anthropic_client
from augura_api.modules.agents import schemas
from augura_api.modules.agents.service import AgentService

VALID_DAG: dict[str, Any] = {
    "nodes": [
        {"id": "A", "label": "Engagement", "role": "intervention", "measured": True},
        {"id": "Y", "label": "HbA1c", "role": "outcome", "measured": True},
    ],
    "edges": [{"from": "A", "to": "Y"}],
    "adjustment_set": [],
    "collider_ids": [],
    "rationale": "Direct total effect of engagement on HbA1c.",
}


def _msg(tool_input: dict[str, Any]) -> Message:
    content: list[ContentBlock] = [
        ToolUseBlock(type="tool_use", id="tu_1", name="build_dag", input=tool_input)
    ]
    return Message(
        id="msg_1",
        content=content,
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
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


async def test_build_dag_happy_path() -> None:
    client = _FakeClient(_msg(VALID_DAG))
    out = await AgentService(client, _settings()).build_dag(
        schemas.DagRequest(intervention="High engagement", outcome="ΔHbA1c at 12m")
    )
    assert isinstance(out, schemas.DagResponse)
    assert {n.id for n in out.nodes} == {"A", "Y"}
    assert out.edges[0].source == "A"
    assert out.edges[0].to == "Y"
    assert client.messages.calls == 1


async def test_build_dag_repairs_invalid_output() -> None:
    client = _FakeClient(_msg({"nodes": "oops"}), _msg(VALID_DAG))
    out = await AgentService(client, _settings()).build_dag(
        schemas.DagRequest(intervention="x", outcome="y")
    )
    assert isinstance(out, schemas.DagResponse)
    assert client.messages.calls == 2  # 1 invalid + 1 repair


async def test_build_dag_fails_after_repair() -> None:
    client = _FakeClient(_msg({"nodes": "oops"}), _msg({"still": "bad"}))
    with pytest.raises(AgentInvalidOutput):
        await AgentService(client, _settings()).build_dag(
            schemas.DagRequest(intervention="x", outcome="y")
        )


async def test_build_dag_requires_fields() -> None:
    client = _FakeClient(_msg(VALID_DAG))
    with pytest.raises(BadRequestError):
        await AgentService(client, _settings()).build_dag(
            schemas.DagRequest(intervention="", outcome="y")
        )


def test_get_anthropic_client_requires_key() -> None:
    with pytest.raises(AgentUpstreamError):
        get_anthropic_client(_settings())
