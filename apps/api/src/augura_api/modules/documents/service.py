"""Logic of the documents module: asynchronous generation via job (spec §5)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.core.errors import NotFoundError
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules import analytics
from augura_api.modules.documents import schemas
from augura_api.modules.documents.repo import DocumentRepo
from augura_api.modules.jobs import create_job


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_documents(self, tenant: CurrentTenant) -> list[schemas.GeneratedDocumentOut]:
        rows = await DocumentRepo(self.session).list_documents(tenant.tenant_id)
        return [schemas.GeneratedDocumentOut.model_validate(r) for r in rows]

    async def get(self, tenant: CurrentTenant, document_id: UUID) -> schemas.GeneratedDocumentOut:
        doc = await DocumentRepo(self.session).get(tenant.tenant_id, document_id)
        if doc is None:
            raise NotFoundError("document not found", document_id=str(document_id))
        return schemas.GeneratedDocumentOut.model_validate(doc)

    async def download(self, tenant: CurrentTenant, document_id: UUID) -> tuple[str, bytes]:
        """Returns (type, bytes) of the generated document, read FROM THE DATABASE (content) —
        consistent cross-container on Modal. NotFoundError until the document is `ready`."""
        doc = await DocumentRepo(self.session).get(tenant.tenant_id, document_id)
        if doc is None:
            raise NotFoundError("document not found", document_id=str(document_id))
        if doc.content is None:
            raise NotFoundError("document not yet generated", document_id=str(document_id))
        return doc.type, bytes(doc.content)

    async def generate(
        self, tenant: CurrentTenant, req: schemas.GenerateRequest
    ) -> schemas.GeneratedDocumentCreated:
        doc = await DocumentRepo(self.session).create(
            tenant.tenant_id, study_id=req.study_id, doc_type=req.type
        )
        job = await create_job(
            self.session,
            tenant.tenant_id,
            type=f"generate_{req.type}",
            payload={
                "document_id": str(doc.id),
                "study_id": str(req.study_id) if req.study_id else None,
            },
            idempotency_key=req.idempotency_key,
        )
        await analytics.log_usage(
            self.session,
            tenant_id=tenant.tenant_id,
            user_id=tenant.user_id,
            event_type="document.requested",
            route="/documents",
            metadata={"document_id": str(doc.id), "type": req.type},
        )
        # The worker (jobs.runner) generates the document and marks it `ready` after the
        # response — local fallback of the Modal WeasyPrint/python-docx worker → Storage.
        return schemas.GeneratedDocumentCreated(
            document_id=doc.id, job_id=job.id, status=doc.status
        )
