"""Accès base du module semantic — catalogues globaux (lecture seule)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.modules.semantic.models import (
    DqConstraint,
    TableArchetype,
    TaxonomyConcept,
    TaxonomyDqValidValue,
    TaxonomyMeasurementUnit,
    TaxonomySynonym,
    UnitConversion,
)


class SemanticRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_concepts(
        self, *, domain: str | None = None, active: bool = True
    ) -> list[TaxonomyConcept]:
        stmt = select(TaxonomyConcept)
        if active:
            stmt = stmt.where(TaxonomyConcept.active.is_(True))
        if domain:
            stmt = stmt.where(TaxonomyConcept.augura_domain == domain)
        stmt = stmt.order_by(TaxonomyConcept.local_concept_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_synonyms(self) -> list[TaxonomySynonym]:
        return list((await self.session.execute(select(TaxonomySynonym))).scalars().all())

    async def list_valid_values(self) -> list[TaxonomyDqValidValue]:
        return list((await self.session.execute(select(TaxonomyDqValidValue))).scalars().all())

    async def list_measurement_units(self) -> list[TaxonomyMeasurementUnit]:
        return list((await self.session.execute(select(TaxonomyMeasurementUnit))).scalars().all())

    async def list_unit_conversions(self) -> list[UnitConversion]:
        return list((await self.session.execute(select(UnitConversion))).scalars().all())

    async def list_archetypes(self, *, active: bool = True) -> list[TableArchetype]:
        stmt = select(TableArchetype)
        if active:
            stmt = stmt.where(TableArchetype.active.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_constraints(self, *, status: str | None = "active") -> list[DqConstraint]:
        stmt = select(DqConstraint)
        if status:
            stmt = stmt.where(DqConstraint.status == status)
        return list((await self.session.execute(stmt)).scalars().all())
