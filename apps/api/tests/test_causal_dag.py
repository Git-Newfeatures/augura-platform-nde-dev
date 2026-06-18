"""Tests du module causal — LLM mocké + repo factice (aucune clé, aucune base).

Couvre l'orchestration generate() de bout en bout (sous-graphe → LLM → graphe),
l'ancrage ontologique (arêtes data-backed), et un cas de relation proposée par le LLM.
"""

from typing import Any

from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from augura_api.core.config import Settings
from augura_api.modules.causal import schemas
from augura_api.modules.causal.service import CausalService
from augura_api.modules.semantic.models import OntologyRelation, TaxonomyConcept


def _rel(rid: str, subj: str, obj: str) -> OntologyRelation:
    return OntologyRelation(
        relation_id=rid,
        subject_concept_id=subj,
        predicate="causally_influences",
        object_concept_id=obj,
        polarity="increases",
        default_strength="moderate",
        default_temporal_lag="none",
        mechanism_summary=f"{subj}→{obj}",
        review_status="approved",
        version="v1",
        active=True,
    )


def _concept(cid: str, name: str, domain: str) -> TaxonomyConcept:
    return TaxonomyConcept(
        local_concept_id=cid,
        layer=1,
        concept_name=name,
        augura_domain=domain,
        review_status="approved",
        version="v1",
        active=True,
    )


class _FakeRepo:
    def __init__(self, relations: list[OntologyRelation], concepts: list[TaxonomyConcept]) -> None:
        self._relations = relations
        self._concepts = concepts

    async def list_relations(self, *, active: bool = True) -> list[OntologyRelation]:
        return [r for r in self._relations if r.active or not active]

    async def list_relation_evidence(self) -> list[Any]:
        return []

    async def list_relation_qualifiers(self) -> list[Any]:
        return []

    async def list_concepts(
        self, *, domain: str | None = None, active: bool = True
    ) -> list[TaxonomyConcept]:
        return self._concepts


def _msg(tool_input: dict[str, Any]) -> Message:
    content: list[ContentBlock] = [
        ToolUseBlock(type="tool_use", id="tu_1", name="filter_dag_relations", input=tool_input)
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
    return Settings(env="dev")  # pyright: ignore[reportCallIssue] -- champs via env


def _confounded_triangle() -> _FakeRepo:
    relations = [_rel("R1", "W", "A"), _rel("R2", "W", "Y"), _rel("R3", "A", "Y")]
    concepts = [
        _concept("A", "Engagement", "intervention"),
        _concept("Y", "HbA1c", "measurement"),
        _concept("W", "Baseline severity", "condition"),
    ]
    return _FakeRepo(relations, concepts)


def _request() -> schemas.CausalDagRequest:
    return schemas.CausalDagRequest(
        clinical_question="Does engagement lower HbA1c?",
        mapped_concepts=[
            schemas.MappedConcept(concept_id="A", concept_label="Engagement", confidence=0.9),
            schemas.MappedConcept(concept_id="Y", concept_label="HbA1c", confidence=0.9),
            schemas.MappedConcept(concept_id="W", concept_label="Baseline", confidence=0.9),
        ],
    )


_FULL_RESULT: dict[str, Any] = {
    "selected_relations": [
        {"relation_id": "R1", "dag_role_subject": "confounder", "dag_role_object": "exposure"},
        {"relation_id": "R2", "dag_role_subject": "confounder", "dag_role_object": "outcome"},
        {"relation_id": "R3", "dag_role_subject": "exposure", "dag_role_object": "outcome"},
    ],
    "excluded_relations": [],
    "node_roles": {
        "A": {"role": "exposure"},
        "Y": {"role": "outcome"},
        "W": {"role": "confounder"},
    },
    "missing_variables": [],
    "proposed_concepts": [],
    "proposed_relations": [],
    "llm_reasoning": "Confounding triangle.",
}


async def test_generate_builds_ontology_grounded_dag() -> None:
    client = _FakeClient(_msg(_FULL_RESULT))
    out = await CausalService(_confounded_triangle(), client, _settings()).generate(_request())

    assert {n.id for n in out.nodes} == {"A", "Y", "W"}
    assert {(e.source, e.to) for e in out.edges} == {("W", "A"), ("W", "Y"), ("A", "Y")}
    assert all(e.supported_by_data for e in out.edges)  # ancrage : concepts mappés
    assert out.graph.exposure_ids == ["A"]
    assert out.graph.outcome_ids == ["Y"]
    assert out.graph.adjusted_ids == ["W"]  # confounder observé → ajusté
    assert out.quality.label == "High"
    assert client.messages.calls == 1


async def test_edges_serialise_with_from_alias() -> None:
    client = _FakeClient(_msg(_FULL_RESULT))
    out = await CausalService(_confounded_triangle(), client, _settings()).generate(_request())
    dumped = out.edges[0].model_dump(by_alias=True)
    assert "from" in dumped and "source" not in dumped


async def test_label_comes_from_taxonomy_metadata() -> None:
    client = _FakeClient(_msg(_FULL_RESULT))
    out = await CausalService(_confounded_triangle(), client, _settings()).generate(_request())
    labels = {n.id: n.label for n in out.nodes}
    assert labels["Y"] == "HbA1c"


async def test_proposed_relation_adds_llm_node_and_edge() -> None:
    result: dict[str, Any] = {
        **_FULL_RESULT,
        "proposed_concepts": [
            {
                "provisional_id": "PROP_med",
                "label": "Medication",
                "domain": "intervention",
                "layer": 1,
                "rationale": "gap",
            }
        ],
        "proposed_relations": [
            {
                "subject_concept_id": "PROP_med",
                "object_concept_id": "Y",
                "predicate": "causally_influences",
                "polarity": "decreases",
                "default_strength": "strong",
                "mechanism_summary": "Med lowers HbA1c.",
            }
        ],
    }
    client = _FakeClient(_msg(result))
    out = await CausalService(_confounded_triangle(), client, _settings()).generate(_request())

    prop_node = next(n for n in out.nodes if n.id == "PROP_med")
    assert prop_node.source == "llm_proposed"
    assert prop_node.label == "Medication"  # méta du concept proposé
    prop_edge = next(e for e in out.edges if e.source == "PROP_med")
    assert prop_edge.direction == "inhibitory"  # polarity decreases
    assert prop_edge.supported_by_data is False


async def test_empty_selection_yields_warning_and_empty_graph() -> None:
    empty: dict[str, Any] = {**_FULL_RESULT, "selected_relations": [], "node_roles": {}}
    client = _FakeClient(_msg(empty))
    out = await CausalService(_confounded_triangle(), client, _settings()).generate(_request())
    assert out.nodes == []
    assert any("empty" in w.lower() for w in out.warnings)
