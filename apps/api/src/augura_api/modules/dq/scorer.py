"""Scoring DQ — par dimension + global pondéré (MVP dq-scorer.js)."""

from __future__ import annotations

from typing import Any

from augura_api.modules.dq.config import (
    DIMENSION_CATEGORIES,
    SEVERITY_DEDUCTIONS,
    WEIGHT_PROFILES,
)


def compute_dq_score(findings: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    weights = WEIGHT_PROFILES[profile]
    dimensions: dict[str, Any] = {}
    for dim, weight in weights.items():
        cats = DIMENSION_CATEGORIES[dim]
        dim_findings = [f for f in findings if f["category"] in cats]
        score = 1.0
        counts = {"hard": 0, "soft": 0, "info": 0}
        for f in dim_findings:
            sev = f["severity"]
            score = max(0.0, score - SEVERITY_DEDUCTIONS.get(sev, 0.0))
            counts[sev] = counts.get(sev, 0) + 1
        dimensions[dim] = {
            "score": round(score, 3),
            "weight": weight,
            "finding_counts": counts,
        }
    overall = sum(d["score"] * d["weight"] for d in dimensions.values())
    return {"overall": round(overall, 3), "dimensions": dimensions}
