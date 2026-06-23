"""Local tests for the E1 agent (profiling SSE) — mocked LLM + retriever.

Checks the multi-turn loop (tool_use → server retrieval → synthesis), parsing
of the final profile, and the error paths (parse / max_tokens).
"""

import json
from typing import Any

from anthropic.types import ContentBlock, Message, TextBlock, ToolUseBlock, Usage

from augura_api.modules.agents.streaming import stream_profiling


def _tool_msg(name: str, query: str) -> Message:
    content: list[ContentBlock] = [
        ToolUseBlock(type="tool_use", id="tu_1", name=name, input={"query": query})
    ]
    return Message(
        id="m1",
        content=content,
        model="claude-opus-4-8",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=Usage(input_tokens=5, output_tokens=3),
    )


def _text_msg(text: str, stop_reason: str = "end_turn") -> Message:
    content: list[ContentBlock] = [TextBlock(type="text", text=text, citations=None)]
    return Message(
        id="m2",
        content=content,
        model="claude-opus-4-8",
        role="assistant",
        stop_reason=stop_reason,  # type: ignore[arg-type] -- literal validated by the SDK
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


async def _retriever(_tool_name: str, query: str) -> list[dict[str, Any]]:
    return [
        {
            "content": f"hit for {query}",
            "similarity": 0.9,
            "source_id": "pubmed",
            "title": "A study",
        }
    ]


async def _collect(client: _FakeClient, **kw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    async for line in stream_profiling(client, retriever=_retriever, model="claude-opus-4-8", **kw):
        out.append(json.loads(line))
    return out


PROFILE: dict[str, Any] = {
    "feasibility_score": 78,
    "design_type": "Retrospective cohort",
    "endpoint": "HbA1c at 12m",
    "pubmed_evidence_count": 12,
    "risk_signal": "LOW",
}


async def test_stream_profiling_tool_then_synthesis() -> None:
    client = _FakeClient(
        _tool_msg("search_pubmed", "engagement HbA1c"),
        _text_msg("```json\n" + json.dumps(PROFILE) + "\n```"),
    )
    events = await _collect(
        client,
        system="E1 system",
        tools=[{"name": "search_pubmed"}],
        messages=[{"role": "user", "content": "product"}],
    )
    types = [e["type"] for e in events]
    assert "tool_use" in types
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["profile"]["feasibility_score"] == 78
    assert client.messages.calls == 2  # 1 tool round + 1 synthesis


async def test_stream_profiling_parse_failure() -> None:
    client = _FakeClient(_text_msg("not json at all"))
    events = await _collect(
        client, system="E1", tools=[], messages=[{"role": "user", "content": "p"}]
    )
    assert events[-1]["type"] == "error"
    assert events[-1]["text"] == "parse_failed"


async def test_stream_profiling_max_tokens() -> None:
    client = _FakeClient(_text_msg("", stop_reason="max_tokens"))
    events = await _collect(
        client, system="E1", tools=[], messages=[{"role": "user", "content": "p"}]
    )
    assert events[-1]["type"] == "error"
    assert "max_tokens" in events[-1]["text"]
