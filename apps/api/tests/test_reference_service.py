"""Tests unitaires du service reference — mapping ORM→schéma sans base (faux repo)."""

from uuid import UUID

import pytest

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import TenantId, UserId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.reference.models import CeslSource, CeslStudyDesign, Org
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
        return [CeslSource(code="pubmed", label="PubMed", sort_order=10, active=True)]

    async def list_study_designs(self) -> list[CeslStudyDesign]:
        return [
            CeslStudyDesign(
                code="retro_cohort", label="Retrospective cohort", sort_order=10, active=True
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
    assert designs[0].label == "Retrospective cohort"
