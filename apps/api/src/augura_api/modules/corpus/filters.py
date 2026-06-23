# apps/api/src/augura_api/modules/corpus/filters.py
"""Live search filters (date + study type) — PURE mapping, source-specific.

No I/O ⇒ testable without network. The router builds `SearchFilters` from the
request; the retriever passes it to the PubMed/CT.gov clients, which apply these
mappers. An empty filter (date_range='any', study_types=()) is a no-op: the query
goes out unchanged — preserves existing behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

VALID_DATE_RANGES = ("any", "1y", "5y", "10y")
_YEARS_BACK = {"1y": 1, "5y": 5, "10y": 10}

# Augura study_type → PubMed Publication Type term ([pt]).
_PUBMED_PT = {
    "rct": "Randomized Controlled Trial[pt]",
    "observational": "Observational Study[pt]",
    "systematic_review": "Systematic Review[pt]",
    "meta_analysis": "Meta-Analysis[pt]",
}
VALID_STUDY_TYPES = tuple(_PUBMED_PT.keys())

# Augura study_type → CT.gov studyType (aggFilters). Reviews/meta-analyses are
# not CT.gov trial types → ignored on the CT.gov side.
_CTGOV_STUDY_TYPE = {"rct": "int", "observational": "obs"}


@dataclass(frozen=True)
class SearchFilters:
    date_range: str = "any"
    study_types: tuple[str, ...] = ()


def _from_year(date_range: str, today: date) -> int | None:
    back = _YEARS_BACK.get(date_range)
    return None if back is None else today.year - back


def build_pubmed_term(query: str, filters: SearchFilters | None) -> str:
    """esearch term: `(query) AND (pt OR pt)`. Without study_types → `query` unchanged."""
    if not filters or not filters.study_types:
        return query
    pts = [_PUBMED_PT[t] for t in filters.study_types if t in _PUBMED_PT]
    if not pts:
        return query
    return f"({query}) AND ({' OR '.join(pts)})"


def pubmed_date_params(filters: SearchFilters | None, today: date) -> dict[str, str]:
    """esearch date params (year granularity). Empty if date_range='any'."""
    if not filters:
        return {}
    year = _from_year(filters.date_range, today)
    if year is None:
        return {}
    return {"datetype": "pdat", "mindate": str(year), "maxdate": str(today.year)}


def ctgov_filter_params(filters: SearchFilters | None, today: date) -> dict[str, str]:
    """CT.gov v2 params: aggFilters studyType (only 1 mappable type) + date range.
    Two types int+obs selected, or only a non-mappable type → no studyType."""
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
