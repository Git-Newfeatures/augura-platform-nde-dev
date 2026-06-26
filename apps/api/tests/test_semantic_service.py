"""Unit tests for the semantic service — ORM→schema mapping without a database."""

from typing import Any

from augura_api.modules.semantic.models import OntologyRelation, TaxonomyConcept
from augura_api.modules.semantic.service import SemanticService


def _relation(relation_id: str, subject: str, obj: str) -> OntologyRelation:
    return OntologyRelation(
        relation_id=relation_id,
        subject_concept_id=subject,
        predicate="causes",
        object_concept_id=obj,
        polarity="positive",
        default_strength="moderate",
        default_temporal_lag="none",
        mechanism_summary="…",
        review_status="approved",
        version="v1",
        active=True,
    )


class _FakeRepo:
    async def list_concepts(self, *, domain: str | None = None, active: bool = True):
        return [
            TaxonomyConcept(
                local_concept_id="hba1c",
                layer=1,
                concept_name="HbA1c",
                augura_domain="cardiometabolic",
                review_status="approved",
                version="v1",
                active=True,
                value_type="numeric",
            )
        ]

    async def list_relations(self, *, active: bool = True):
        return [_relation("r-all", "hba1c", "retinopathy")]

    async def relations_for_concepts(self, concept_ids: list[str]):
        return [_relation("r-sub", concept_ids[0], "retinopathy")]

    async def read_bundle(self):
        # The 18 keys are always present (coalesced to [] on the SQL side).
        empty: dict[str, list[Any]] = {
            t: []
            for t in (
                "taxonomy_concepts",
                "taxonomy_synonyms",
                "taxonomy_standard_codes",
                "taxonomy_therapeutic_areas",
                "taxonomy_relationships",
                "taxonomy_dq_valid_values",
                "taxonomy_measurement_units",
                "unit_conversions",
                "causal_predicates",
                "ontology_relations",
                "ontology_relation_evidence",
                "ontology_relation_qualifiers",
                "dq_constraints",
                "table_archetypes",
                "dimension_kinds",
                "affix_archetypes",
                "affix_archetype_values",
                "affix_archetype_aliases",
            )
        }
        return {**empty, "taxonomy_concepts": [{"local_concept_id": "hba1c", "layer": 1}]}

    async def release_status(self):
        return {
            "release": {"semantic_release_version": "2.2.0", "is_current": True},
            "counts": {"taxonomy_concepts": 1, "ontology_relations": 0},
        }


async def test_concepts_maps_rows() -> None:
    out = await SemanticService(_FakeRepo()).concepts()  # type: ignore[arg-type]
    assert out[0].local_concept_id == "hba1c"
    assert out[0].concept_name == "HbA1c"
    assert out[0].augura_domain == "cardiometabolic"


async def test_relations_lists_all_without_concept_id() -> None:
    out = await SemanticService(_FakeRepo()).relations()  # type: ignore[arg-type]
    assert [r.relation_id for r in out] == ["r-all"]
    assert out[0].subject_concept_id == "hba1c"
    assert out[0].predicate == "causes"


async def test_relations_subgraph_when_concept_id_given() -> None:
    out = await SemanticService(_FakeRepo()).relations(concept_id="hba1c")  # type: ignore[arg-type]
    assert [r.relation_id for r in out] == ["r-sub"]
    assert out[0].subject_concept_id == "hba1c"


async def test_bundle_exposes_18_tables_with_raw_rows() -> None:
    out = await SemanticService(_FakeRepo()).bundle()  # type: ignore[arg-type]
    assert out.taxonomy_concepts[0]["local_concept_id"] == "hba1c"
    # The empty tables remain present (18-key contract).
    assert out.dq_constraints == []
    assert out.table_archetypes == []
    # Dimension grammar / affix archetypes are part of the bundle.
    assert out.dimension_kinds == []
    assert out.affix_archetypes == []
    assert out.affix_archetype_values == []
    assert out.affix_archetype_aliases == []


async def test_release_status_shape() -> None:
    out = await SemanticService(_FakeRepo()).release()  # type: ignore[arg-type]
    assert out.release is not None
    assert out.release["semantic_release_version"] == "2.2.0"
    assert out.counts["taxonomy_concepts"] == 1
