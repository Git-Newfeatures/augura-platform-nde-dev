"""Logique métier du module reference. Le router est un adaptateur fin."""

from typing import Protocol

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.reference import schemas
from augura_api.modules.reference.models import CeslSource, CeslStudyDesign, Org


class _RefReader(Protocol):
    async def get_org(self, tenant_id: TenantId) -> Org | None: ...
    async def list_cesl_sources(self) -> list[CeslSource]: ...
    async def list_study_designs(self) -> list[CeslStudyDesign]: ...


class ReferenceService:
    def __init__(self, repo: _RefReader) -> None:
        self.repo = repo

    async def tenant_profile(self, tenant: CurrentTenant) -> schemas.TenantProfileOut:
        org = await self.repo.get_org(tenant.tenant_id)
        if org is None:
            raise NotFoundError("organisation introuvable", tenant_id=str(tenant.tenant_id))
        return schemas.TenantProfileOut.model_validate(org)

    async def cesl_sources(self) -> list[schemas.CeslSourceOut]:
        rows = await self.repo.list_cesl_sources()
        return [schemas.CeslSourceOut.model_validate(r) for r in rows]

    async def study_designs(self) -> list[schemas.StudyDesignOut]:
        rows = await self.repo.list_study_designs()
        return [schemas.StudyDesignOut.model_validate(r) for r in rows]
