"""Client PubMed via les E-utilities NCBI (esearch + efetch).

Le backend déployé (Modal) ne peut pas utiliser un MCP plugin : on tape l'API
publique NCBI directement (HTTP). `PubMedClient` est un Protocol injectable ⇒ les
tests fournissent un faux client sans réseau. Le parsing efetch (XML) extrait
titre/abstract/DOI/date/types de publication, mappés vers le modèle Document.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import httpx

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Type de publication PubMed → evidence_type Augura (cf. heatmap de couverture).
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


def _evidence_type(article_types: list[str]) -> str:
    for needle, ev in _EVIDENCE_TYPE_MAP:
        if any(needle.lower() == t.lower() for t in article_types):
            return ev
    return "study"


def _parse_pubdate(article_el: ET.Element) -> date | None:
    # PubDate (Year/Month/Day) ou ArticleDate ; on tolère les champs manquants.
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


def _parse_article(article_el: ET.Element) -> PubMedArticle | None:
    pmid = _text(article_el.find(".//MedlineCitation/PMID"))
    title = _text(article_el.find(".//Article/ArticleTitle"))
    if not pmid or not title:
        return None
    # Abstract : peut être segmenté (plusieurs AbstractText) → on concatène.
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
    )


class PubMedClient(Protocol):
    async def search(self, query: str, max_results: int) -> list[PubMedArticle]: ...

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]: ...


class NCBIPubMedClient:
    """Implémentation réelle : esearch (JSON) → PMIDs, efetch (XML) → articles."""

    def __init__(self, http: httpx.AsyncClient, *, api_key: str | None = None) -> None:
        self._http = http
        self._api_key = api_key

    def _params(self, **extra: str) -> dict[str, str]:
        params = {"db": "pubmed", **extra}
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    async def _esearch(self, term: str, retmax: int) -> list[str]:
        esearch = await self._http.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params=self._params(term=term, retmax=str(retmax), retmode="json", sort="relevance"),
        )
        esearch.raise_for_status()
        idlist: list[str] = esearch.json().get("esearchresult", {}).get("idlist", [])
        return idlist

    async def fetch_by_ids(self, pmids: list[str]) -> list[PubMedArticle]:
        """Efetch direct par PMID — aucun esearch. C'est le chemin known-item PMID :
        en s'adressant à efetch avec `id=`, il est structurellement insensible au bug
        de qualificateur de champ (un PMID n'est jamais réinterprété comme un terme).
        Réutilise le même parseur efetch que `search`."""
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

    async def search(self, query: str, max_results: int) -> list[PubMedArticle]:
        n = max(1, min(50, max_results))
        pmids = await self._esearch(query, n)
        if not pmids:
            return []
        return await self.fetch_by_ids(pmids)
