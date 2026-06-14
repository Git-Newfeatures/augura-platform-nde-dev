"""Logique du module corpus : feed paginé, heatmap de couverture, sources, recherche.

Choix : on valide les filtres énumérables (jurisdiction, lifecycle) mais on laisse
`evidence_type`/`source_id` libres (match exact, longueur bornée) pour ne pas rejeter
de valeurs stockées légitimes. age_label et gap_score sont calculés côté service.
"""

from datetime import UTC, date, datetime

from augura_api.core.errors import BadRequestError
from augura_api.modules.corpus import schemas
from augura_api.modules.corpus.repo import CorpusFilters, CorpusRepo

VALID_JURISDICTIONS = {
    "fda",
    "ema",
    "mhra",
    "health_ca",
    "tga",
    "imdrf",
    "global",
    "unknown",
}
VALID_LIFECYCLES = {"pre_market", "post_market", "policy", "unknown"}

# Dimensions de la heatmap (zero-fill sur ces cellules).
COVERAGE_JURISDICTIONS = ["fda", "ema", "imdrf", "global"]
COVERAGE_EVIDENCE_TYPES = [
    "guidance",
    "rwe_study",
    "rct",
    "preprint",
    "trial_record",
    "meta_analysis",
]

MAX_LIMIT = 50
EMBEDDING_DIM = 1536


def _age_label(published: date | None, today: date) -> str | None:
    if published is None:
        return None
    days = (today - published).days
    if days < 0:
        return "0d"
    if days < 7:
        return f"{days}d"
    if days < 30:
        return f"{days // 7}w"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


def _gap(doc_count: int) -> tuple[float, str]:
    if doc_count == 0:
        return 1.0, "high"
    if doc_count < 5:
        return 0.6, "medium"
    if doc_count < 20:
        return 0.3, "low"
    return 0.0, "low"


class CorpusService:
    def __init__(self, repo: CorpusRepo) -> None:
        self.repo = repo

    async def feed(
        self,
        *,
        jurisdiction: str | None,
        evidence_type: str | None,
        source_id: str | None,
        lifecycle: str | None,
        limit: int,
        offset: int,
    ) -> schemas.FeedResponse:
        if jurisdiction and jurisdiction not in VALID_JURISDICTIONS:
            raise BadRequestError("jurisdiction invalide", value=jurisdiction)
        if lifecycle and lifecycle not in VALID_LIFECYCLES:
            raise BadRequestError("lifecycle invalide", value=lifecycle)
        if source_id and len(source_id) > 100:
            raise BadRequestError("source_id trop long")

        limit = min(max(1, limit), MAX_LIMIT)
        offset = max(0, offset)
        filters = CorpusFilters(
            jurisdiction=jurisdiction,
            evidence_type=evidence_type,
            source_id=source_id,
            lifecycle=lifecycle,
        )
        docs, total = await self.repo.feed(filters, limit=limit, offset=offset)
        today = datetime.now(UTC).date()
        items = [
            schemas.FeedDocument(
                id=d.id,
                source_id=d.source_id,
                evidence_type=d.evidence_type,
                jurisdiction=d.jurisdiction,
                lifecycle=d.lifecycle,
                title=d.title,
                summary=d.summary,
                url=d.url,
                published_at=d.published_at,
                is_new=d.is_new,
                age_label=_age_label(d.published_at, today),
            )
            for d in docs
        ]
        return schemas.FeedResponse(meta=schemas.FeedMeta(total=total), documents=items)

    async def coverage(self) -> schemas.CoverageResponse:
        counts = {(j, e): n for j, e, n in await self.repo.coverage_counts()}
        matrix: list[schemas.CoverageCell] = []
        pills: list[schemas.GapPill] = []
        for jur in COVERAGE_JURISDICTIONS:
            for ev in COVERAGE_EVIDENCE_TYPES:
                n = counts.get((jur, ev), 0)
                gap_score, severity = _gap(n)
                matrix.append(
                    schemas.CoverageCell(
                        jurisdiction=jur,
                        evidence_type=ev,
                        doc_count=n,
                        gap_score=gap_score,
                        gap_severity=severity,
                    )
                )
                if severity in ("high", "medium"):
                    pills.append(
                        schemas.GapPill(
                            jurisdiction=jur,
                            evidence_type=ev,
                            gap_severity=severity,
                            gap_score=gap_score,
                            doc_count=n,
                        )
                    )
        pills.sort(key=lambda p: p.gap_score, reverse=True)
        total = await self.repo.total_docs()
        return schemas.CoverageResponse(
            meta=schemas.CoverageMeta(
                total_docs=total,
                jurisdictions=COVERAGE_JURISDICTIONS,
                evidence_types=COVERAGE_EVIDENCE_TYPES,
            ),
            matrix=matrix,
            gap_pills=pills,
        )

    async def sources(self) -> schemas.SourcesResponse:
        counts = await self.repo.source_counts()
        return schemas.SourcesResponse(
            total=sum(c for _, c in counts),
            sources=[schemas.SourceCount(source_id=s, count=c) for s, c in counts],
        )

    async def search(self, req: schemas.SearchRequest) -> list[schemas.SearchHit]:
        if len(req.query_embedding) != EMBEDDING_DIM:
            raise BadRequestError(
                "query_embedding de dimension inattendue",
                expected=EMBEDDING_DIM,
                got=len(req.query_embedding),
            )
        rows = await self.repo.search(req.query_embedding, req.match_count, req.filter)
        return [schemas.SearchHit.model_validate(r) for r in rows]
