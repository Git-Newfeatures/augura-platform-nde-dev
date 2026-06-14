"""Logique métier du module studies. Le router et les jobs sont des adaptateurs fins."""

from augura_api.core.errors import NotFoundError
from augura_api.core.ids import StudyId
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.studies import schemas
from augura_api.modules.studies.repo import StudyRepo


class StudyService:
    def __init__(self, repo: StudyRepo) -> None:
        self.repo = repo

    async def list_studies(self, tenant: CurrentTenant) -> list[schemas.StudyOut]:
        rows = await self.repo.list_for_tenant(tenant.tenant_id)
        return [schemas.StudyOut.model_validate(r) for r in rows]

    async def create_study(
        self, tenant: CurrentTenant, data: schemas.StudyCreate
    ) -> schemas.StudyOut:
        study = await self.repo.create(
            tenant.tenant_id,
            name=data.name,
            slug=data.slug,
            tagline=data.tagline,
            category=data.category,
            framework=data.framework,
            n_subjects=data.n_subjects,
            created_by=tenant.user_id,
        )
        return schemas.StudyOut.model_validate(study)

    async def get_study(self, tenant: CurrentTenant, study_id: StudyId) -> schemas.StudyOut:
        study = await self.repo.get(tenant.tenant_id, study_id)
        if study is None:
            raise NotFoundError("étude introuvable", study_id=str(study_id))
        return schemas.StudyOut.model_validate(study)

    async def get_state(self, tenant: CurrentTenant, study_id: StudyId) -> schemas.StudyStateOut:
        await self.get_study(tenant, study_id)  # 404 si pas d'accès tenant
        state = await self.repo.latest_state(tenant.tenant_id, study_id)
        if state is None:
            raise NotFoundError("aucun état pour cette étude", study_id=str(study_id))
        return schemas.StudyStateOut.model_validate(state)

    async def save_state(
        self, tenant: CurrentTenant, study_id: StudyId, payload: schemas.StudyStatePut
    ) -> schemas.StudyStateOut:
        await self.get_study(tenant, study_id)
        state = await self.repo.add_state(
            tenant.tenant_id, study_id, state=payload.state, created_by=tenant.user_id
        )
        return schemas.StudyStateOut.model_validate(state)
