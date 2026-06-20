# apps/api/src/augura_api/modules/corpus/filters.py
"""Filtres de recherche live (date + type d'étude) — mapping PUR, source-spécifique.

Aucune I/O ⇒ testable sans réseau. Le routeur construit `SearchFilters` depuis la
requête ; le retriever le passe aux clients PubMed/CT.gov, qui appliquent ces
mappers. Un filtre vide (date_range='any', study_types=()) est un no-op : la requête
part inchangée — préserve le comportement existant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

VALID_DATE_RANGES = ("any", "1y", "5y", "10y")
_YEARS_BACK = {"1y": 1, "5y": 5, "10y": 10}

# study_type Augura → terme PubMed Publication Type ([pt]).
_PUBMED_PT = {
    "rct": "Randomized Controlled Trial[pt]",
    "observational": "Observational Study[pt]",
    "systematic_review": "Systematic Review[pt]",
    "meta_analysis": "Meta-Analysis[pt]",
}
VALID_STUDY_TYPES = tuple(_PUBMED_PT.keys())

# study_type Augura → studyType CT.gov (aggFilters). Revues/méta-analyses ne sont
# pas des types d'essai CT.gov → ignorées côté CT.gov.
_CTGOV_STUDY_TYPE = {"rct": "int", "observational": "obs"}


@dataclass(frozen=True)
class SearchFilters:
    date_range: str = "any"
    study_types: tuple[str, ...] = ()


def _from_year(date_range: str, today: date) -> int | None:
    back = _YEARS_BACK.get(date_range)
    return None if back is None else today.year - back


def build_pubmed_term(query: str, filters: SearchFilters | None) -> str:
    """Terme esearch : `(query) AND (pt OR pt)`. Sans study_types → `query` inchangée."""
    if not filters or not filters.study_types:
        return query
    pts = [_PUBMED_PT[t] for t in filters.study_types if t in _PUBMED_PT]
    if not pts:
        return query
    return f"({query}) AND ({' OR '.join(pts)})"


def pubmed_date_params(filters: SearchFilters | None, today: date) -> dict[str, str]:
    """Params esearch de date (granularité année). Vide si date_range='any'."""
    if not filters:
        return {}
    year = _from_year(filters.date_range, today)
    if year is None:
        return {}
    return {"datetype": "pdat", "mindate": str(year), "maxdate": str(today.year)}


def ctgov_filter_params(filters: SearchFilters | None, today: date) -> dict[str, str]:
    """Params CT.gov v2 : aggFilters studyType (1 seul type mappable) + range de date.
    Deux types int+obs sélectionnés, ou type non mappable seul → pas de studyType."""
    if not filters:
        return {}
    params: dict[str, str] = {}
    cts = {_CTGOV_STUDY_TYPE[t] for t in filters.study_types if t in _CTGOV_STUDY_TYPE}
    if len(cts) == 1:
        params["aggFilters"] = f"studyType:{next(iter(cts))}"
    year = _from_year(filters.date_range, today)
    if year is not None:
        params["filter.advanced"] = f"AREA[StudyFirstPostDate]RANGE[{year}-01-01,MAX]"
    return params
