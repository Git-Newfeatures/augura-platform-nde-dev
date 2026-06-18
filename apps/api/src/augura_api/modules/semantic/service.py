"""Logique métier du module semantic. Le router est un adaptateur fin."""

from typing import Protocol

from augura_api.modules.semantic import schemas
from augura_api.modules.semantic.models import OntologyRelation, TaxonomyConcept


class _SemanticReader(Protocol):
    async def list_concepts(
        self, *, domain: str | None = ..., active: bool = ...
    ) -> list[TaxonomyConcept]: ...

    async def list_relations(self, *, active: bool = ...) -> list[OntologyRelation]: ...

    async def relations_for_concepts(self, concept_ids: list[str]) -> list[OntologyRelation]: ...


class SemanticService:
    def __init__(self, repo: _SemanticReader) -> None:
        self.repo = repo

    async def concepts(
        self, *, domain: str | None = None, active: bool = True
    ) -> list[schemas.ConceptOut]:
        rows = await self.repo.list_concepts(domain=domain, active=active)
        return [schemas.ConceptOut.model_validate(r) for r in rows]

    async def relations(
        self, *, concept_id: str | None = None, active: bool = True
    ) -> list[schemas.RelationOut]:
        rows = (
            await self.repo.relations_for_concepts([concept_id])
            if concept_id
            else await self.repo.list_relations(active=active)
        )
        return [schemas.RelationOut.model_validate(r) for r in rows]
