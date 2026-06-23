"""PubMed client via the NCBI E-utilities (esearch + efetch).

The deployed backend (Modal) cannot use an MCP plugin: we hit the public NCBI
API directly (HTTP). `PubMedClient` is an injectable Protocol ⇒ tests provide a
fake client with no network. The efetch parsing (XML) extracts
title/abstract/DOI/date/publication types, mapped to the Document model.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

import httpx

from augura_api.modules.corpus.filters import (
    SearchFilters,
    build_pubmed_term,
    pubmed_date_params,
)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# PubMed publication type → Augura evidence_type (cf. coverage heatmap).
_EVIDENCE_TYPE_MAP: list[tuple[str, str]] = [
    ("Randomized Controlled Trial", "rct"),
    ("Meta-Analysis", "meta_analysis"),
    ("Systematic Review", "systematic_review"),
    ("Practice Guideline", "guidance"),
    ("Guideline", "guidance"),
    ("Observational Study", "rwe_study"),
    ("Clinical Trial", "rct"),
    ("Review", "review"),
]

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass(frozen=True)
class PubMedArticle:
    pmid: str
    title: str
    abstract: str
    url: str
    evidence_type: str
    article_types: tuple[str, ...] = ()
    published_at: date | None = None
    journal: str | None = None
    doi: str | None = None
    authors: tuple[str, ...] = ()


def _evidence_type(article_types: list[str]) -> str:
    for needle, ev in _EVIDENCE_TYPE_MAP:
        if any(needle.lower() == t.lower() for t in article_types):
            return ev
    return "study"


def _parse_pubdate(article_el: ET.Element) -> date | None:
    # PubDate (Year/Month/Day) or ArticleDate; we tolerate missing fields.
    for path in (".//Article/Journal/JournalIssue/PubDate", ".//Article/ArticleDate"):
        el = article_el.find(path)
        if el is None:
            continue
        year_el = el.find("Year")
        if year_el is None or not (year_el.text or "").strip().isdigit():
            continue
        year = int(year_el.text.strip())  # type: ignore[union-attr]
        month = 1
        m_el = el.find("Month")
        if m_el is not None and m_el.text:
            raw = m_el.text.strip()
            month = int(raw) if raw.isdigit() else _MONTHS.get(raw[:3].lower(), 1)
        day = 1
        d_el = el.find("Day")
        if d_el is not None and (d_el.text or "").strip().isdigit():
            day = int(d_el.text.strip())  # type: ignore[union-attr]
        try:
            return date(year, max(1, min(12, month)), max(1, min(28, day)))
        except ValueError:
            return date(year, 1, 1)
    return None


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _parse_authors(article_el: ET.Element) -> tuple[str, ...]:
    """Authors in "LastName Initials" form (e.g. "Smith JA") in PubMed order.
    Tolerates collective authors (CollectiveName) and missing fields."""
    out: list[str] = []
    for author in article_el.findall(".//Article/AuthorList/Author"):
        last = _text(author.find("LastName"))
        if last:
            initials = _text(author.find("Initials"))
            out.append(f"{last} {initials}".strip() if initials else last)
            continue
        collective = _text(author.find("CollectiveName"))
        if collective:
            out.append(collective)
    return tuple(out)


def _parse_article(article_el: ET.Element) -> PubMedArticle | None:
    pmid = _text(article_el.find(".//MedlineCitation/PMID"))
    title = _text(article_el.find(".//Article/ArticleTitle"))
    if not pmid or not title:
        return None
    # Abstract: may be segmented (several AbstractText) → we concatenate.
    abstract = "\n\n".join(
        _text(a) for a in article_el.findall(".//Article/Abstract/AbstractText")
    ).strip()
    journal = _text(article_el.find(".//Article/Journal/Title")) or None
    types = [_text(t) for t in article_el.findall(".//PublicationTypeList/PublicationType")]
    doi = None
    for aid in article_el.findall(".//ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = _text(aid) or None
            break
    url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return PubMedArticle(
        pmid=pmid,
        title=title,
        abstract=abstract,
        url=url,
        evidence_type=_evidence_type(types),
        article_types=tuple(types),
        published_at=_parse_pubdate(article_el),
        journal=journal,
        doi=doi,
        authors=_parse_authors(article_el),
    )


class PubMedClient(Protocol):
    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[PubMedArticle]: ...

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]: ...


class NCBIPubMedClient:
    """Real implementation: esearch (JSON) → PMIDs, efetch (XML) → articles."""

    def __init__(self, http: httpx.AsyncClient, *, api_key: str | None = None) -> None:
        self._http = http
        self._api_key = api_key

    def _params(self, **extra: str) -> dict[str, str]:
        params = {"db": "pubmed", **extra}
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    async def _esearch(
        self, term: str, retmax: int, *, extra: dict[str, str] | None = None
    ) -> list[str]:
        esearch = await self._http.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params=self._params(
                term=term, retmax=str(retmax), retmode="json", sort="relevance", **(extra or {})
            ),
        )
        esearch.raise_for_status()
        idlist: list[str] = esearch.json().get("esearchresult", {}).get("idlist", [])
        return idlist

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]:
        """Direct efetch by PMID — no esearch. This is the known-item PMID path:
        by calling efetch with `id=`, it is structurally immune to the field-qualifier
        bug (a PMID is never reinterpreted as a term).
        Reuses the same efetch parser as `search`."""
        clean = [p.strip() for p in pmids if p.strip()]
        if not clean:
            return []
        efetch = await self._http.get(
            f"{EUTILS_BASE}/efetch.fcgi",
            params=self._params(id=",".join(clean), retmode="xml", rettype="abstract"),
        )
        efetch.raise_for_status()
        root = ET.fromstring(efetch.text)
        articles = [_parse_article(a) for a in root.findall(".//PubmedArticle")]
        return [a for a in articles if a is not None]

    async def search(
        self,
        query: str,
        max_results: int,
        *,
        filters: SearchFilters | None = None,
        today: date | None = None,
    ) -> list[PubMedArticle]:
        n = max(1, min(50, max_results))
        day = today or datetime.now(UTC).date()
        term = build_pubmed_term(query, filters)
        pmids = await self._esearch(term, n, extra=pubmed_date_params(filters, day))
        if not pmids:
            return []
        return await self.fetch_by_ids(pmids)
