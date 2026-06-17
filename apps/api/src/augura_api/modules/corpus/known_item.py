"""Routeur known-item : aiguille une saisie vers une recherche exacte.

Brique partagée du nouvel endpoint retrieve-and-freeze (distinct de l'ingestion
`search_and_ingest`). Deux temps, volontairement séparés :

  - `classify_known_item` est PUR (aucune I/O) : il détecte le type d'identifiant
    et construit le `query_string` exact (terme esearch ou appel efetch par id, ou
    id NCT) — c'est ce `query_string` que le modèle de gel (Tier 2) capture.
  - `resolve_pubmed_known_item` exécute la recherche côté PubMed pour les types
    PMID / DOI / titre. Le PMID passe par efetch-par-id (bypass esearch) ; DOI et
    titre passent par un esearch qualifié de champ puis efetch.

Règle dure : un miss known-item renvoie une liste vide, honnêtement. PAS de
repli sur une recherche topique pour un lookup exact (cf. message ci-dessous).
La résolution NCT vit côté CT.gov (ctgov), pas ici.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from augura_api.modules.corpus.pubmed import PubMedArticle, PubMedClient

# Message affiché quand un lookup exact ne trouve rien — sans repli topique.
KNOWN_ITEM_MISS_MESSAGE = (
    "No exact match found. The record may be too recently indexed, "
    "or check the PMID / DOI / NCT id."
)

# Sources de récupération.
SOURCE_PUBMED = "pubmed"
SOURCE_CTGOV = "ctgov"


class KnownItemKind(StrEnum):
    PMID = "pmid"
    DOI = "doi"
    TITLE = "title"
    NCT = "nct"


@dataclass(frozen=True)
class KnownItem:
    """Plan de récupération exact pour une saisie identifiée."""

    kind: KnownItemKind
    source: str  # SOURCE_PUBMED | SOURCE_CTGOV
    value: str  # identifiant/titre normalisé
    query_string: str  # terme/appel exact, capturé pour le modèle de gel


# all digits, 1 à 9 caractères après trim
_PMID_RE = re.compile(r"^\d{1,9}$")
# 10.<registrant>/<suffix>
_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")
# NCTxxxxxxxx (8 chiffres)
_NCT_RE = re.compile(r"^NCT\d{8}$", re.IGNORECASE)
# Préfixe URL DOI toléré : on le retire avant de tester le motif DOI.
_DOI_URL_PREFIX = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)


def classify_known_item(raw: str) -> KnownItem | None:
    """Détecte un identifiant known-item. Renvoie None pour une saisie topique
    (texte libre) — l'appelant retombe alors sur la recherche topique normale."""
    s = raw.strip()
    if not s:
        return None

    # Saisie entre guillemets → titre exact.
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        title = s[1:-1].strip()
        if title:
            return KnownItem(KnownItemKind.TITLE, SOURCE_PUBMED, title, f'"{title}"[Title]')
        return None

    # NCT id → CT.gov (résolution côté ctgov).
    if _NCT_RE.match(s):
        nct = s.upper()
        return KnownItem(KnownItemKind.NCT, SOURCE_CTGOV, nct, nct)

    # PMID → efetch par id (aucun esearch).
    if _PMID_RE.match(s):
        return KnownItem(KnownItemKind.PMID, SOURCE_PUBMED, s, f"efetch:id={s}")

    # DOI (éventuellement collé en URL) → esearch term=<doi>[DOI].
    doi = _DOI_URL_PREFIX.sub("", s)
    if _DOI_RE.match(doi):
        return KnownItem(KnownItemKind.DOI, SOURCE_PUBMED, doi, f"{doi}[DOI]")

    return None


async def resolve_pubmed_known_item(item: KnownItem, pubmed: PubMedClient) -> list[PubMedArticle]:
    """Exécute un lookup exact PubMed (PMID/DOI/titre). Renvoie [] sur miss —
    jamais de repli sur la recherche topique."""
    if item.source != SOURCE_PUBMED:
        raise ValueError(f"resolve_pubmed_known_item: source non-PubMed {item.source!r}")

    if item.kind is KnownItemKind.PMID:
        # Bypass esearch : efetch direct par id.
        return await pubmed.fetch_by_ids([item.value])

    # DOI / titre : esearch qualifié de champ (query_string) → efetch. max_results=1,
    # un lookup exact attend au plus une correspondance.
    return await pubmed.search(item.query_string, 1)
