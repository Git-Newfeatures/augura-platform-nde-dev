"""Multi-source fan-out of the live search (retrieve, not ingest).

Retrieval core of the new retrieve-and-freeze endpoint (Tier 2 adds the freeze
+ hash + persistence on top of these results). It touches NEITHER `LiteratureService`
NOR `search_and_ingest`: it is a separate verb sharing the same clients.

Routing:
  - known-item (PMID/DOI/title/NCT) → we query ONLY the identifier's
    source. A miss returns an empty group + an honest message; never a
    fallback to the topical search.
  - topical (free text) → parallel fan-out over the requested sources (default:
    PubMed + CT.gov), results grouped by source.

For EACH result we capture the `query_string` actually sent to the source
(esearch term / efetch-by-id call on the PubMed side; API string on the CT.gov side) —
it is the field the frozen-evidence schema (Tier 2) expects, now controlled directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog

from augura_api.core.errors import BadRequestError
from augura_api.core.llm.runtime import AgentInvalidOutput, AgentUpstreamError
from augura_api.modules.corpus.ctgov import CTGovClient, CTGovStudy
from augura_api.modules.corpus.curation import (
    CurationCandidate,
    Curator,
    apply_curation,
)
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

# Note shown when a source goes down (network/WAF) — e.g. CT.gov returns 403 on
# some datacenter IPs (Modal). We degrade to partial rather than break everything.
_SOURCE_UNAVAILABLE_NOTE = "Source temporarily unavailable (network error) — partial results."


@dataclass(frozen=True)
class RetrievedItem:
    """Normalized result, aligned with the frozen-evidence schema (per citation)."""

    source: str
    id: str  # PMID or NCT
    title: str
    query_string: str  # exact term/call sent to the source
    retrieval_date: date
    record: dict[str, Any]  # structured record, JSON-serializable (freeze)
    annotation: str | None = None  # kept/dismissed/null — set later by the UI
    rationale: str | None = None  # curation justification (None if not curated)


@dataclass(frozen=True)
class SourceGroup:
    source: str
    query_string: str
    items: list[RetrievedItem]
    note: str | None = None  # e.g. known-item miss message


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
        "authors": list(a.authors),
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
        raise BadRequestError("unknown source", value=sorted(unknown))
    return set(sources)


class LiteratureRetriever:
    """Retrieve-only orchestration: known-item routing + parallel topical fan-out."""

    def __init__(
        self, pubmed: PubMedClient, ctgov: CTGovClient, *, curator: Curator | None = None
    ) -> None:
        self._pubmed = pubmed
        self._ctgov = ctgov
        self._curator = curator

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
            # known-item = exact lookup: the date/type filters do not apply.
            return await self._known_item(query, item, srcs, day)
        return await self._topical(query, srcs, max_results, day, filters)

    async def _known_item(
        self, query: str, item: KnownItem, srcs: set[str], day: date
    ) -> RetrievalResult:
        # The identifier determines its source; if it is not requested, nothing to do.
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
        """Isolates a source failure: returns an annotated empty group rather than
        letting the exception fail the whole fan-out (which would cut the stream
        → "network error" on the front side). The working source comes back normally."""
        try:
            return await coro
        except Exception as exc:
            log.warning("retrieve.source_failed", source=source, error=str(exc))
            return SourceGroup(source, "", [], note=_SOURCE_UNAVAILABLE_NOTE)

    def _pool(self, max_results: int) -> int:
        """Over-fetched pool size: no curation ⇒ exactly max_results
        (historical behavior unchanged); otherwise min(50, max(25, max_results*2))."""
        if self._curator is None:
            return max_results
        return min(50, max(25, max_results * 2))

    async def _curate_pubmed(
        self, query: str, articles: list[PubMedArticle], max_results: int
    ) -> list[tuple[PubMedArticle, str | None]]:
        if self._curator is None:
            return [(a, None) for a in articles[:max_results]]
        cands = [CurationCandidate(a.pmid, a.title, a.abstract) for a in articles]
        try:
            refs = await self._curator.curate(query, SOURCE_PUBMED, cands, max_results=max_results)
        except (AgentUpstreamError, AgentInvalidOutput) as exc:
            log.warning("curate.failed", source=SOURCE_PUBMED, error=str(exc))
            return [(a, None) for a in articles[:max_results]]
        applied = apply_curation(refs, {a.pmid: a for a in articles}, max_results=max_results)
        if not applied:
            return [(a, None) for a in articles[:max_results]]
        return [(a, rat or None) for a, rat in applied]

    async def _curate_ctgov(
        self, query: str, studies: list[CTGovStudy], max_results: int
    ) -> list[tuple[CTGovStudy, str | None]]:
        if self._curator is None:
            return [(s, None) for s in studies[:max_results]]
        cands = [
            CurationCandidate(
                s.nct_id,
                s.title,
                f"Conditions: {', '.join(s.conditions)}. Interventions: "
                f"{', '.join(s.interventions)}. Phase {s.phase}. Status {s.status}.",
            )
            for s in studies
        ]
        try:
            refs = await self._curator.curate(query, SOURCE_CTGOV, cands, max_results=max_results)
        except (AgentUpstreamError, AgentInvalidOutput) as exc:
            log.warning("curate.failed", source=SOURCE_CTGOV, error=str(exc))
            return [(s, None) for s in studies[:max_results]]
        applied = apply_curation(refs, {s.nct_id: s for s in studies}, max_results=max_results)
        if not applied:
            return [(s, None) for s in studies[:max_results]]
        return [(s, rat or None) for s, rat in applied]

    async def _pubmed_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        # The term actually sent to esearch (with [pt] filters) IS the query_string.
        term = build_pubmed_term(query, filters)
        articles = await self._pubmed.search(
            query, self._pool(max_results), filters=filters, today=day
        )
        curated = await self._curate_pubmed(query, articles, max_results)
        items = [
            RetrievedItem(SOURCE_PUBMED, a.pmid, a.title, term, day, _pubmed_record(a), rationale=r)
            for a, r in curated
        ]
        return SourceGroup(SOURCE_PUBMED, term, items)

    async def _ctgov_topical(
        self, query: str, max_results: int, day: date, filters: SearchFilters | None
    ) -> SourceGroup:
        extra = ctgov_filter_params(filters, day)
        suffix = "".join(f"&{k}={v}" for k, v in sorted(extra.items()))
        qs = f"query.term={query}{suffix}"  # CT.gov API string actually sent
        studies = await self._ctgov.search(
            query, self._pool(max_results), filters=filters, today=day
        )
        curated = await self._curate_ctgov(query, studies, max_results)
        items = [
            RetrievedItem(SOURCE_CTGOV, s.nct_id, s.title, qs, day, _ctgov_record(s), rationale=r)
            for s, r in curated
        ]
        return SourceGroup(SOURCE_CTGOV, qs, items)
