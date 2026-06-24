"""Phase 1 — LLM (Haiku) parse of a clinical question into a PICOT/PECO frame.

Runs alongside the browser's deterministic regex parser (`picot-parser.js`). The two results
are shown side by side so the user can audit what the rule-based parser found on its own, what
the LLM corrected/added, and (critically) the effect-modifier moderators that regex cannot infer.
"""

from __future__ import annotations

from anthropic.types import ToolParam

from augura_api.core.llm.runtime import LLMClient, run_structured_agent
from augura_api.modules.causal import schemas

_SYSTEM = (
    "You are a clinical epidemiologist. Extract the PICOT/PECO frame from the clinical question: "
    "population, intervention/exposure, comparator, outcomes, timeframe, therapeutic area, and "
    "effect-modifier / subgroup moderators (which rule-based parsers cannot infer). Be concise and "
    "use the wording from the question. Leave a field empty when it is not present."
)

_PARSE_TOOL: ToolParam = {
    "name": "parse_clinical_question",
    "description": "Extract the PICOT/PECO frame (with effect modifiers) from a clinical question.",
    "input_schema": {
        "type": "object",
        "required": [
            "population",
            "intervention",
            "comparator",
            "outcomes",
            "timeframe",
            "moderators",
            "therapeutic_area",
        ],
        "properties": {
            "population": {"type": "string"},
            "intervention": {"type": "string", "description": "the intervention or exposure"},
            "comparator": {"type": "string"},
            "outcomes": {"type": "array", "items": {"type": "string"}},
            "timeframe": {"type": "string"},
            "moderators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "effect modifiers / subgroup variables",
            },
            "therapeutic_area": {"type": "string"},
        },
    },
}


async def parse_question(
    client: LLMClient, *, model: str, question: str
) -> schemas.ParseQuestionResponse:
    result = await run_structured_agent(
        client,
        model=model,
        system=_SYSTEM,
        tool=_PARSE_TOOL,
        messages=[{"role": "user", "content": f"CLINICAL QUESTION:\n{question}"}],
        output_model=schemas.ParsedQuestion,
        max_tokens=1000,
    )
    return schemas.ParseQuestionResponse(parsed=result.output, model=result.model)
