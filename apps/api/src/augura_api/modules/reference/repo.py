"""Accès base du module reference.

`orgs` est lu scopé au tenant courant (la RLS `tenant_self` n'expose que sa
ligne ; le filtre explicite est une défense en profondeur). Les catalogues CESL
sont globaux (lecture seule, RLS « backend FOR SELECT »).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.reference.models import (
    BiomarkerRangeCatalog,
    CeslSource,
    CeslStudyDesign,
    DomainCatalog,
    EstimandCatalog,
    EstimatorCatalog,
    EvidenceTypeCatalog,
    FrameworkCatalog,
    JurisdictionCatalog,
    LiteratureDesignCatalog,
    Org,
    OutcomeCatalog,
    PiiPatternCatalog,
    VariableGroupCatalog,
    VariableRoleCatalog,
)


class ReferenceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_org(self, tenant_id: TenantId) -> Org | None:
        res = await self.session.execute(select(Org).where(Org.id == tenant_id))
        return res.scalar_one_or_none()

    async def list_cesl_sources(self) -> list[CeslSource]:
        res = await self.session.execute(
            select(CeslSource).where(CeslSource.active.is_(True)).order_by(CeslSource.sort_order)
        )
        return list(res.scalars().all())

    async def list_study_designs(self) -> list[CeslStudyDesign]:
        res = await self.session.execute(
            select(CeslStudyDesign)
            .where(CeslStudyDesign.active.is_(True))
            .order_by(CeslStudyDesign.sort_order)
        )
        return list(res.scalars().all())

    async def list_outcomes(self) -> list[OutcomeCatalog]:
        res = await self.session.execute(
            select(OutcomeCatalog)
            .where(OutcomeCatalog.active.is_(True))
            .order_by(OutcomeCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_estimands(self) -> list[EstimandCatalog]:
        res = await self.session.execute(
            select(EstimandCatalog)
            .where(EstimandCatalog.active.is_(True))
            .order_by(EstimandCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_estimators(self) -> list[EstimatorCatalog]:
        res = await self.session.execute(
            select(EstimatorCatalog)
            .where(EstimatorCatalog.active.is_(True))
            .order_by(EstimatorCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_frameworks(self) -> list[FrameworkCatalog]:
        res = await self.session.execute(
            select(FrameworkCatalog)
            .where(FrameworkCatalog.active.is_(True))
            .order_by(FrameworkCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_evidence_types(self) -> list[EvidenceTypeCatalog]:
        res = await self.session.execute(
            select(EvidenceTypeCatalog)
            .where(EvidenceTypeCatalog.active.is_(True))
            .order_by(EvidenceTypeCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_domains(self) -> list[DomainCatalog]:
        res = await self.session.execute(
            select(DomainCatalog)
            .where(DomainCatalog.active.is_(True))
            .order_by(DomainCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_jurisdictions(self) -> list[JurisdictionCatalog]:
        res = await self.session.execute(
            select(JurisdictionCatalog)
            .where(JurisdictionCatalog.active.is_(True))
            .order_by(JurisdictionCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_literature_designs(self) -> list[LiteratureDesignCatalog]:
        res = await self.session.execute(
            select(LiteratureDesignCatalog)
            .where(LiteratureDesignCatalog.active.is_(True))
            .order_by(LiteratureDesignCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_pii_patterns(self) -> list[PiiPatternCatalog]:
        res = await self.session.execute(
            select(PiiPatternCatalog)
            .where(PiiPatternCatalog.active.is_(True))
            .order_by(PiiPatternCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_biomarker_ranges(self) -> list[BiomarkerRangeCatalog]:
        res = await self.session.execute(
            select(BiomarkerRangeCatalog)
            .where(BiomarkerRangeCatalog.active.is_(True))
            .order_by(BiomarkerRangeCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_variable_groups(self) -> list[VariableGroupCatalog]:
        res = await self.session.execute(
            select(VariableGroupCatalog)
            .where(VariableGroupCatalog.active.is_(True))
            .order_by(VariableGroupCatalog.sort_order)
        )
        return list(res.scalars().all())

    async def list_variable_roles(self) -> list[VariableRoleCatalog]:
        res = await self.session.execute(
            select(VariableRoleCatalog)
            .where(VariableRoleCatalog.active.is_(True))
            .order_by(VariableRoleCatalog.sort_order)
        )
        return list(res.scalars().all())
