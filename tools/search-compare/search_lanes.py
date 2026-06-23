"""Engine for the three-lane clinical literature-search comparison.

Each lane takes a natural-language clinical question and returns a ``SearchResult``
(answer + supporting sources + status + latency). The lanes are:

1. ``pubmed_llm_search``   — Claude curates an Entrez query, runs NCBI E-utilities,
   then synthesizes a grounded answer citing ``[PMID:...]``. Works today (no key needed,
   an optional ``NCBI_API_KEY`` only raises the rate limit).
2. ``consensus_search``    — calls the documented Consensus ``/v1/quick_search`` API
   (header ``x-api-key``). That API returns papers but no written answer, so Claude
   synthesizes the answer from the returned papers. Needs ``CONSENSUS_API_KEY`` (gated).
3. ``openevidence_search`` — a configurable adapter for OpenEvidence's enterprise API
   (no public/self-serve access; request/response schema is not officially published, so
   the path and field mappings are env-overridable). Needs ``OPENEVIDENCE_API_KEY`` +
   ``OPENEVIDENCE_API_BASE``.

No-fabrication rule: a lane that is not configured returns ``status="not_configured"``;
a lane that errors returns ``status="error"`` with the message. A lane never invents an
answer or sources.

The module reads configuration from environment variables only (the notebook is
responsible for loading a ``.env`` file). Network access is isolated in ``_eutils_get``,
``_consensus_get``, ``_openevidence_post`` and ``_llm_complete`` so tests can monkeypatch
them without hitting the network.
"""

from __future__ import annotations

import html
import json
import os
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import requests

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_MODEL = "claude-opus-4-8"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CONSENSUS_DEFAULT_BASE = "https://api.consensus.app"
TOOL_NAME = "augura-search-compare"

STATUS_OK = "ok"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_ERROR = "error"

_SYNTHESIS_SYSTEM = (
    "You are a careful evidence-based medical research assistant. "
    "Answer only from the provided sources. Do not invent facts or citations. "
    "If the evidence is insufficient, say so plainly."
)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class Source:
    """A single supporting reference shown in a citation card."""

    title: str
    url: str = ""
    year: str = ""
    journal: str = ""
    authors: str = ""  # first few authors, comma-joined
    identifier: str = ""  # e.g. "PMID:12345" or "DOI:10.x/y"

    def label(self) -> str:
        bits = [self.title or "(untitled)"]
        meta = " · ".join(b for b in (self.year, self.journal, self.identifier) if b)
        if meta:
            bits.append(f"({meta})")
        return " ".join(bits)


@dataclass
class SearchResult:
    """The outcome of one lane for one question."""

    method: str
    status: str = STATUS_OK
    answer: str = ""
    sources: list[Source] = field(default_factory=list)
    query_used: str = ""  # the curated query / request actually sent, for transparency
    latency_s: float = 0.0
    error: str = ""
    note: str = ""  # how-to-enable hint or caveat

    @property
    def display_text(self) -> str:
        """What to show in the Answer cell, falling back to note/error."""
        if self.answer:
            return self.answer
        if self.status == STATUS_NOT_CONFIGURED:
            return self.note or "Lane not configured."
        if self.status == STATUS_ERROR:
            return f"Error: {self.error}"
        return self.note or "(no answer)"


# --------------------------------------------------------------------------- #
# LLM access (isolated for testability)
# --------------------------------------------------------------------------- #


def _llm_complete(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    system: str = "",
    max_tokens: int = 1200,
) -> str:
    """Single-shot Anthropic completion. Raises if ANTHROPIC_API_KEY is unset."""
    import anthropic  # imported lazily so the module loads without the SDK installed

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or None,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ).strip()


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort extraction of the first JSON object from an LLM reply."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


# --------------------------------------------------------------------------- #
# Lane 1 — PubMed (LLM-curated)
# --------------------------------------------------------------------------- #


def _eutils_get(endpoint: str, params: dict[str, Any]) -> requests.Response:
    """GET an E-utilities endpoint with NCBI best-practice params applied."""
    payload = dict(params)
    payload.setdefault("tool", TOOL_NAME)
    email = os.getenv("NCBI_EMAIL") or os.getenv("AUGURA_NCBI_EMAIL")
    if email:
        payload.setdefault("email", email)
    api_key = os.getenv("NCBI_API_KEY") or os.getenv("AUGURA_NCBI_API_KEY")
    if api_key:
        payload.setdefault("api_key", api_key)
    response = requests.get(f"{EUTILS_BASE}/{endpoint}", params=payload, timeout=30)
    response.raise_for_status()
    return response


