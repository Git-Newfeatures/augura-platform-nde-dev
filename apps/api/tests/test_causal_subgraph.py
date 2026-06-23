"""Unit tests for the deterministic causal subgraph (no LLM, no database)."""

from augura_api.modules.causal.subgraph import (
    Relation,
    build_relations,
    cap_candidates,
    causal_subgraph,
    concept_index,
)
from augura_api.modules.semantic.models import (
    OntologyRelation,
    OntologyRelationEvidence,
    OntologyRelationQualifier,
    TaxonomyConcept,
)


def _rel(rid: str, subj: str, obj: str, *, active: bool = True) -> OntologyRelation:
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
        active=active,
    )


def _relations() -> list[Relation]:
    rows = [_rel("R1", "W", "A"), _rel("R2", "W", "Y"), _rel("R3", "A", "Y"), _rel("R4", "Z", "Q")]
    return build_relations(rows, [], [])


def test_build_relations_drops_inactive() -> None:
    rows = [_rel("R1", "A", "Y"), _rel("R2", "A", "Z", active=False)]
    rels = build_relations(rows, [], [])
    assert {r.id for r in rels} == {"R1"}


def test_build_relations_joins_evidence_and_qualifiers() -> None:
    rows = [_rel("R1", "A", "Y")]
    evidence = [
        OntologyRelationEvidence(
            evidence_id="E1",
            relation_id="R1",
            source_type="rct",
            citation_or_url="Doe 2020",
            evidence_summary="…",
            population_notes="",
            evidence_strength="strong",
            review_status="approved",
        )
    ]
    quals = [
        OntologyRelationQualifier(
            qualifier_id="Q1",
            relation_id="R1",
            qualifier_type="population",
            qualifier_concept_id=None,
            qualifier_value="elderly",
            qualifier_effect="attenuates",
            is_hard_constraint=True,
            notes="",
        )
    ]
    rel = build_relations(rows, evidence, quals)[0]
    assert rel.evidence[0]["citation"] == "Doe 2020"
    assert rel.qualifiers[0]["is_hard_constraint"] is True


def test_subgraph_zero_hop_is_direct_neighbours() -> None:
    # hops=0 makes one pass (faithful port of `for h in 0..=hops`): direct neighbours of A.
    sub = causal_subgraph(_relations(), ["A"], hops=0)
    # A is subject of R3 (A→Y) and object of R1 (W→A); R2 (W→Y) not yet reached.
    assert {r.id for r in sub} == {"R1", "R3"}


def test_subgraph_one_hop_reaches_next_ring() -> None:
    sub = causal_subgraph(_relations(), ["A"], hops=1)
    # 2nd pass from W and Y → R2 (W→Y) joins the subgraph; R4 (Z→Q) out of reach.
    assert {r.id for r in sub} == {"R1", "R2", "R3"}


def test_subgraph_default_excludes_unreachable() -> None:
    sub = causal_subgraph(_relations(), ["A"])  # hops=2 by default
    assert "R4" not in {r.id for r in sub}


def test_cap_prioritises_direct_relations() -> None:
    rels = _relations()
    capped = cap_candidates(rels, ["A"])  # below the cap → returned as-is
    assert capped == rels


def test_concept_index_maps_metadata() -> None:
    concepts = [
        TaxonomyConcept(
            local_concept_id="A",
            layer=2,
            concept_name="Engagement",
            augura_domain="intervention",
            review_status="approved",
            version="v1",
            active=True,
        )
    ]
    idx = concept_index(concepts)
    assert idx["A"].label == "Engagement"
    assert idx["A"].domain == "intervention"
    assert idx["A"].layer == 2
