"""Known-item router: routes an input toward an exact search.

Shared building block of the new retrieve-and-freeze endpoint (distinct from the
`search_and_ingest` ingestion). Two stages, deliberately separated:

  - `classify_known_item` is PURE (no I/O): it detects the identifier type
    and builds the exact `query_string` (esearch term or efetch-by-id call, or
    NCT id) — it is this `query_string` that the freeze model (Tier 2) captures.
  - `resolve_pubmed_known_item` runs the search on the PubMed side for the
    PMID / DOI / title types. PMID goes through efetch-by-id (bypassing esearch); DOI and
    title go through a field-qualified esearch then efetch.

Hard rule: a known-item miss honestly returns an empty list. NO
fallback to a topical search for an exact lookup (cf. message below).
NCT resolution lives on the CT.gov side (ctgov), not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from augura_api.modules.corpus.pubmed import PubMedArticle, PubMedClient

# Message shown when an exact lookup finds nothing — without topical fallback.
KNOWN_ITEM_MISS_MESSAGE = (
    "No exact match found. The record may be too recently indexed, "
    "or check the PMID / DOI / NCT id."
)

# Retrieval sources.
SOURCE_PUBMED = "pubmed"
SOURCE_CTGOV = "ctgov"


class KnownItemKind(StrEnum):
    PMID = "pmid"
    DOI = "doi"
    TITLE = "title"
    NCT = "nct"


@dataclass(frozen=True)
class KnownItem:
    """Exact retrieval plan for an identified input."""

    kind: KnownItemKind
    source: str  # SOURCE_PUBMED | SOURCE_CTGOV
    value: str  # normalized identifier/title
    query_string: str  # exact term/call, captured for the freeze model


# all digits, 1 to 9 characters after trim
_PMID_RE = re.compile(r"^\d{1,9}$")
# 10.<registrant>/<suffix>
_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")
# NCTxxxxxxxx (8 digits)
_NCT_RE = re.compile(r"^NCT\d{8}$", re.IGNORECASE)
# Tolerated DOI URL prefix: we strip it before testing the DOI pattern.
_DOI_URL_PREFIX = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)


def classify_known_item(raw: str) -> KnownItem | None:
    """Detects a known-item identifier. Returns None for a topical input
    (free text) — the caller then falls back to the normal topical search."""
    s = raw.strip()
    if not s:
        return None

    # Quoted input → exact title.
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        title = s[1:-1].strip()
        if title:
            return KnownItem(KnownItemKind.TITLE, SOURCE_PUBMED, title, f'"{title}"[Title]')
        return None

    # NCT id → CT.gov (resolution on the ctgov side).
    if _NCT_RE.match(s):
        nct = s.upper()
        return KnownItem(KnownItemKind.NCT, SOURCE_CTGOV, nct, nct)

    # PMID → efetch by id (no esearch).
    if _PMID_RE.match(s):
        return KnownItem(KnownItemKind.PMID, SOURCE_PUBMED, s, f"efetch:id={s}")

    # DOI (possibly pasted as a URL) → esearch term=<doi>[DOI].
    doi = _DOI_URL_PREFIX.sub("", s)
    if _DOI_RE.match(doi):
        return KnownItem(KnownItemKind.DOI, SOURCE_PUBMED, doi, f"{doi}[DOI]")

    return None


async def resolve_pubmed_known_item(item: KnownItem, pubmed: PubMedClient) -> list[PubMedArticle]:
    """Runs an exact PubMed lookup (PMID/DOI/title). Returns [] on a miss —
    never falls back to the topical search."""
    if item.source != SOURCE_PUBMED:
        raise ValueError(f"resolve_pubmed_known_item: non-PubMed source {item.source!r}")

    if item.kind is KnownItemKind.PMID:
        # Bypass esearch: direct efetch by id.
        return await pubmed.fetch_by_ids([item.value])

    # DOI / title: field-qualified esearch (query_string) → efetch. max_results=1,
    # an exact lookup expects at most one match.
    return await pubmed.search(item.query_string, 1)
