"""Business logic for the reference module. The router is a thin adapter."""

from typing import Protocol

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.reference import schemas
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


class _RefReader(Protocol):
    async def get_org(self, tenant_id: TenantId) -> Org | None: ...
    async def list_cesl_sources(self) -> list[CeslSource]: ...
    async def list_study_designs(self) -> list[CeslStudyDesign]: ...
    async def list_outcomes(self) -> list[OutcomeCatalog]: ...
    async def list_estimands(self) -> list[EstimandCatalog]: ...
    async def list_estimators(self) -> list[EstimatorCatalog]: ...
    async def list_frameworks(self) -> list[FrameworkCatalog]: ...
    async def list_evidence_types(self) -> list[EvidenceTypeCatalog]: ...
    async def list_domains(self) -> list[DomainCatalog]: ...
    async def list_jurisdictions(self) -> list[JurisdictionCatalog]: ...
    async def list_literature_designs(self) -> list[LiteratureDesignCatalog]: ...
    async def list_pii_patterns(self) -> list[PiiPatternCatalog]: ...
    async def list_biomarker_ranges(self) -> list[BiomarkerRangeCatalog]: ...
    async def list_variable_groups(self) -> list[VariableGroupCatalog]: ...
    async def list_variable_roles(self) -> list[VariableRoleCatalog]: ...


class ReferenceService:
    def __init__(self, repo: _RefReader) -> None:
        self.repo = repo

    async def tenant_profile(self, tenant: CurrentTenant) -> schemas.TenantProfileOut:
        org = await self.repo.get_org(tenant.tenant_id)
        if org is None:
            raise NotFoundError("organization not found", tenant_id=str(tenant.tenant_id))
        return schemas.TenantProfileOut.model_validate(org)

    async def cesl_sources(self) -> list[schemas.CeslSourceOut]:
        rows = await self.repo.list_cesl_sources()
        return [schemas.CeslSourceOut.model_validate(r) for r in rows]

    async def study_designs(self) -> list[schemas.StudyDesignOut]:
        rows = await self.repo.list_study_designs()
        return [schemas.StudyDesignOut.model_validate(r) for r in rows]

    async def outcomes(self) -> list[schemas.OutcomeOut]:
        return [schemas.OutcomeOut.model_validate(r) for r in await self.repo.list_outcomes()]

    async def estimands(self) -> list[schemas.EstimandOut]:
        return [schemas.EstimandOut.model_validate(r) for r in await self.repo.list_estimands()]

    async def estimators(self) -> list[schemas.EstimatorOut]:
        return [schemas.EstimatorOut.model_validate(r) for r in await self.repo.list_estimators()]

    async def frameworks(self) -> list[schemas.FrameworkOut]:
        return [schemas.FrameworkOut.model_validate(r) for r in await self.repo.list_frameworks()]

    async def evidence_types(self) -> list[schemas.CodeLabelOut]:
        return [
            schemas.CodeLabelOut.model_validate(r) for r in await self.repo.list_evidence_types()
        ]

    async def domains(self) -> list[schemas.CodeLabelOut]:
        return [schemas.CodeLabelOut.model_validate(r) for r in await self.repo.list_domains()]

    async def jurisdictions(self) -> list[schemas.CodeLabelOut]:
        return [
            schemas.CodeLabelOut.model_validate(r) for r in await self.repo.list_jurisdictions()
        ]

    async def literature_designs(self) -> list[schemas.CodeLabelOut]:
        return [
            schemas.CodeLabelOut.model_validate(r)
            for r in await self.repo.list_literature_designs()
        ]

    async def dq_rules(self) -> schemas.DqRulesOut:
        return schemas.DqRulesOut(
            pii_patterns=[
                schemas.PiiPatternOut.model_validate(r) for r in await self.repo.list_pii_patterns()
            ],
            biomarker_ranges=[
                schemas.BiomarkerRangeOut.model_validate(r)
                for r in await self.repo.list_biomarker_ranges()
            ],
        )

    async def variable_roles(self) -> schemas.VariableRolesOut:
        rows = await self.repo.list_variable_groups()
        groups = [schemas.VariableGroupOut.model_validate(g) for g in rows if g.alias_of is None]
        aliases = {g.code: g.alias_of for g in rows if g.alias_of is not None}
        roles = [
            schemas.VariableRoleOut.model_validate(r) for r in await self.repo.list_variable_roles()
        ]
        return schemas.VariableRolesOut(groups=groups, roles=roles, group_aliases=aliases)
