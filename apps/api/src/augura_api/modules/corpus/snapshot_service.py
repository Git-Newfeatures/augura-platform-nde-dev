"""Service retrieve-and-freeze : gel d'un jeu de preuves + relecture vérifiée.

Verbe distinct de l'ingestion (`LiteratureService.search_and_ingest`, intouchée).
  - freeze        : construit la charge canonique, calcule le content_hash, insère.
  - read_snapshot : relit, RECALCULE le hash et compare (erreur dure si divergence) —
                    lecture base PURE, zéro appel live (PubMed/CT.gov).
  - sessions/events : journal de l'interaction de recherche.

`to_retrieve_response` mappe le résultat du fan-out (LiteratureRetriever) vers le
schéma de réponse ; la récupération live elle-même vit côté routeur (clients HTTP
request-scoped), pas dans ce service base.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from augura_api.core.errors import NotFoundError
from augura_api.core.tenancy import CurrentTenant
from augura_api.modules.corpus import schemas
from augura_api.modules.corpus.freeze import content_hash, verify_content_hash
from augura_api.modules.corpus.live_repo import LiveRepo
from augura_api.modules.corpus.models import LiteratureEvent, LiteratureSnapshot, SearchSession
from augura_api.modules.corpus.retrieval import RetrievalResult


def to_retrieve_response(result: RetrievalResult) -> schemas.LiteratureRetrieveResponse:
    return schemas.LiteratureRetrieveResponse(
        query=result.query,
        sources=result.sources,
        known_item=result.known_item,
        kind=result.kind,
        groups=[
            schemas.SourceGroupOut(
                source=g.source,
                query_string=g.query_string,
                note=g.note,
                items=[
                    schemas.RetrievedItemOut(
                        source=i.source,
                        id=i.id,
                        title=i.title,
                        query_string=i.query_string,
                        retrieval_date=i.retrieval_date,
                        record=i.record,
                        annotation=i.annotation,
                    )
                    for i in g.items
                ],
            )
            for g in result.groups
        ],
    )


def _build_payload(
    req: schemas.SnapshotWriteRequest, *, created_by: UUID, created_at: datetime
) -> dict[str, Any]:
    """Artefact canonique haché — toutes les valeurs sont JSON-stables (dates en ISO)."""
    return {
        "query": req.query,
        "sources": list(req.sources),
        "model_version": req.model_version,
        "prompt_version": req.prompt_version,
        "study_id": str(req.study_id) if req.study_id else None,
        "created_by": str(created_by),
        "created_at": created_at.isoformat(),
        "results": [
            {
                "source": r.source,
                "id": r.id,
                "title": r.title,
                "query_string": r.query_string,
                "retrieval_date": r.retrieval_date.isoformat(),
                "record": r.record,
                "annotation": r.annotation,
            }
            for r in req.results
        ],
    }


class LiteratureSnapshotService:
    def __init__(self, repo: LiveRepo) -> None:
        self.repo = repo

    # ── Snapshots ────────────────────────────────────────────────────────────
    async def freeze(
        self, tenant: CurrentTenant, req: schemas.SnapshotWriteRequest
    ) -> schemas.LiteratureSnapshot:
        created_at = datetime.now(UTC)
        payload = _build_payload(req, created_by=tenant.user_id, created_at=created_at)
        digest = content_hash(payload)
        row = await self.repo.insert_snapshot(
            tenant.tenant_id,
            study_id=req.study_id,
            created_by=tenant.user_id,
            payload=payload,
            content_hash=digest,
        )
        return self._to_snapshot(row)

    async def read_snapshot(
        self, tenant: CurrentTenant, snapshot_id: UUID
    ) -> schemas.LiteratureSnapshot:
        row = await self.repo.get_snapshot(tenant.tenant_id, snapshot_id)
        if row is None:
            raise NotFoundError("snapshot introuvable", id=str(snapshot_id))
        # Vérification d'intégrité : recalcul du hash sur le payload stocké. Aucune
        # source externe sollicitée — relecture base pure (rejeu sans appel live).
        verify_content_hash({**row.payload, "content_hash": row.content_hash})
        return self._to_snapshot(row)

    def _to_snapshot(self, row: LiteratureSnapshot) -> schemas.LiteratureSnapshot:
        p = row.payload
        return schemas.LiteratureSnapshot(
            id=row.id,
            study_id=row.study_id,
            query=p["query"],
            sources=p["sources"],
            model_version=p["model_version"],
            prompt_version=p["prompt_version"],
            results=[schemas.FrozenResult(**r) for r in p["results"]],
            created_at=datetime.fromisoformat(p["created_at"]),
            created_by=row.created_by,
            content_hash=row.content_hash,
            verified=True,
        )

    # ── Sessions ─────────────────────────────────────────────────────────────
    async def create_session(
        self, tenant: CurrentTenant, req: schemas.SessionCreateRequest
    ) -> schemas.SearchSession:
        row = await self.repo.create_session(
            tenant.tenant_id, created_by=tenant.user_id, study_id=req.study_id, query=req.query
        )
        return self._to_session(row)

    async def get_session(self, tenant: CurrentTenant, session_id: UUID) -> schemas.SearchSession:
        row = await self.repo.get_session(tenant.tenant_id, session_id)
        if row is None:
            raise NotFoundError("session introuvable", id=str(session_id))
        return self._to_session(row)

    async def list_sessions(
        self, tenant: CurrentTenant, *, status: str | None = None
    ) -> list[schemas.SearchSession]:
        rows = await self.repo.list_sessions(tenant.tenant_id, status=status)
        return [self._to_session(r) for r in rows]

    def _to_session(self, row: SearchSession) -> schemas.SearchSession:
        return schemas.SearchSession(
            id=row.id,
            study_id=row.study_id,
            query=row.query,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            created_by=row.created_by,
        )

    # ── Events ───────────────────────────────────────────────────────────────
    async def append_event(
        self, tenant: CurrentTenant, session_id: UUID, req: schemas.EventAppendRequest
    ) -> schemas.LiteratureEvent:
        # La session doit exister pour ce tenant avant d'y rattacher un événement.
        if await self.repo.get_session(tenant.tenant_id, session_id) is None:
            raise NotFoundError("session introuvable", id=str(session_id))
        row = await self.repo.append_event(
            tenant.tenant_id,
            session_id=session_id,
            event_type=req.event_type,
            payload=req.payload,
            created_by=tenant.user_id,
        )
        return self._to_event(row)

    def _to_event(self, row: LiteratureEvent) -> schemas.LiteratureEvent:
        return schemas.LiteratureEvent(
            id=row.id,
            session_id=row.session_id,
            event_type=row.event_type,
            payload=row.payload,
            created_at=row.created_at,
            created_by=row.created_by,
        )