def _build_pubmed_query(question: str, *, model: str) -> str:
    """Use the LLM to turn a clinical question into a curated Entrez query string."""
    prompt = (
        "Convert this clinical question into a single high-precision PubMed Entrez search "
        "query. Use field tags like [Title/Abstract] and [MeSH Terms], Boolean operators, "
        "and relevant synonyms. Return ONLY a JSON object of the form "
        '{"term": "<entrez query>"}. No prose.\n\n'
        f"Question: {question}"
    )
    raw = _llm_complete(
        prompt,
        model=model,
        system="You are a biomedical librarian expert in PubMed/Entrez query syntax.",
        max_tokens=1024,  # curated queries with MeSH + synonyms can be long; avoid truncation
    )
    term = str(_extract_json(raw).get("term", "")).strip()
    return term or question


def _pubmed_esearch(term: str, *, retmax: int) -> list[str]:
    response = _eutils_get(
        "esearch.fcgi",
        {"db": "pubmed", "term": term, "retmode": "json", "retmax": retmax, "sort": "relevance"},
    )
    return response.json().get("esearchresult", {}).get("idlist", [])


def _pubmed_esummary(pmids: list[str]) -> list[Source]:
    if not pmids:
        return []
    response = _eutils_get(
        "esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    )
    result = response.json().get("result", {})
    sources: list[Source] = []
    for pmid in result.get("uids", []):
        rec = result.get(pmid, {})
        doi = next(
            (a.get("value", "") for a in rec.get("articleids", []) if a.get("idtype") == "doi"),
            "",
        )
        authors = ", ".join(a.get("name", "") for a in rec.get("authors", [])[:3])
        identifier = f"PMID:{pmid}" + (f" · DOI:{doi}" if doi else "")
        sources.append(
            Source(
                title=rec.get("title", ""),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                year=str(rec.get("pubdate", ""))[:4],
                journal=rec.get("fulljournalname", ""),
                authors=authors,
                identifier=identifier,
            )
        )
    return sources


def _pubmed_abstracts(pmids: list[str]) -> dict[str, dict[str, str]]:
    if not pmids:
        return {}
    response = _eutils_get(
        "efetch.fcgi",
        {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"},
    )
    root = ET.fromstring(response.content)
    out: dict[str, dict[str, str]] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//MedlineCitation/PMID")
        pmid = pmid_el.text or "" if pmid_el is not None else ""
        title_el = article.find(".//Article/ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""
        abstract = " ".join(
            "".join(part.itertext()) for part in article.findall(".//Abstract/AbstractText")
        ).strip()
        if pmid:
            out[pmid] = {"title": title, "abstract": abstract}
    return out


def pubmed_llm_search(
    question: str, *, model: str = DEFAULT_MODEL, retmax: int = 8
) -> SearchResult:
    """Lane 1: LLM-curated PubMed query → E-utilities → LLM synthesis."""
    started = time.perf_counter()
    result = SearchResult(method="PubMed (LLM-curated)")
    try:
        term = _build_pubmed_query(question, model=model)
        result.query_used = term
        pmids = _pubmed_esearch(term, retmax=retmax)
        result.sources = _pubmed_esummary(pmids)
        abstracts = _pubmed_abstracts(pmids)
        context = "\n\n".join(
            f"[PMID:{pmid}] {data['title']}\n{data['abstract']}"
            for pmid, data in abstracts.items()
            if data["abstract"]
        )
        if context:
            result.answer = _llm_complete(
                f"Question: {question}\n\n"
                "Using ONLY the abstracts below, give a concise evidence-based answer and "
                "cite supporting PMIDs inline like [PMID:12345].\n\n"
                f"{context}",
                model=model,
                system=_SYNTHESIS_SYSTEM,
                max_tokens=1200,
            )
        else:
            result.answer = (
                f"No PubMed abstracts were available to synthesize an answer (query: {term})."
            )
    except Exception as exc:  # noqa: BLE001 — isolate the lane, surface the message
        result.status = STATUS_ERROR
        result.error = f"{type(exc).__name__}: {exc}"
    result.latency_s = round(time.perf_counter() - started, 2)
    return result


# --------------------------------------------------------------------------- #
# Lane 2 — Consensus
# --------------------------------------------------------------------------- #


def _author_name(author: Any) -> str:
    """Coerce a Consensus author entry (string or {"name": ...} object) to a name string."""
    if isinstance(author, dict):
        return str(author.get("name", "") or author.get("author", ""))
    return str(author)


def _consensus_get(query: str, *, api_key: str, base: str, retmax: int) -> dict[str, Any]:
    response = requests.get(
        f"{base.rstrip('/')}/v1/quick_search",
        params={"query": query},
        headers={"x-api-key": api_key, "Accept": "application/json"},
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def consensus_search(
    question: str,
    *,
    model: str = DEFAULT_MODEL,
    synthesize: bool = True,
    retmax: int = 10,
) -> SearchResult:
    """Lane 2: Consensus /v1/quick_search papers, with optional LLM synthesis.

    The Consensus quick_search API returns ranked papers but no written answer, so when
    ``synthesize`` is true we ask Claude to synthesize an answer from those papers.
    """
    started = time.perf_counter()
    result = SearchResult(method="Consensus")
    api_key = os.getenv("CONSENSUS_API_KEY")
    base = os.getenv("CONSENSUS_API_BASE", CONSENSUS_DEFAULT_BASE)
    if not api_key:
        result.status = STATUS_NOT_CONFIGURED
        result.note = (
            "Set CONSENSUS_API_KEY to enable. Access is application-gated — apply at "
            "https://consensus.app/home/api/ (endpoint GET /v1/quick_search, header x-api-key)."
        )
        result.latency_s = round(time.perf_counter() - started, 2)
        return result
    try:
        data = _consensus_get(question, api_key=api_key, base=base, retmax=retmax)
        papers = (data.get("results") or [])[:retmax]
        result.query_used = question
        for paper in papers:
            doi = paper.get("doi", "")
            url = paper.get("url", "") or (f"https://doi.org/{doi}" if doi else "")
            # Consensus' response shape is gated/unverified — authors may be strings or objects.
            authors = ", ".join(_author_name(a) for a in (paper.get("authors") or [])[:3])
            result.sources.append(
                Source(
                    title=paper.get("title", ""),
                    url=url,
                    year=str(paper.get("publish_year", "")),
                    journal=paper.get("journal_name", ""),
                    authors=authors,
                    identifier=f"DOI:{doi}" if doi else "",
                )
            )
        if not papers:
            result.answer = "Consensus returned no papers for this query."
        elif synthesize:
            context = "\n\n".join(
                f"[{i + 1}] {p.get('title', '')} ({p.get('publish_year', '')}). "
                f"{p.get('abstract', '')}"
                for i, p in enumerate(papers)
            )
            result.answer = _llm_complete(
                f"Question: {question}\n\n"
                "Using ONLY the paper abstracts below (retrieved from Consensus), give a "
                "concise evidence-based answer and cite sources inline like [1], [2].\n\n"
                f"{context}",
                model=model,
                system=_SYNTHESIS_SYSTEM,
                max_tokens=1200,
            )
            result.note = (
                "Answer synthesized by Claude from Consensus papers — the quick_search API "
                "returns ranked papers, not a written answer."
            )
        else:
            result.answer = f"Consensus returned {len(papers)} papers (synthesis disabled)."
    except Exception as exc:  # noqa: BLE001
        result.status = STATUS_ERROR
        result.error = f"{type(exc).__name__}: {exc}"
    result.latency_s = round(time.perf_counter() - started, 2)
    return result


# --------------------------------------------------------------------------- #
# Lane 3 — OpenEvidence (configurable, gated)
# --------------------------------------------------------------------------- #


def _openevidence_post(
    question: str, *, api_key: str, base: str, path: str, org_id: str
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if org_id:
        headers["X-Org-Id"] = org_id
    response = requests.post(
        f"{base.rstrip('/')}{path}",
        headers=headers,
        json={"question": question},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def openevidence_search(question: str, *, model: str = DEFAULT_MODEL, **_: Any) -> SearchResult:
    """Lane 3: configurable adapter for OpenEvidence's gated enterprise API.

    OpenEvidence has no public/self-serve API and its request/response schema is not
    officially published. Everything here is therefore overridable via environment
    variables so it can be matched to the real (gated) spec without code changes:

      OPENEVIDENCE_API_BASE     base URL (required to activate the lane)
      OPENEVIDENCE_API_KEY      bearer token (required to activate the lane)
      OPENEVIDENCE_ORG_ID       organization id (sent as X-Org-Id if set)
      OPENEVIDENCE_SEARCH_PATH  request path (default "/analysis" — UNVERIFIED, confirm it)
      OPENEVIDENCE_ANSWER_FIELD response field holding the answer text (default "answer")
      OPENEVIDENCE_SOURCES_FIELD response field holding the citation list (default "references")

    Until both base and key are set, the lane reports ``not_configured`` and never fires.
    """
    started = time.perf_counter()
    result = SearchResult(method="OpenEvidence")
    api_key = os.getenv("OPENEVIDENCE_API_KEY")
    base = os.getenv("OPENEVIDENCE_API_BASE")
    if not (api_key and base):
        result.status = STATUS_NOT_CONFIGURED
        result.note = (
            "No public API. Enterprise access + a signed BAA are required "
            "(contact sales@openevidence.com / https://www.openevidence.com/product/api). "
            "Then set OPENEVIDENCE_API_BASE + OPENEVIDENCE_API_KEY (+ OPENEVIDENCE_ORG_ID) "
            "and verify the request path / field mappings against the official spec."
        )
        result.latency_s = round(time.perf_counter() - started, 2)
        return result
    try:
        data = _openevidence_post(
            question,
            api_key=api_key,
            base=base,
            path=os.getenv("OPENEVIDENCE_SEARCH_PATH", "/analysis"),
            org_id=os.getenv("OPENEVIDENCE_ORG_ID", ""),
        )
        answer_field = os.getenv("OPENEVIDENCE_ANSWER_FIELD", "answer")
        sources_field = os.getenv("OPENEVIDENCE_SOURCES_FIELD", "references")
        result.query_used = question
        result.answer = str(data.get(answer_field, "") or "")
        for src in data.get(sources_field, []) or []:
            if isinstance(src, dict):
                result.sources.append(
                    Source(
                        title=src.get("title", "") or src.get("citation", ""),
                        url=src.get("url", ""),
                        year=str(src.get("year", "")),
                        journal=src.get("journal", ""),
                        identifier=src.get("doi", ""),
                    )
                )
            else:
                result.sources.append(Source(title=str(src)))
        result.note = (
            "⚠️ Response parsed via a configurable mapping — confirm field names against "
            "the official OpenEvidence API spec."
        )
    except Exception as exc:  # noqa: BLE001
        result.status = STATUS_ERROR
        result.error = f"{type(exc).__name__}: {exc}"
    result.latency_s = round(time.perf_counter() - started, 2)
    return result


# --------------------------------------------------------------------------- #
# Orchestration + rendering
# --------------------------------------------------------------------------- #

LANES: list[Callable[..., SearchResult]] = [
    pubmed_llm_search,
    consensus_search,
    openevidence_search,
]


def _safe_lane(fn: Callable[..., SearchResult], question: str, model: str) -> SearchResult:
    """Run a lane so that even an unexpected failure becomes an error SearchResult."""
    try:
        return fn(question, model=model)
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        name = getattr(fn, "__name__", "lane")
        return SearchResult(method=name, status=STATUS_ERROR, error=f"{type(exc).__name__}: {exc}")


def compare(question: str, *, model: str = DEFAULT_MODEL) -> list[SearchResult]:
    """Run all three lanes concurrently; order of the returned list matches ``LANES``."""
    results: list[SearchResult | None] = [None] * len(LANES)
    with ThreadPoolExecutor(max_workers=len(LANES)) as executor:
        futures = {
            executor.submit(_safe_lane, fn, question, model): i for i, fn in enumerate(LANES)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return [r for r in results if r is not None]


def lane_status() -> dict[str, str]:
    """Report which lanes are ready to run given the current environment."""
    anthropic_ready = bool(os.getenv("ANTHROPIC_API_KEY"))
    return {
        "PubMed (LLM-curated)": "ready" if anthropic_ready else "needs ANTHROPIC_API_KEY",
        "Consensus": "ready"
        if (os.getenv("CONSENSUS_API_KEY") and anthropic_ready)
        else "needs CONSENSUS_API_KEY (gated) + ANTHROPIC_API_KEY",
        "OpenEvidence": "ready"
        if (os.getenv("OPENEVIDENCE_API_KEY") and os.getenv("OPENEVIDENCE_API_BASE"))
        else "needs enterprise API (gated)",
    }


def results_to_dataframe(results: list[SearchResult]) -> Any:
    """Build a pandas comparison table (rows = lanes)."""
    import pandas as pd

    rows = [
        {
            "Method": r.method,
            # Append the provenance/how-to-enable note (when an answer is present) so the
            # dataframe view is as honest as the HTML view about synthesized answers.
            "Answer": r.display_text + (f"\n\n[{r.note}]" if r.note and r.answer else ""),
            "Status": r.status,
            "Top sources": "\n".join(f"• {s.label()}" for s in r.sources[:5]) or "—",
            "Latency (s)": r.latency_s,
        }
        for r in results
    ]
    return pd.DataFrame(rows, columns=["Method", "Status", "Answer", "Top sources", "Latency (s)"])


_STATUS_COLORS = {
    STATUS_OK: "#137333",
    STATUS_NOT_CONFIGURED: "#9a6700",
    STATUS_ERROR: "#b3261e",
}


def _safe_url(url: str) -> str:
    """Return the URL only if it uses an http(s) scheme, else "" (blocks javascript:/data:)."""
    from urllib.parse import urlparse

    try:
        return url if urlparse(url).scheme in ("http", "https") else ""
    except (ValueError, AttributeError):
        return ""


def results_to_html(results: list[SearchResult]) -> str:
    """Render a styled HTML comparison table with clickable source links."""

    def esc(text: str) -> str:
        return html.escape(str(text or ""))

    def sources_html(sources: list[Source]) -> str:
        if not sources:
            return "<span style='color:#888'>—</span>"
        items = []
        for s in sources[:6]:
            label = esc(s.label())
            # Only emit a link for http(s) URLs — source URLs come from third-party APIs,
            # so reject javascript:/data: schemes that would execute on click.
            safe = _safe_url(s.url)
            link = (
                f"<a href='{esc(safe)}' target='_blank' rel='noopener noreferrer'>{label}</a>"
                if safe
                else label
            )
            items.append(f"<li style='margin-bottom:4px'>{link}</li>")
        return f"<ul style='margin:0;padding-left:18px'>{''.join(items)}</ul>"

    header = (
        "<tr>"
        "<th style='text-align:left;padding:8px'>Method</th>"
        "<th style='text-align:left;padding:8px'>Status</th>"
        "<th style='text-align:left;padding:8px;min-width:320px'>Answer</th>"
        "<th style='text-align:left;padding:8px;min-width:260px'>Top sources</th>"
        "<th style='text-align:left;padding:8px'>Latency</th>"
        "</tr>"
    )
    body_rows = []
    for r in results:
        color = _STATUS_COLORS.get(r.status, "#444")
        badge = (
            f"<span style='background:{color};color:#fff;border-radius:10px;"
            f"padding:2px 8px;font-size:12px'>{esc(r.status)}</span>"
        )
        note = (
            f"<div style='color:#9a6700;font-size:12px;margin-top:6px'>{esc(r.note)}</div>"
            if r.note
            else ""
        )
        body_rows.append(
            "<tr style='border-top:1px solid #e0e0e0;vertical-align:top'>"
            f"<td style='padding:8px;font-weight:600'>{esc(r.method)}</td>"
            f"<td style='padding:8px'>{badge}</td>"
            f"<td style='padding:8px;white-space:pre-wrap'>{esc(r.display_text)}{note}</td>"
            f"<td style='padding:8px'>{sources_html(r.sources)}</td>"
            f"<td style='padding:8px'>{r.latency_s}s</td>"
            "</tr>"
        )
    return (
        "<table style='border-collapse:collapse;width:100%;font-family:"
        "-apple-system,Segoe UI,sans-serif;font-size:14px'>"
        f"<thead style='background:#f5f5f7'>{header}</thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )
