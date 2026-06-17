"""Dispatch des checks DQ + audit d'exécution."""

from __future__ import annotations

from typing import Any


def evaluate_check(
    check: dict[str, Any], ctx: dict[str, Any], audit: dict[str, Any]
) -> list[dict[str, Any]]:
    item = audit.setdefault(
        check["id"], {"check_id": check["id"], "scope": check["scope"],
                      "evaluations": 0, "triggered": 0, "findings": 0, "errors": []}
    )
    item["evaluations"] += 1
    try:
        triggered = bool(check["trigger"](ctx))
    except Exception as exc:  # noqa: BLE001
        item["errors"].append(f"trigger: {exc}")
        return []
    if not triggered:
        return []
    item["triggered"] += 1
    try:
        findings = check["run"](ctx)
    except Exception as exc:  # noqa: BLE001
        item["errors"].append(f"run: {exc}")
        return []
    for f in findings:
        f.setdefault("severity", check["severity"])
    item["findings"] += len(findings)
    return findings
