"""LLM curation of live results (re-ranking by abstract + rationale).

Sibling of `pubmed.py` / `ctgov.py`. `Curator` is an injectable Protocol (tests with
no network); `LLMCurator` reuses `run_structured_agent` (forced tool + Pydantic
validation + 1 repair retry). The LLM returns ONLY ordered ids + rationale;
the mapping to the already-retrieved records is deterministic (`apply_curation`),
so no content fabrication is possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from anthropic.types import ToolParam
from pydantic import BaseModel

from augura_api.core.llm.runtime import LLMClient, run_structured_agent

# Curation prompt version — pinned in the snapshot provenance.
CURATION_PROMPT_VERSION = "curate-v1"

# Token bound: we truncate each candidate's text (abstract / CT.gov summary).
_MAX_TEXT = 1200


@dataclass(frozen=True)
class CurationCandidate:
    """Candidate submitted to the LLM: stable id + title + judgeable text (abstract or summary)."""

    id: str
    title: str
    text: str


@dataclass(frozen=True)
class CuratedRef:
    """Per-item curation output: the list order carries the ranking."""

    id: str
    rationale: str


def apply_curation[T](
    refs: list[CuratedRef], by_id: dict[str, T], *, max_results: int
) -> list[tuple[T, str]]:
    """Maps the LLM's ordered refs → (record, rationale), deterministically:
    ignores ids outside `by_id` (hallucinated) and duplicates, caps at
    `max_results`. Returns [] if nothing matches (the caller decides the fallback)."""
    seen: set[str] = set()
    out: list[tuple[T, str]] = []
    for ref in refs:
        if ref.id in seen or ref.id not in by_id:
            continue
        seen.add(ref.id)
        out.append((by_id[ref.id], ref.rationale))
        if len(out) >= max_results:
            break
    return out


class Curator(Protocol):
    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]: ...


class _CuratedItem(BaseModel):
    id: str
    rationale: str = ""


class _CurationOutput(BaseModel):
    selected: list[_CuratedItem]


_CURATION_TOOL: ToolParam = {
    "name": "curate_results",
    "description": "Returns the most relevant results, ranked from most to least "
    "relevant, each with a short rationale.",
    "input_schema": {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "exact id of a provided candidate"},
                        "rationale": {"type": "string", "description": "1-sentence justification"},
                    },
                    "required": ["id"],
                },
            }
        },
        "required": ["selected"],
    },
}

_SYSTEM = (
    "You are a biomedical information specialist. Given a research question and "
    "a list of results (id, title, text), select and RANK the most relevant ones, "
    "from most to least relevant. At equal relevance, prioritize the strongest "
    "evidence (meta-analyses / systematic reviews / RCT > observational > "
    "other). NEVER invent an id: use only the ids provided. Give a one-sentence "
    "rationale per selected result. Discard off-topic results."
)


def _render(candidates: list[CurationCandidate]) -> str:
    lines: list[str] = []
    for c in candidates:
        text = c.text[:_MAX_TEXT]
        lines.append(f"[{c.id}] {c.title}\n{text}")
    return "\n\n".join(lines)


class LLMCurator:
    """Real implementation: one `run_structured_agent` call per source."""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    async def curate(
        self, query: str, source: str, candidates: list[CurationCandidate], *, max_results: int
    ) -> list[CuratedRef]:
        if not candidates:
            return []
        user = (
            f"Question: {query}\nSource: {source}\n"
            f"Select at most {max_results} results from:\n\n{_render(candidates)}"
        )
        result = await run_structured_agent(
            self._client,
            model=self._model,
            system=_SYSTEM,
            tool=_CURATION_TOOL,
            messages=[{"role": "user", "content": user}],
            output_model=_CurationOutput,
        )
        return [CuratedRef(id=i.id, rationale=i.rationale) for i in result.output.selected]
