"""Adaptateur HTTP du module documents."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, status
from fastapi.responses import Response

from augura_api.core.deps import CurrentTenantDep, SessionDep, SettingsDep
from augura_api.jobs.runner import enqueue_job
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
    req: schemas.GenerateRequest,
    tenant: CurrentTenantDep,
    session: SessionDep,
    settings: SettingsDep,
    background_tasks: BackgroundTasks,
) -> schemas.GeneratedDocumentCreated:
    created = await DocumentService(session).generate(tenant, req)
    # Le worker rend le dossier (HTML print-friendly) et marque le document `ready`
    # après la réponse — fallback local du worker Modal WeasyPrint/python-docx.
    enqueue_job(background_tasks, tenant, created.job_id, settings=settings)
    return created


@router.get("/{document_id}", response_model=schemas.GeneratedDocumentOut)
async def get_document(
    document_id: UUID, tenant: CurrentTenantDep, session: SessionDep
) -> schemas.GeneratedDocumentOut:
    return await DocumentService(session).get(tenant, document_id)


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    tenant: CurrentTenantDep,
    session: SessionDep,
) -> Response:
    """Sert les octets du dossier généré (scopé tenant), lus EN BASE
    (generated_documents.content) — cohérent cross-conteneur sur Modal, contrairement au
    disque local éphémère. 404 tant que le dossier n'est pas `ready`."""
    doc_type, data = await DocumentService(session).download(tenant, document_id)
    filename = f"{doc_type}-{document_id}.html"
    return Response(
        content=data,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
