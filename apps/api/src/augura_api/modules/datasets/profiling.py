"""Column profiling — ported/condensed from the MVP profiler.js.

Produces exactly the fields persisted in dataset_columns. The full DQ profiler
(quartiles, sentinels, outliers) is ported in A3.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

_MISSING = {"", "na", "n/a"}
_SAMPLE = 200
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S")


@dataclass(frozen=True)
class ColumnProfile:
    value_kind: str
    n_total: int
    n_non_null: int
    null_pct: float
    n_distinct: int
    value_min: float | None
    value_max: float | None
    top_values: list[dict[str, str | int]]


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_date(s: str) -> bool:
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def profile_column(name: str, values: list[str]) -> ColumnProfile:
    n_total = len(values)
    non_null = [v for v in values if v.strip().lower() not in _MISSING]
    n_non_null = len(non_null)
    null_pct = 0.0 if n_total == 0 else round(1 - n_non_null / n_total, 6)
    n_distinct = len(set(non_null))

    sample = non_null[:_SAMPLE]

    def frac(pred: Callable[[str], bool]) -> float:
        return sum(1 for v in sample if pred(v)) / len(sample) if sample else 0.0

    # value_kind vocabulary is constrained by the dataset_columns CHECK:
    # ('numeric', 'text', 'binary', 'timestamp'). 'binary' = exactly two distinct
    # non-null values; richer categorical typing (for DQ) is derived in A3.
    if frac(_is_float) >= 0.8:
        value_kind = "numeric"
    elif frac(_is_date) >= 0.8:
        value_kind = "timestamp"
    elif n_distinct == 2:
        value_kind = "binary"
    else:
        value_kind = "text"

    value_min: float | None = None
    value_max: float | None = None
    if value_kind == "numeric":
        nums = [float(v) for v in non_null if _is_float(v)]
        if nums:
            value_min, value_max = min(nums), max(nums)

    top_values = [{"value": val, "count": cnt} for val, cnt in Counter(non_null).most_common(10)]
    return ColumnProfile(
        value_kind=value_kind,
        n_total=n_total,
        n_non_null=n_non_null,
        null_pct=null_pct,
        n_distinct=n_distinct,
        value_min=value_min,
        value_max=value_max,
        top_values=top_values,
    )
