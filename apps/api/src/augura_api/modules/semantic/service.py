"""Logique métier du module semantic. Le router est un adaptateur fin."""

from typing import Protocol

from augura_api.modules.semantic import schemas
from augura_api.modules.semantic.models import TaxonomyConcept


class _ConceptReader(Protocol):
    async def list_concepts(
        self, *, domain: str | None = ..., active: bool = ...
    ) -> list[TaxonomyConcept]: ...


class SemanticService:
    def __init__(self, repo: _ConceptReader) -> None:
        self.repo = repo

    async def concepts(
        self, *, domain: str | None = None, active: bool = True
    ) -> list[schemas.ConceptOut]:
        rows = await self.repo.list_concepts(domain=domain, active=active)
        return [schemas.ConceptOut.model_validate(r) for r in rows]
