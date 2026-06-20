# apps/api/tests/test_corpus_filters.py
"""Mappers de filtres (date + type d'étude) — purs, sans réseau."""

from datetime import date

from augura_api.modules.corpus.filters import (
    SearchFilters,
    build_pubmed_term,
    ctgov_filter_params,
    pubmed_date_params,
)

TODAY = date(2026, 6, 19)


def test_empty_filters_are_noop() -> None:
    f = SearchFilters()
    assert build_pubmed_term("hba1c", f) == "hba1c"
    assert pubmed_date_params(f, TODAY) == {}
    assert ctgov_filter_params(f, TODAY) == {}
    # None aussi (chemin sans filtres)
    assert build_pubmed_term("hba1c", None) == "hba1c"
    assert pubmed_date_params(None, TODAY) == {}
    assert ctgov_filter_params(None, TODAY) == {}


def test_pubmed_term_appends_publication_types() -> None:
    f = SearchFilters(study_types=("rct", "meta_analysis"))
    assert build_pubmed_term("hba1c", f) == (
        "(hba1c) AND (Randomized Controlled Trial[pt] OR Meta-Analysis[pt])"
    )


def test_pubmed_date_params_use_year_window() -> None:
    f = SearchFilters(date_range="5y")
    assert pubmed_date_params(f, TODAY) == {
        "datetype": "pdat",
        "mindate": "2021",
        "maxdate": "2026",
    }


def test_ctgov_single_study_type_maps_to_aggfilter() -> None:
    assert ctgov_filter_params(SearchFilters(study_types=("observational",)), TODAY) == {
        "aggFilters": "studyType:obs"
    }
    assert ctgov_filter_params(SearchFilters(study_types=("rct",)), TODAY) == {
        "aggFilters": "studyType:int"
    }


def test_ctgov_both_or_unmappable_types_skip_studytype() -> None:
    # rct + observational ⇒ les deux types ⇒ pas de filtre studyType
    assert "aggFilters" not in ctgov_filter_params(
        SearchFilters(study_types=("rct", "observational")), TODAY
    )
    # systematic_review/meta_analysis n'existent pas côté CT.gov
    assert ctgov_filter_params(SearchFilters(study_types=("systematic_review",)), TODAY) == {}


def test_ctgov_date_uses_advanced_range() -> None:
    assert ctgov_filter_params(SearchFilters(date_range="10y"), TODAY) == {
        "filter.advanced": "AREA[StudyFirstPostDate]RANGE[2016-01-01,MAX]"
    }
