"""Tests for the enrich_propose LLM orchestration — LLM mocked, no DB or network.

Covers:
- The full flow (questions → coverage → batches → prechecks → result).
- The selectedConcepts shortcut (no coverage, a single LLM call).
"""

from typing import Any

import pytest
from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from augura_api.modules.semantic.enrich_propose import propose


def _empty_batch_msg() -> Message:
    """Empty LLM response message (all arrays at zero)."""
    block = ToolUseBlock(
        type="tool_use",
        id="tu",
        name="propose_enrichment_batch",
        input={
            "taxonomy_concepts": [],
            "taxonomy_synonyms": [],
            "taxonomy_standard_codes": [],
            "ontology_relations": [],
            "ontology_relation_evidence": [],
            "ontology_relation_qualifiers": [],
        },
    )
    content: list[ContentBlock] = [block]
    return Message(
        id="m",
        content=content,
        model="claude-opus-4-8",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=Usage(input_tokens=1, output_tokens=1),
    )


class _Msgs:
    """Fake LLM messages — always returns an empty batch."""

    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kw: Any) -> Message:
        self.calls += 1
        return _empty_batch_msg()


class _Client:
    def __init__(self) -> None:
        self.messages = _Msgs()


# ── Test 1: full flow with PICOT questions ────────────────────────────────


@pytest.mark.asyncio
async def test_propose_aggregates_and_reports_progress() -> None:
    """The full flow returns the expected structure and emits at least one progress event."""
    progress: list[tuple[float, str]] = []

    async def on_progress(frac: float, msg: str) -> None:
        progress.append((frac, msg))

    bundle: dict[str, Any] = {
        "taxonomy_concepts": [],
        "taxonomy_synonyms": [],
        "ontology_relations": [],
        "causal_predicates": [{"predicate_id": "precedes", "description": "x"}],
    }
    result = await propose(
        client=_Client(),
        model="claude-opus-4-8",
        bundle=bundle,
        questions=[
            {
                "id": "q1",
                "picot": {
                    "intervention": ["aspirin"],
                    "outcome": ["stroke"],
                },
            }
        ],
        selected_concepts=None,
        on_progress=on_progress,
    )

    # Proposals structure
    assert "taxonomy_concepts" in result["proposals"]
    assert "taxonomy_synonyms" in result["proposals"]
    assert "taxonomy_standard_codes" in result["proposals"]
    assert "ontology_relations" in result["proposals"]
    assert "ontology_relation_evidence" in result["proposals"]
    assert "ontology_relation_qualifiers" in result["proposals"]

    # Mandatory return keys
    assert "coverage_summary" in result
    assert "summary" in result
    assert "precheck_log" in result

    # At least one progress event emitted
    assert progress, "no progress emitted"

    # Fractions are in [0, 1]
    for frac, _ in progress:
        assert 0.0 <= frac <= 1.0, f"fraction out of range: {frac}"


# ── Test 2: selectedConcepts shortcut ───────────────────────────────────────


@pytest.mark.asyncio
async def test_propose_selected_concepts_shortcut() -> None:
    """The selectedConcepts shortcut skips coverage and returns a valid result."""
    progress: list[tuple[float, str]] = []

    async def on_progress(frac: float, msg: str) -> None:
        progress.append((frac, msg))

    bundle: dict[str, Any] = {
        "taxonomy_concepts": [],
        "taxonomy_synonyms": [],
        "ontology_relations": [],
        "causal_predicates": [{"predicate_id": "precedes", "description": "x"}],
    }
    result = await propose(
        client=_Client(),
        model="claude-opus-4-8",
        bundle=bundle,
        questions=None,
        selected_concepts=[{"id": "C1", "label": "x", "domain": "therapeutics"}],
        on_progress=on_progress,
    )

    # Proposals structure present
    assert isinstance(result["proposals"], dict)
    assert "taxonomy_concepts" in result["proposals"]
    assert "ontology_relations" in result["proposals"]

    # The shortcut produces no coverage_summary (or returns it empty/None)
    # — the spec says: "empty/absent for the selected_concepts shortcut path"
    summary = result.get("coverage_summary")
    assert summary is None or summary == {}

    # At least one progress event emitted
    assert progress
