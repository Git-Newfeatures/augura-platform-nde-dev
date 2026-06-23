"""Structured-agent runtime (typed port of agents/runtime/anthropic.js).

Pattern: forced tool_choice → extraction of the tool input → Pydantic validation
→ 1 "repair" retry with the error injected (spec §9), then outright failure.
The LLM client is injected (Protocol): tests run against a mocked LLM, without a key.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import anthropic
from anthropic.types import Message, MessageParam, TextBlock, ToolParam, ToolUseBlock
from pydantic import BaseModel, ValidationError

from augura_api.core.config import Settings
from augura_api.core.errors import AppError


class AgentUpstreamError(AppError):
    code = "agent_upstream"
    http_status = 503
    title = "Agent upstream failure"


class AgentInvalidOutput(AppError):
    code = "agent_invalid_output"
    http_status = 502
    title = "Agent returned invalid output"


class LLMMessages(Protocol):
    async def create(self, **kwargs: Any) -> Message: ...


class LLMClient(Protocol):
    @property
    def messages(self) -> LLMMessages: ...


@dataclass(frozen=True)
class AgentResult[T: BaseModel]:
    output: T
    model: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ChatResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def get_anthropic_client(settings: Settings) -> LLMClient:
    if settings.anthropic_api_key is None:
        raise AgentUpstreamError("ANTHROPIC_API_KEY missing")
    # AsyncAnthropic.messages has an overloaded signature that pyright does not reconcile
    # with the minimal LLMMessages Protocol; the cast assumes responsibility for that boundary.
    return cast(LLMClient, anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key))


async def run_structured_agent[T: BaseModel](
    client: LLMClient,
    *,
    model: str,
    system: str,
    tool: ToolParam,
    messages: Sequence[MessageParam],
    output_model: type[T],
    max_tokens: int = 2000,
    max_repair: int = 1,
) -> AgentResult[T]:
    convo: list[MessageParam] = list(messages)
    tool_name = tool["name"]
    last_error: ValidationError | None = None

    for _attempt in range(max_repair + 1):
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=convo,
            )
        except anthropic.APIError as exc:
            raise AgentUpstreamError("LLM call failed", model=model, reason=str(exc)) from exc

        block = next(
            (b for b in resp.content if isinstance(b, ToolUseBlock) and b.name == tool_name),
            None,
        )
        if block is None:
            raise AgentInvalidOutput("no tool output", model=model)

        try:
            output = output_model.model_validate(block.input)
        except ValidationError as exc:
            last_error = exc
            convo = [
                *convo,
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": tool_name,
                            "input": block.input,
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": (
                                f"Validation failed: {exc}. Return a corrected tool output."
                            ),
                            "is_error": True,
                        }
                    ],
                },
            ]
            continue

        return AgentResult(
            output=output,
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

    raise AgentInvalidOutput("invalid tool output after repair", model=model, error=str(last_error))


async def run_chat(
    client: LLMClient,
    *,
    model: str,
    system: str,
    messages: Sequence[MessageParam],
    max_tokens: int = 1024,
) -> ChatResult:
    """Free chat (without a forced tool) — gateway for the frontend's inline assistant.
    Concatenates the response's text blocks. Raises AgentUpstreamError (503) on LLM outage
    (and get_anthropic_client already raises 503 if the key is missing)."""
    try:
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=list(messages),
        )
    except anthropic.APIError as exc:
        raise AgentUpstreamError("LLM call failed", model=model, reason=str(exc)) from exc

    text = "".join(b.text for b in resp.content if isinstance(b, TextBlock))
    return ChatResult(
        text=text,
        model=model,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )
