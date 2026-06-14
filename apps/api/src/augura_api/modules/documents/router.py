"""Adaptateur HTTP du module documents."""

from uuid import UUID

from fastapi import APIRouter, status

from augura_api.core.deps import CurrentTenantDep, SessionDep
from augura_api.modules.documents import schemas
from augura_api.modules.documents.service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[schemas.GeneratedDocumentOut])
async def list_documents(
    tenant: CurrentTenantDep, session: SessionDep
) -> list[schemas.GeneratedDocumentOut]:
    return await DocumentService(session).list_documents(tenant)


@router.post(
    "", response_model=schemas.GeneratedDocumentCreated, status_code=status.HTTP_202_ACCEPTED
)
async def generate(
    req: schemas.GenerateRequest, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.GeneratedDocumentCreated:
    return await DocumentService(session).generate(tenant, req)


@router.get("/{document_id}", response_model=schemas.GeneratedDocumentOut)
async def get_document(
    document_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.GeneratedDocumentOut:
    return await DocumentService(session).get(tenant, document_id)
