"""Accès base du module corpus. RLS : la session voit le corpus global + le tenant."""

import json
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from augura_api.modules.corpus.models import Document


class CorpusFilters:
    def __init__(
        self,
        *,
        jurisdiction: str | None = None,
        evidence_type: str | None = None,
        source_id: str | None = None,
        lifecycle: str | None = None,
    ) -> None:
        self.jurisdiction = jurisdiction
        self.evidence_type = evidence_type
        self.source_id = source_id
        self.lifecycle = lifecycle


class CorpusRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _apply(self, stmt: Select[Any], f: CorpusFilters) -> Select[Any]:
        if f.jurisdiction:
            stmt = stmt.where(Document.jurisdiction == f.jurisdiction)
        if f.evidence_type:
            stmt = stmt.where(Document.evidence_type == f.evidence_type)
        if f.source_id:
            stmt = stmt.where(Document.source_id == f.source_id)
        if f.lifecycle:
            stmt = stmt.where(Document.lifecycle == f.lifecycle)
        return stmt

    async def feed(
        self, f: CorpusFilters, *, limit: int, offset: int
    ) -> tuple[list[Document], int]:
        total = await self.session.scalar(
            self._apply(select(func.count()).select_from(Document), f)
        )
        rows = await self.session.execute(
            self._apply(select(Document), f)
            .order_by(Document.priority_score.desc().nullslast(), Document.ingested_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(total or 0)

    async def source_counts(self) -> list[tuple[str, int]]:
        rows = await self.session.execute(
            select(Document.source_id, func.count())
            .group_by(Document.source_id)
            .order_by(func.count().desc())
        )
        return [(str(src), int(n)) for src, n in rows.all()]

    async def coverage_counts(self) -> list[tuple[str | None, str | None, int]]:
        rows = await self.session.execute(
            select(Document.jurisdiction, Document.evidence_type, func.count()).group_by(
                Document.jurisdiction, Document.evidence_type
            )
        )
        return [(j, e, int(n)) for j, e, n in rows.all()]

    async def total_docs(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(Document)) or 0)

    async def search(
        self, embedding: list[float], match_count: int, filt: dict[str, str]
    ) -> list[dict[str, Any]]:
        emb = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
        rows = await self.session.execute(
            text(
                "select id, document_id, content, similarity, source_id, title "
                "from match_chunks((:emb)::vector, :n, (:filt)::jsonb)"
            ).bindparams(emb=emb, n=match_count, filt=json.dumps(filt))
        )
        return [dict(m) for m in rows.mappings().all()]
