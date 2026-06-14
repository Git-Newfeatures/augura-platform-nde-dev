"""Agent E1 (profiling) — boucle tool-use multi-tour, streamée en NDJSON.

Port de lucis-dashboard/api/trace.js, mais la boucle tourne côté serveur :
l'outil de retrieval appelle l'interface publique de `corpus` (spec §8), au lieu
de faire un aller-retour client. Émet des événements NDJSON (log/tool_use/done/
error). LLM et retriever sont injectés ⇒ testable sans clé ni base.
"""

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import anthropic

from augura_api.core.llm.runtime import LLMClient

# (tool_name, query) → lignes de corpus (dicts façon match_chunks)
Retriever = Callable[[str, str], Awaitable[list[dict[str, Any]]]]

TOOL_LABELS = {
    "search_pubmed": "PubMed",
    "search_clinicaltrials": "ClinicalTrials.gov",
    "search_maude": "MAUDE",
    "search_fda_guidance": "FDA Guidance",
}

MAX_ITERATIONS = 10


def _ndjson(event_type: str, text: str = "", **data: Any) -> str:
    return json.dumps({"type": event_type, "text": text, **data}) + "\n"


def _parse_profile(text: str) -> dict[str, Any] | None:
    clean = text.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{[\s\S]*\}", clean)
    candidate = match.group(0) if match else clean
    try:
        parsed: Any = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else None


async def stream_profiling(
    client: LLMClient,
    *,
    system: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    retriever: Retriever,
    model: str,
    max_iterations: int = MAX_ITERATIONS,
) -> AsyncIterator[str]:
    convo: list[dict[str, Any]] = list(messages)
    if len(convo) <= 1:
        yield _ndjson("log", "Initialising E1 Profiling Agent v1.0")
        yield _ndjson(
            "log", "Corpus access verified — PubMed · ClinicalTrials.gov · MAUDE · FDA Guidance"
        )

    for _iteration in range(max_iterations):
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=2000,
                system=system,
                tools=tools,
                messages=convo,
            )
        except anthropic.APIError as exc:
            yield _ndjson("error", f"Agent error: {exc}")
            return

        tool_uses = [b for b in resp.content if b.type == "tool_use"]

        if tool_uses:
            convo.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                        for b in tool_uses
                    ],
                }
            )
            results: list[dict[str, Any]] = []
            for block in tool_uses:
                query_str = str(block.input.get("query", ""))
                label = TOOL_LABELS.get(block.name, block.name)
                shown = query_str[:72] + ("…" if len(query_str) > 72 else "")
                yield _ndjson(
                    "tool_use", f"→ [{label}] {shown}", tool=block.name, tool_use_id=block.id
                )
                rows = await retriever(block.name, query_str)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(rows),
                    }
                )
            convo.append({"role": "user", "content": results})
            continue

        if resp.stop_reason == "end_turn":
            text = "".join(b.text for b in resp.content if b.type == "text")
            profile = _parse_profile(text)
            if profile is None:
                yield _ndjson("error", "parse_failed")
                return
            yield _ndjson("log", "→ [Augura Engine] Synthesising findings across all sources")
            yield _ndjson("done", "", profile=profile)
            return

        if resp.stop_reason == "max_tokens":
            yield _ndjson("error", "max_tokens — model output truncated.")
            return

        break

    yield _ndjson("error", "agent did not converge (max iterations reached)")
