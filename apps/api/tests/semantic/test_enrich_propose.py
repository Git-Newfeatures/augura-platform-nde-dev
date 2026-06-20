"""Tests de l'orchestration LLM enrich_propose — LLM mocké, sans DB ni réseau.

Couvre :
- Le flux complet (questions → couverture → batches → préchecks → résultat).
- Le raccourci selectedConcepts (pas de couverture, 1 seul appel LLM).
"""

from typing import Any

import pytest
from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from augura_api.modules.semantic.enrich_propose import propose


def _empty_batch_msg() -> Message:
    """Message LLM de réponse vide (tous les tableaux à zéro)."""
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
    """Messages LLM fictifs — retourne toujours un batch vide."""

    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **_kw: Any) -> Message:
        self.calls += 1
        return _empty_batch_msg()


class _Client:
    def __init__(self) -> None:
        self.messages = _Msgs()


# ── Test 1 : flux complet avec questions PICOT ────────────────────────────────


@pytest.mark.asyncio
async def test_propose_aggregates_and_reports_progress() -> None:
    """Le flux complet renvoie la structure attendue et émet au moins un progrès."""
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

    # Structure des proposals
    assert "taxonomy_concepts" in result["proposals"]
    assert "taxonomy_synonyms" in result["proposals"]
    assert "taxonomy_standard_codes" in result["proposals"]
    assert "ontology_relations" in result["proposals"]
    assert "ontology_relation_evidence" in result["proposals"]
    assert "ontology_relation_qualifiers" in result["proposals"]

    # Clés de retour obligatoires
    assert "coverage_summary" in result
    assert "summary" in result
    assert "precheck_log" in result

    # Au moins une émission de progrès
    assert progress, "aucun progrès émis"

    # Les fractions sont dans [0, 1]
    for frac, _ in progress:
        assert 0.0 <= frac <= 1.0, f"fraction hors plage : {frac}"


# ── Test 2 : raccourci selectedConcepts ───────────────────────────────────────


@pytest.mark.asyncio
async def test_propose_selected_concepts_shortcut() -> None:
    """Le raccourci selectedConcepts saute la couverture et renvoie un résultat valide."""
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

    # Structure des proposals présente
    assert isinstance(result["proposals"], dict)
    assert "taxonomy_concepts" in result["proposals"]
    assert "ontology_relations" in result["proposals"]

    # Le raccourci ne produit pas de coverage_summary (ou le retourne vide/None)
    # — la spec dit : "empty/absent for the selected_concepts shortcut path"
    summary = result.get("coverage_summary")
    assert summary is None or summary == {}

    # Au moins un progrès émis
    assert progress
