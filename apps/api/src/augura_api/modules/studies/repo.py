"""Accès base du module studies — chaque méthode exige un TenantId (spec §4).

Le filtre `org_id == tenant_id` est une défense en profondeur : la RLS l'impose
déjà côté Postgres, mais le repo ne s'y fie pas.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import StudyId, TenantId, UserId
from augura_api.modules.studies.models import Study, StudyState


class StudyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_tenant(self, tenant_id: TenantId) -> list[Study]:
        res = await self.session.execute(
            select(Study).where(Study.org_id == tenant_id).order_by(Study.created_at.desc())
        )
        return list(res.scalars().all())

    async def get(self, tenant_id: TenantId, study_id: StudyId) -> Study | None:
        res = await self.session.execute(
            select(Study).where(Study.org_id == tenant_id, Study.id == study_id)
        )
        return res.scalar_one_or_none()

    async def create(
        self,
        tenant_id: TenantId,
        *,
        name: str,
        slug: str,
        tagline: str | None,
        category: str | None,
        framework: str | None,
        n_subjects: int | None,
        created_by: UserId,
    ) -> Study:
        study = Study(
            org_id=tenant_id,
            name=name,
            slug=slug,
            tagline=tagline,
            category=category,
            framework=framework,
            n_subjects=n_subjects,
            created_by=created_by,
        )
        self.session.add(study)
        await self.session.flush()
        await self.session.refresh(study)
        return study

    async def latest_state(self, tenant_id: TenantId, study_id: StudyId) -> StudyState | None:
        res = await self.session.execute(
            select(StudyState)
            .join(Study, Study.id == StudyState.study_id)
            .where(Study.org_id == tenant_id, StudyState.study_id == study_id)
            .order_by(StudyState.version.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def add_state(
        self,
        tenant_id: TenantId,
        study_id: StudyId,
        *,
        state: dict[str, Any],
        created_by: UserId,
    ) -> StudyState:
        res = await self.session.execute(
            select(func.coalesce(func.max(StudyState.version), 0))
            .join(Study, Study.id == StudyState.study_id)
            .where(Study.org_id == tenant_id, StudyState.study_id == study_id)
        )
        next_version = int(res.scalar_one()) + 1
        row = StudyState(
            study_id=study_id, version=next_version, state=state, created_by=created_by
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row
