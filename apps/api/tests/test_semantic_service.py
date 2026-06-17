"""Tests unitaires du service semantic — mapping ORM→schéma sans base."""

from augura_api.modules.semantic.models import TaxonomyConcept
from augura_api.modules.semantic.service import SemanticService


class _FakeRepo:
    async def list_concepts(self, *, domain: str | None = None, active: bool = True):
        return [
            TaxonomyConcept(
                local_concept_id="hba1c", layer=1, concept_name="HbA1c",
                augura_domain="cardiometabolic", review_status="approved",
                version="v1", active=True, value_type="numeric",
            )
        ]


async def test_concepts_maps_rows() -> None:
    out = await SemanticService(_FakeRepo()).concepts()  # type: ignore[arg-type]
    assert out[0].local_concept_id == "hba1c"
    assert out[0].concept_name == "HbA1c"
    assert out[0].augura_domain == "cardiometabolic"
