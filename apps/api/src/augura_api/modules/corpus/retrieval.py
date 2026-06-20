"""Fan-out multi-sources de la recherche live (retrieve, pas ingest).

Cœur de récupération du nouvel endpoint retrieve-and-freeze (Tier 2 ajoute le gel
+ hash + persistance par-dessus ces résultats). Il ne touche NI `LiteratureService`
NI `search_and_ingest` : c'est un autre verbe partageant les mêmes clients.

Aiguillage :
  - known-item (PMID/DOI/titre/NCT) → on interroge UNIQUEMENT la source de
    l'identifiant. Un miss renvoie un groupe vide + un message honnête ; jamais de
    repli sur la recherche topique.
  - topique (texte libre) → fan-out parallèle sur les sources demandées (défaut :
    PubMed + CT.gov), résultats regroupés par source.

Pour CHAQUE résultat on capture le `query_string` réellement envoyé à la source
(terme esearch / appel efetch par id côté PubMed ; chaîne API côté CT.gov) — c'est
le champ que le schéma de preuve gelée (Tier 2) attend, désormais contrôlé en direct.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog

from augura_api.core.errors import BadRequestError
from augura_api.modules.corpus.ctgov import CTGovClient, CTGovStudy
from augura_api.modules.corpus.filters import SearchFilters, build_pubmed_term, ctgov_filter_params
from augura_api.modules.corpus.known_item import (
    KNOWN_ITEM_MISS_MESSAGE,
    SOURCE_CTGOV,
    SOURCE_PUBMED,
    KnownItem,
    classify_known_item,
    resolve_pubmed_known_item,
)
from augura_api.modules.corpus.pubmed import PubMedArticle, PubMedClient

VALID_SOURCES = (SOURCE_PUBMED, SOURCE_CTGOV)

log = structlog.get_logger(__name__)

# Note affichée quand une source tombe (réseau/WAF) — ex. CT.gov renvoie 403 sur
# certaines IP datacenter (Modal). On dégrade en partiel plutôt que tout casser.
_SOURCE_UNAVAILABLE_NOTE = (
    "Source temporairement indisponible (erreur réseau) — résultats partiels."
)


@dataclass(frozen=True)
class RetrievedItem:
    """Résultat normalisé, aligné sur le schéma de preuve gelée (par citation)."""

    source: str
    id: str  # PMID ou NCT
    title: str
    query_string: str  # terme/appel exact envoyé à la source
    retrieval_date: date
    record: dict[str, Any]  # enregistrement structuré, JSON-sérialisable (gel)
    annotation: str | None = None  # kept/dismissed/null — posé plus tard par l'UI


@dataclass(frozen=True)
class SourceGroup:
    source: str
    query_string: str
    items: list[RetrievedItem]
    note: str | None = None  # ex. message de miss known-item


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    sources: list[str]
    known_item: bool
    kind: str | None
    groups: list[SourceGroup]


def _pubmed_record(a: PubMedArticle) -> dict[str, Any]:
    return {
        "pmid": a.pmid,
        "title": a.title,
        "abstract": a.abstract,
        "journal": a.journal,
        "doi": a.doi,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "evidence_type": a.evidence_type,
        "article_types": list(a.article_types),
        "url": a.url,
    }


def _ctgov_record(s: CTGovStudy) -> dict[str, Any]:
    return {
        "nct_id": s.nct_id,
        "title": s.title,
        "status": s.status,
        "phase": s.phase,
        "conditions": list(s.conditions),
        "interventions": list(s.interventions),
        "url": s.url,
    }


def _normalize_sources(sources: set[str] | None) -> set[str]:
    if not sources:
        return set(VALID_SOURCES)
    unknown = sources - set(VALID_SOURCES)
    if unknown:
        raise BadRequestError("source inconnue", value=sorted(unknown))
    return set(sources)


class LiteratureRetriever:
    """Orchestration retrieve-only : known-item routing + fan-out topique parallèle."""

    def __init__(self, pubmed: PubMedClient, ctgov: CTGovClient) -> None:
        self._pubmed = pubmed
        self._ctgov = ctgov

    async def retrieve(
        self,
        query: str,
        *,
        sources: set[str] | None = None,
        max_results: int = 10,
        today: date | None = None,
        filters: SearchFilters | None = None,
    ) -> RetrievalResult:
        srcs = _normalize_sources(sources)
        day = today or datetime.now(UTC).date()
        item = classify_known_item(query)
        if item is not None:
            # known-item = lookup exact : les filtres date/type ne s'appliquent pas.
            return await self._known_item(query, item, srcs, day)
        return await self._topical(query, srcs, max_results, day, filters)

    async def _known_item(
        self, query: str, item: KnownItem, srcs: set[str], day: date
    ) -> RetrievalResult:
        # L'identifiant détermine sa source ; si elle n'est pas demandée, rien à faire.
        if item.source not in srcs:
            return RetrievalResult(query, sorted(srcs), True, str(item.kind), [])

        if item.source == SOURCE_PUBMED:
            articles = await resolve_pubmed_known_item(item, self._pubmed)
            items = [
                RetrievedItem(
                    SOURCE_PUBMED, a.pmid, a.title, item.query_string, day, _pubmed_record(a)
                )
                for a in articles
            ]
        else:  # SOURCE_CTGOV
            study = await self._ctgov.fetch_by_nct(item.value)
            items = (
                [
                    RetrievedItem(
                        SOURCE_CTGOV,
                        study.nct_id,
                        study.title,
                        item.query_string,
                        day,
                        _ctgov_record(study),
                    )
                ]
                if study is not None
                else []
            )

        note = None if items else KNOWN_ITEM_MISS_MESSAGE
        group = SourceGroup(item.source, item.query_string, items, note)
        return RetrievalResult(query, [item.source], True, str(item.kind), [group])

    async def _topical(
        self, query: str, srcs: set[str], max_results: int, day: date, filters: SearchFilters | None
    ) -> RetrievalResult:
        builders: list[Coroutine[Any, Any, SourceGroup]] = []
        order: list[str] = []
        if SOURCE_PUBMED in srcs:
            order.append(SOURCE_PUBMED)
            builders.append(
                self._safe_group(
                    SOURCE_PUBMED, self._pubmed_topical(query, max_results, day, filters)
                )
            )
        if SOURCE_CTGOV in srcs:
            order.append(SOURCE_CTGOV)
            builders.append(
                self._safe_group(
                    SOURCE_CTGOV, self._ctgov_topical(query, max_results, day, filters)
                )
            )
        groups: list[SourceGroup] = await asyncio.gather(*builders)
        return RetrievalResult(query, order, False, None, groups)

    @staticmethod
    async def _safe_group(source: str, coro: Coroutine[Any, Any, SourceGroup]) -> SourceGroup:
        """Isole l'échec d'une source : renvoie un groupe vide annoté plutôt que de
        laisser l'exception faire échouer tout le fan-out (ce qui couperait le stream
        → « network error » côté front). La source qui fonctionne remonte normalement."""
        try:
            return await coro
        except Exception as exc:
            log.warning("retrieve.source_failed", source=source, error=str(exc))
            return SourceGroup(source, "", [], note=_SOURCE_UNAVAILABLE_NOTE)

    async def _pubmed_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        # Le terme réellement envoyé à esearch (avec filtres [pt]) EST le query_string.
        term = build_pubmed_term(query, filters)
        articles = await self._pubmed.search(query, max_results, filters=filters, today=day)
        items = [
            RetrievedItem(SOURCE_PUBMED, a.pmid, a.title, term, day, _pubmed_record(a))
            for a in articles
        ]
        return SourceGroup(SOURCE_PUBMED, term, items)

    async def _ctgov_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        extra = ctgov_filter_params(filters, day)
        suffix = "".join(f"&{k}={v}" for k, v in sorted(extra.items()))
        qs = f"query.term={query}{suffix}"  # chaîne API CT.gov réellement envoyée
        studies = await self._ctgov.search(query, max_results, filters=filters, today=day)
        items = [
            RetrievedItem(SOURCE_CTGOV, s.nct_id, s.title, qs, day, _ctgov_record(s))
            for s in studies
        ]
        return SourceGroup(SOURCE_CTGOV, qs, items)
