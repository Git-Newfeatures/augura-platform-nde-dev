"""Tests unitaires du service semantic — mapping ORM→schéma sans base."""

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
