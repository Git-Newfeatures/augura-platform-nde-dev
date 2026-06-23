# apps/api/tests/test_corpus_retrieve_request.py
"""Validation of the retrieve request + construction of SearchFilters on the router side."""

import pytest

from augura_api.core.errors import BadRequestError
from augura_api.modules.corpus.filters import SearchFilters
from augura_api.modules.corpus.router import build_filters as _build_filters


def test_build_filters_defaults_to_any() -> None:
    assert _build_filters("any", []) == SearchFilters(date_range="any", study_types=())


def test_build_filters_normalizes_lists_to_tuples() -> None:
    f = _build_filters("5y", ["rct", "observational"])
    assert f == SearchFilters(date_range="5y", study_types=("rct", "observational"))


def test_build_filters_rejects_bad_date_range() -> None:
    with pytest.raises(BadRequestError):
        _build_filters("yesterday", [])


def test_build_filters_rejects_bad_study_type() -> None:
    with pytest.raises(BadRequestError):
        _build_filters("any", ["cohort"])
