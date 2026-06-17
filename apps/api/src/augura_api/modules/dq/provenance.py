"""Fabrique de findings DQ (forme exacte, traçabilité)."""

from __future__ import annotations

from typing import Any

from augura_api.modules.dq.config import POLICY_VERSION


def make_finding(
    *,
    check_id: str,
    category: str,
    scope: str,
    severity: str,
    message: str,
    table: str | None = None,
    column: str | None = None,
    columns: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    affected_count: int | None = None,
    affected_proportion: float | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "scope": scope,
        "table": table,
        "column": column,
        "columns": columns,
        "severity": severity,
        "message": message,
        "evidence": evidence or {},
        "affected_count": affected_count,
        "affected_proportion": affected_proportion,
        "handling_status": "open",
        "policy_version": POLICY_VERSION,
    }
