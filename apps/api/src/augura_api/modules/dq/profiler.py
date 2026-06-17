"""Profiler DQ complet — porté de l'MVP profiler.js (transitoire, non persisté)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

_MISSING = {"", "na", "n/a"}
_SAMPLE = 200
_SENTINEL_NUMERIC = {-1, -99, -999, 999, 9999, 99999, -9999}
_SENTINEL_STRING = {
    "na",
    "n/a",
    "unknown",
    "unk",
    "missing",
    "none",
    "null",
    "not applicable",
    "not available",
    "nr",
    "nd",
    "refused",
}


@dataclass(frozen=True)
class NumSummary:
    n: int
    min: float
    max: float
    mean: float
    median: float
    q1: float | None
    q3: float | None
    iqr: float | None
    std_dev: float | None


@dataclass(frozen=True)
class ColumnDQProfile:
    col_name: str
    total_count: int
    is_numeric: bool
    is_categorical: bool
    is_date: bool
    missing_count: int
    missing_rate: float
    sentinel_count: int
    numeric_values: list[float] | None
    num_summary: NumSummary | None
    unique_values: list[str] | None
    unique_count: int
    sample_values: list[str]


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_date_like(s: str) -> bool:
    import re

    return bool(
        re.match(r"^\d{4}-\d{2}-\d{2}", s) or re.match(r"^\d{1,2}[/.]\d{1,2}[/.]\d{2,4}", s)
    )


def profile_column(col_name: str, values: Sequence[str | None]) -> ColumnDQProfile:
    vals = [("" if v is None else str(v)) for v in values]
    total = len(vals)
    sample = vals[:_SAMPLE]

    def frac(pred: Callable[[str], bool]) -> float:
        return sum(1 for v in sample if v.strip() and pred(v)) / len(sample) if sample else 0.0

    is_numeric = frac(_is_float) >= 0.8
    is_date = (not is_numeric) and frac(_is_date_like) >= 0.8
    non_missing = [v for v in vals if v.strip().lower() not in _MISSING]
    unique_count = len(set(non_missing))
    is_categorical = (not is_numeric) and (not is_date) and bool(non_missing) and unique_count <= 50

    missing_count = sum(1 for v in vals if v.strip().lower() in _MISSING)
    missing_rate = missing_count / total if total else 0.0

    def _is_sentinel(v: str) -> bool:
        s = v.strip().lower()
        if s in _SENTINEL_STRING:
            return True
        return _is_float(v) and float(v) in _SENTINEL_NUMERIC

    sentinel_count = sum(1 for v in vals if v.strip() and _is_sentinel(v))

    numeric_values: list[float] | None = None
    num_summary: NumSummary | None = None
    if is_numeric:
        nums = sorted(float(v) for v in non_missing if _is_float(v))
        numeric_values = nums
        if nums:
            n = len(nums)
            mean = sum(nums) / n
            q1 = nums[int(n * 0.25)]
            q3 = nums[int(n * 0.75)]
            var = sum((x - mean) ** 2 for x in nums) / (n - 1) if n > 1 else None
            num_summary = NumSummary(
                n=n,
                min=nums[0],
                max=nums[-1],
                mean=round(mean, 4),
                median=nums[n // 2],
                q1=q1,
                q3=q3,
                iqr=q3 - q1,
                std_dev=(var**0.5 if var is not None else None),
            )

    return ColumnDQProfile(
        col_name=col_name,
        total_count=total,
        is_numeric=is_numeric,
        is_categorical=is_categorical,
        is_date=is_date,
        missing_count=missing_count,
        missing_rate=missing_rate,
        sentinel_count=sentinel_count,
        numeric_values=numeric_values,
        num_summary=num_summary,
        unique_values=(sorted(set(non_missing)) if is_categorical else None),
        unique_count=unique_count,
        sample_values=non_missing[:5],
    )
