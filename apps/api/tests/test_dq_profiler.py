"""Tests du profiler DQ complet (quartiles, sentinelles, vecteurs)."""

from augura_api.modules.dq.profiler import profile_column


def test_numeric_summary_quartiles() -> None:
    p = profile_column("x", [str(i) for i in range(1, 101)])  # 1..100
    assert p.is_numeric
    assert p.num_summary is not None
    assert p.num_summary.min == 1.0
    assert p.num_summary.max == 100.0
    assert p.num_summary.iqr is not None and p.num_summary.iqr > 0


def test_missing_and_sentinel() -> None:
    p = profile_column("v", ["1", "2", "", "-999", "5"])
    assert p.missing_count == 1
    assert abs(p.missing_rate - 0.2) < 1e-9
    assert p.sentinel_count == 1  # -999 is a numeric sentinel
