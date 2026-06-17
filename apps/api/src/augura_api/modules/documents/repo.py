"""Accès base du module documents — chaque méthode exige un TenantId."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.ids import TenantId
from augura_api.modules.documents.models import GeneratedDocument


class DocumentRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_documents(self, tenant_id: TenantId) -> list[GeneratedDocument]:
        res = await self.session.execute(
            select(GeneratedDocument)
            .where(GeneratedDocument.org_id == tenant_id)
            .order_by(GeneratedDocument.created_at.desc())
        )
        return list(res.scalars().all())

    async def get(self, tenant_id: TenantId, document_id: UUID) -> GeneratedDocument | None:
        res = await self.session.execute(
            select(GeneratedDocument).where(
                GeneratedDocument.org_id == tenant_id, GeneratedDocument.id == document_id
            )
        )
        return res.scalar_one_or_none()

    async def create(
        self, tenant_id: TenantId, *, study_id: UUID | None, doc_type: str
    ) -> GeneratedDocument:
        doc = GeneratedDocument(org_id=tenant_id, study_id=study_id, type=doc_type)
        self.session.add(doc)
        await self.session.flush()
        await self.session.refresh(doc)
        return doc

    async def set_status(
        self,
        tenant_id: TenantId,
        document_id: UUID,
        *,
        status: str,
        storage_path: str | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if storage_path is not None:
            values["storage_path"] = storage_path
        await self.session.execute(
            update(GeneratedDocument)
            .where(
                GeneratedDocument.org_id == tenant_id,
                GeneratedDocument.id == document_id,
            )
            .values(**values)
        )
        await self.session.flush()
