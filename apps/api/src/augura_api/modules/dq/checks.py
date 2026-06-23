"""Data-only DQ checks (A3a+A3b). Each check: trigger(ctx) + run(ctx)->findings."""

from __future__ import annotations

import hashlib
import re
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


_MISSING = {"", "na", "n/a"}
_SENTINEL_NUMERIC = {-1, -99, -999, 999, 9999, 99999, -9999}
_DATE_PATTERNS = [
    ("ISO", re.compile(r"^\d{4}-\d{2}-\d{2}")),
    ("US", re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}")),
    ("European", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}")),
    ("Compact", re.compile(r"^\d{8}$")),
]


def _is_missing(v: str | None) -> bool:
    return (v or "").strip().lower() in _MISSING


# ── File scope (A3b) ──────────────────────────────────────────────────────────
def non_ascii_encoding(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    raw: bytes = ctx["raw_bytes"][:10240]
    positions = [i for i, b in enumerate(raw) if b > 127]
    if not positions:
        return []
    return [
        make_finding(
            check_id="DQ_FILE_003",
            category="file",
            scope="file",
            severity="soft",
            message="Non-ASCII characters detected — possible encoding issue",
            evidence={"count": len(positions), "first_positions": positions[:5]},
        )
    ]


# ── Column scope (A3b) ────────────────────────────────────────────────────────
def mixed_date_formats(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[str | None] = ctx["values"]
    non_missing = [v for v in values if not _is_missing(v)]
    detected: set[str] = set()
    for v in non_missing[:200]:
        for name, pat in _DATE_PATTERNS:
            if pat.match((v or "").strip()):
                detected.add(name)
                break
    if len(detected) <= 1:
        return []
    return [
        make_finding(
            check_id="DQ_TYPE_002",
            category="type",
            scope="column",
            severity="soft",
            table=ctx["table"],
            column=ctx["column"],
            message=f"Mixed date formats: {', '.join(sorted(detected))}",
            evidence={"patterns": sorted(detected)},
        )
    ]


def sentinel_values(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    p: ColumnDQProfile = ctx["profile"]
    if p.sentinel_count == 0:
        return []
    return [
        make_finding(
            check_id="DQ_MISS_002",
            category="missing",
            scope="column",
            severity="soft",
            table=ctx["table"],
            column=p.col_name,
            message=f'"{p.col_name}": {p.sentinel_count} sentinel value(s) detected',
            evidence={"sentinel_count": p.sentinel_count},
            affected_count=p.sentinel_count,
        )
    ]


# ── Table scope (A3b) ─────────────────────────────────────────────────────────
def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _is_float_str(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _has_numeric_content(col: dict[str, Any]) -> bool:
    """True if the column is numeric or has >50% non-missing float values."""
    if col["profile"].is_numeric:
        return True
    non_missing = [v for v in col["values"] if not _is_missing(v)]
    if not non_missing:
        return False
    floats = sum(1 for v in non_missing if _is_float_str(str(v or "")))
    return floats / len(non_missing) > 0.50


def co_missingness(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [c for c in ctx["columns"] if _has_numeric_content(c)]
    findings: list[dict[str, Any]] = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, b = candidates[i], candidates[j]
            av = [1.0 if _is_missing(v) else 0.0 for v in a["values"]]
            bv = [1.0 if _is_missing(v) else 0.0 for v in b["values"]]
            corr = _pearson(av, bv)
            if corr is not None and corr > 0.80:
                findings.append(
                    make_finding(
                        check_id="DQ_MISS_004",
                        category="missing",
                        scope="table",
                        severity="soft",
                        table=ctx["table"],
                        columns=[a["column"], b["column"]],
                        message=(
                            f'"{a["column"]}" and "{b["column"]}" are co-missing (r={corr:.2f})'
                        ),
                        evidence={
                            "columns": [a["column"], b["column"]],
                            "correlation": round(corr, 3),
                        },
                    )
                )
    return findings


def site_concentrated_missingness(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    site = next(
        (c for c in ctx["columns"] if re.search(r"site|center|arm|group", c["column"], re.I)),
        None,
    )
    if site is None:
        return []
    findings: list[dict[str, Any]] = []
    groups = sorted({(v or "").strip() for v in site["values"] if not _is_missing(v)})
    if len(groups) < 2:
        return []
    for col in ctx["columns"]:
        if col is site or not col["profile"].is_numeric:
            continue
        rates: dict[str, float] = {}
        for g in groups:
            idxs = [k for k, v in enumerate(site["values"]) if (v or "").strip() == g]
            if not idxs:
                continue
            miss = sum(1 for k in idxs if _is_missing(col["values"][k]))
            rates[g] = miss / len(idxs)
        if rates and (max(rates.values()) - min(rates.values())) > 0.20:
            findings.append(
                make_finding(
                    check_id="DQ_MISS_005",
                    category="missing",
                    scope="table",
                    severity="soft",
                    table=ctx["table"],
                    column=col["column"],
                    message=f'"{col["column"]}" missing rate varies by {site["column"]}',
                    evidence={"site_column": site["column"], "by_site": rates},
                )
            )
    return findings


def _trigger_co_missing(ctx: dict[str, Any]) -> bool:
    return sum(1 for c in ctx["columns"] if _has_numeric_content(c)) >= 2


def _trigger_has_site(ctx: dict[str, Any]) -> bool:
    return any(re.search(r"site|center|arm|group", c["column"], re.I) for c in ctx["columns"])


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
    {
        "id": "DQ_FILE_003",
        "category": "file",
        "scope": "file",
        "severity": "soft",
        "trigger": _trigger_true,
        "run": non_ascii_encoding,
    },
    {
        "id": "DQ_TYPE_002",
        "category": "type",
        "scope": "column",
        "severity": "soft",
        "trigger": _trigger_true,
        "run": mixed_date_formats,
    },
    {
        "id": "DQ_MISS_002",
        "category": "missing",
        "scope": "column",
        "severity": "soft",
        "trigger": _trigger_true,
        "run": sentinel_values,
    },
    {
        "id": "DQ_MISS_004",
        "category": "missing",
        "scope": "table",
        "severity": "soft",
        "trigger": _trigger_co_missing,
        "run": co_missingness,
    },
    {
        "id": "DQ_MISS_005",
        "category": "missing",
        "scope": "table",
        "severity": "soft",
        "trigger": _trigger_has_site,
        "run": site_concentrated_missingness,
    },
]
