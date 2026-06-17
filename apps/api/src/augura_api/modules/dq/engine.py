"""Moteur DQ : profile → checks (file/column) → bundle scoré (A3a, sync, sans concept)."""

from __future__ import annotations

import hashlib
from typing import Any

from augura_api.modules.dq.checks import REGISTRY
from augura_api.modules.dq.config import POLICY_VERSION
from augura_api.modules.dq.profiler import profile_column
from augura_api.modules.dq.registry import evaluate_check
from augura_api.modules.dq.scorer import compute_dq_score


def run_dq(
    sheets: list[dict[str, Any]], *, raw_bytes: bytes, weight_profile: str = "exploratory"
) -> dict[str, Any]:
    audit: dict[str, Any] = {}
    fingerprint = hashlib.sha256(raw_bytes).hexdigest()
    all_findings: list[dict[str, Any]] = []

    # File scope
    file_ctx = {"raw_bytes": raw_bytes}
    for check in (c for c in REGISTRY if c["scope"] == "file"):
        all_findings.extend(evaluate_check(check, file_ctx, audit))

    # Column scope (per sheet, per column)
    tables: list[dict[str, Any]] = []
    for sheet in sheets:
        headers: list[str] = sheet["headers"]
        rows: list[list[str]] = sheet["rows"]
        table_cols: list[dict[str, Any]] = []
        for idx, header in enumerate(headers):
            values: list[str | None] = [r[idx] if idx < len(r) else "" for r in rows]
            profile = profile_column(header, values)
            ctx = {"table": sheet["name"], "column": header, "profile": profile}
            col_findings: list[dict[str, Any]] = []
            for check in (c for c in REGISTRY if c["scope"] == "column"):
                col_findings.extend(evaluate_check(check, ctx, audit))
            all_findings.extend(col_findings)
            outliers = next(
                (f["affected_count"] for f in col_findings if f["check_id"] == "DQ_RANGE_002"), 0
            )
            table_cols.append(
                {
                    "column": header,
                    "type": (
                        "numeric"
                        if profile.is_numeric
                        else "date"
                        if profile.is_date
                        else "categorical"
                        if profile.is_categorical
                        else "text"
                    ),
                    "missing_rate": profile.missing_rate,
                    "outlier_count": outliers or 0,
                    "findings": col_findings,
                }
            )
        tables.append(
            {
                "table_label": sheet["name"],
                "grain": None,
                "columns": table_cols,
                "cross_column_findings": [],
                "table_findings": [],
            }
        )

    score = compute_dq_score(all_findings, weight_profile)
    hard_total = sum(1 for f in all_findings if f["severity"] == "hard")
    return {
        "meta": {
            "policy_version": POLICY_VERSION,
            "dataset_fingerprint": fingerprint,
            "score_profile": weight_profile,
            "status": "draft",
        },
        "summary": {
            "overall_score": score["overall"],
            "dimensions": score["dimensions"],
            "hard_findings_total": hard_total,
            "requires_resolution": hard_total > 0,
        },
        "check_plan": {
            "by_scope": {"file": 1, "column": 3},
            "execution": {"total_registered": len(REGISTRY), "checks": list(audit.values())},
        },
        "tables": tables,
        "cross_table_findings": [],
        "provenance": all_findings,
    }
