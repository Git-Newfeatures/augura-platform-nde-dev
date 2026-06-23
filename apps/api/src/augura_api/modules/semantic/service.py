"""Business logic of the semantic module. The router is a thin adapter."""

from typing import Any, Protocol

from augura_api.modules.semantic import schemas
from augura_api.modules.semantic.models import OntologyRelation, TaxonomyConcept


class _SemanticReader(Protocol):
    async def list_concepts(
        self, *, domain: str | None = ..., active: bool = ...
    ) -> list[TaxonomyConcept]: ...

    async def list_relations(self, *, active: bool = ...) -> list[OntologyRelation]: ...

    async def relations_for_concepts(self, concept_ids: list[str]) -> list[OntologyRelation]: ...

    async def read_bundle(self) -> dict[str, Any]: ...

    async def release_status(self) -> dict[str, Any]: ...


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

    async def bundle(self) -> schemas.SemanticBundle:
        """Governed semantic layer as a single block (14 tables) — GET /semantic/bundle."""
        return schemas.SemanticBundle.model_validate(await self.repo.read_bundle())

    async def release(self) -> schemas.ReleaseStatus:
        """Current release + per-table count — GET /semantic/release."""
        return schemas.ReleaseStatus.model_validate(await self.repo.release_status())
