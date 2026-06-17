"""Tests du profiler de colonnes (datasets)."""

from augura_api.modules.datasets.profiling import profile_column


def test_numeric_column() -> None:
    p = profile_column("hba1c", ["5.1", "6.2", "7.0", "", "5.5"])
    assert p.value_kind == "numeric"
    assert p.n_total == 5
    assert p.n_non_null == 4
    assert p.value_min == 5.1
    assert p.value_max == 7.0
    assert abs(p.null_pct - 0.2) < 1e-9


def test_categorical_top_values() -> None:
    p = profile_column("sex", ["M", "F", "F", "F", "M"])
    assert p.value_kind == "categorical"
    assert p.n_distinct == 2
    top = {d["value"]: d["count"] for d in p.top_values}
    assert top == {"F": 3, "M": 2}
    assert p.value_min is None


def test_date_column() -> None:
    p = profile_column("visit_dt", ["2024-01-01", "2024-02-15", "2024-03-30"])
    assert p.value_kind == "date"


def test_all_missing() -> None:
    p = profile_column("empty", ["", "NA", "n/a"])
    assert p.n_non_null == 0
    assert p.null_pct == 1.0
    assert p.value_kind == "text"
