"""Accès base du module reference.

`orgs` est lu scopé au tenant courant (la RLS `tenant_self` n'expose que sa
ligne ; le filtre explicite est une défense en profondeur). Les catalogues CESL
sont globaux (lecture seule, RLS « backend FOR SELECT »).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.reference.models import CeslSource, CeslStudyDesign, Org


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
