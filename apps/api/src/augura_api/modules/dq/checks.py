"""Checks DQ data-only (A3a). Chaque check : trigger(ctx) + run(ctx)->findings."""

from __future__ import annotations

import hashlib
from typing import Any

from augura_api.modules.dq.config import THRESHOLDS
from augura_api.modules.dq.profiler import ColumnDQProfile
from augura_api.modules.dq.provenance import make_finding


# ── File scope ────────────────────────────────────────────────────────────
def file_fingerprint(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    digest = hashlib.sha256(ctx["raw_bytes"]).hexdigest()
    return [
        make_finding(
            check_id="DQ_FILE_002",
            category="file",
            scope="file",
            severity="info",
            message=f"File fingerprint: {digest[:16]}…",
            evidence={"sha256": digest},
        )
    ]


# ── Column scope ──────────────────────────────────────────────────────────
def missing_rate(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    rate = p.missing_rate
    severity = "hard" if rate > 0.50 else "soft" if rate > 0.05 else "info"
    return [
        make_finding(
            check_id="DQ_MISS_001",
            category="missing",
            scope="column",
            severity=severity,
            table=ctx["table"],
            column=p.col_name,
            message=f'"{p.col_name}": {rate * 100:.1f}% missing',
            evidence={
                "missing_count": p.missing_count,
                "total_count": p.total_count,
                "missing_rate": rate,
            },
            affected_count=p.missing_count,
            affected_proportion=rate,
        )
    ]


def mostly_missing(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    return [
        make_finding(
            check_id="DQ_MISS_003",
            category="missing",
            scope="column",
            severity="hard",
            table=ctx["table"],
            column=p.col_name,
            message=(
                f'"{p.col_name}" is {p.missing_rate * 100:.0f}% missing — handling policy required'
            ),
            evidence={
                "missing_rate": p.missing_rate,
                "policy_options": ["exclude", "flag", "keep"],
            },
            affected_count=p.missing_count,
            affected_proportion=p.missing_rate,
        )
    ]


def iqr_outliers(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    ns = p.num_summary
    assert (  # noqa: S101
        ns is not None
        and ns.q1 is not None
        and ns.q3 is not None
        and ns.iqr is not None
        and p.numeric_values is not None
    )
    k = THRESHOLDS["outlier_iqr_factor"]
    lower: float = ns.q1 - k * ns.iqr
    upper: float = ns.q3 + k * ns.iqr
    low = [v for v in p.numeric_values if v < lower]
    high = [v for v in p.numeric_values if v > upper]
    total = len(low) + len(high)
    if total == 0:
        return []
    return [
        make_finding(
            check_id="DQ_RANGE_002",
            category="range",
            scope="column",
            severity="soft",
            table=ctx["table"],
            column=p.col_name,
            message=f'"{p.col_name}": {total} outlier(s) beyond Q1/Q3 ± {k}×IQR',
            evidence={
                "lower_fence": round(lower, 3),
                "upper_fence": round(upper, 3),
                "low_count": len(low),
                "high_count": len(high),
                "low_sample": low[:5],
                "high_sample": high[:5],
            },
            affected_count=total,
            affected_proportion=total / len(p.numeric_values),
        )
    ]


def _trigger_mostly_missing(ctx: dict[str, Any]) -> bool:
    p: ColumnDQProfile = ctx["profile"]
    return p.missing_rate > THRESHOLDS["mostly_missing"]


def _trigger_iqr(ctx: dict[str, Any]) -> bool:
    p: ColumnDQProfile = ctx["profile"]
    return p.is_numeric and p.num_summary is not None and p.num_summary.iqr is not None


def _trigger_true(ctx: dict[str, Any]) -> bool:  # noqa: ARG001
    return True


# id, category, scope, severity, trigger, run
REGISTRY: list[dict[str, Any]] = [
    {
        "id": "DQ_FILE_002",
        "category": "file",
        "scope": "file",
        "severity": "info",
        "trigger": _trigger_true,
        "run": file_fingerprint,
    },
    {
        "id": "DQ_MISS_001",
        "category": "missing",
        "scope": "column",
        "severity": "info",
        "trigger": _trigger_true,
        "run": missing_rate,
    },
    {
        "id": "DQ_MISS_003",
        "category": "missing",
        "scope": "column",
        "severity": "hard",
        "trigger": _trigger_mostly_missing,
        "run": mostly_missing,
    },
    {
        "id": "DQ_RANGE_002",
        "category": "range",
        "scope": "column",
        "severity": "soft",
        "trigger": _trigger_iqr,
        "run": iqr_outliers,
    },
]
