"""Unit tests for the reference service — ORM→schema mapping without a database (fake repo)."""

from uuid import UUID

import pytest

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
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
from augura_api.modules.reference.service import ReferenceService

TENANT = TenantId(UUID("33cb3ba0-00fe-420b-a8c7-70736aaacc44"))
USER = UserId(UUID("11111111-1111-4111-8111-111111111111"))


def _tenant() -> CurrentTenant:
    return CurrentTenant(tenant_id=TENANT, user_id=USER, role="owner")


class _FakeRepo:
    def __init__(self, org: Org | None) -> None:
        self._org = org

    async def get_org(self, tenant_id: TenantId) -> Org | None:
        return self._org

    async def list_cesl_sources(self) -> list[CeslSource]:
        return [
            CeslSource(
                code="pubmed",
                label="PubMed",
                sort_order=10,
                active=True,
                default_evidence_type="rwe_study",
            )
        ]

    async def list_study_designs(self) -> list[CeslStudyDesign]:
        return [
            CeslStudyDesign(
                code="retro_cohort",
                label="Retrospective cohort",
                sort_order=10,
                active=True,
                tags=[],
                estimands=[],
            )
        ]


async def test_tenant_profile_maps_org() -> None:
    org = Org(
        id=TENANT, name="Lucis", slug="lucis", cesl_profile={"clinical_domain": ["cardiometabolic"]}
    )
    svc = ReferenceService(_FakeRepo(org))  # type: ignore[arg-type]
    out = await svc.tenant_profile(_tenant())
    assert out.slug == "lucis"
    assert out.cesl_profile == {"clinical_domain": ["cardiometabolic"]}


async def test_tenant_profile_missing_org_raises_404() -> None:
    svc = ReferenceService(_FakeRepo(None))  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await svc.tenant_profile(_tenant())


async def test_cesl_sources_and_designs_map() -> None:
    org = Org(id=TENANT, name="Lucis", slug="lucis", cesl_profile={})
    svc = ReferenceService(_FakeRepo(org))  # type: ignore[arg-type]
    sources = await svc.cesl_sources()
    designs = await svc.study_designs()
    assert sources[0].code == "pubmed"
    assert sources[0].default_evidence_type == "rwe_study"
    assert designs[0].label == "Retrospective cohort"


class _FakeCatalogRepo:
    async def list_outcomes(self) -> list[OutcomeCatalog]:
        return [
            OutcomeCatalog(
                code="hba1c_pct",
                short_key="hba1c",
                label="HbA1c change",
                unit="%",
                is_primary=True,
                regulatory_tags=[["g", "DiGA"]],
                verdict="g",
                verdict_label="★ Recommended",
                sort_order=10,
            )
        ]

    async def list_estimands(self) -> list[EstimandCatalog]:
        return [
            EstimandCatalog(
                key="ATE", name="ATE — Average Treatment Effect", recommended=True, sort_order=10
            )
        ]

    async def list_estimators(self) -> list[EstimatorCatalog]:
        return [
            EstimatorCatalog(
                key="lme",
                label="Mixed-effects (LME)",
                short="LME",
                recommended=True,
                bootstrap_pending=False,
                interpretability=4,
                stability=True,
                eligible_study_types=["retro", "prosp"],
                sort_order=10,
            )
        ]

    async def list_frameworks(self) -> list[FrameworkCatalog]:
        return [FrameworkCatalog(code="diga", label="DiGA", sort_order=10)]

    async def list_evidence_types(self) -> list[EvidenceTypeCatalog]:
        return [EvidenceTypeCatalog(code="rct", label="RCT", description="…", sort_order=30)]

    async def list_domains(self) -> list[DomainCatalog]:
        return [DomainCatalog(code="cardiometabolic", label="Cardiometabolic", sort_order=10)]

    async def list_jurisdictions(self) -> list[JurisdictionCatalog]:
        return [JurisdictionCatalog(code="fda", label="FDA 🇺🇸", sort_order=10)]

    async def list_literature_designs(self) -> list[LiteratureDesignCatalog]:
        return [
            LiteratureDesignCatalog(code="rct_parallel", label="Parallel-group RCT", sort_order=10)
        ]

    async def list_pii_patterns(self) -> list[PiiPatternCatalog]:
        return [PiiPatternCatalog(key="email", label="email", pattern=r"\bemail\b", sort_order=20)]

    async def list_biomarker_ranges(self) -> list[BiomarkerRangeCatalog]:
        return [
            BiomarkerRangeCatalog(
                code="bmi", pattern="^bmi$", value_min=10, value_max=70, unit="kg/m²", sort_order=40
            )
        ]

    async def list_variable_groups(self) -> list[VariableGroupCatalog]:
        return [
            VariableGroupCatalog(
                code="outcomes", label="Outcomes", description="…", alias_of=None, sort_order=10
            ),
            VariableGroupCatalog(
                code="environment",
                label=None,
                description=None,
                alias_of="engagement",
                sort_order=100,
            ),
        ]

    async def list_variable_roles(self) -> list[VariableRoleCatalog]:
        return [
            VariableRoleCatalog(
                code="outcome",
                label="Outcome",
                group_code="outcomes",
                selectable=True,
                sort_order=10,
            )
        ]


async def test_outcomes_estimands_estimators_map() -> None:
    svc = ReferenceService(_FakeCatalogRepo())  # type: ignore[arg-type]
    outcomes = await svc.outcomes()
    estimands = await svc.estimands()
    estimators = await svc.estimators()
    assert outcomes[0].code == "hba1c_pct"
    assert outcomes[0].regulatory_tags == [["g", "DiGA"]]
    assert estimands[0].key == "ATE" and estimands[0].recommended is True
    assert estimators[0].eligible_study_types == ["retro", "prosp"]


async def test_dq_rules_groups_two_lists() -> None:
    svc = ReferenceService(_FakeCatalogRepo())  # type: ignore[arg-type]
    rules = await svc.dq_rules()
    assert rules.pii_patterns[0].key == "email"
    assert rules.biomarker_ranges[0].code == "bmi"


async def test_variable_roles_splits_aliases() -> None:
    svc = ReferenceService(_FakeCatalogRepo())  # type: ignore[arg-type]
    out = await svc.variable_roles()
    assert [g.code for g in out.groups] == ["outcomes"]
    assert out.group_aliases == {"environment": "engagement"}
    assert out.roles[0].code == "outcome"
