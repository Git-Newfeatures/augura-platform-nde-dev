"""Match confidence (reduced: semantic + method + ambiguity)."""

from __future__ import annotations

from augura_api.modules.mapping.matcher import Candidate

_METHOD_Q = {"exact_synonym": 1.0, "fuzzy_label": 0.92, "fuzzy_synonym": 0.85}


def _label(score: float) -> str:
    if score >= 0.80:
        return "High"
    if score >= 0.60:
        return "Medium"
    if score >= 0.40:
        return "Low"
    if score > 0:
        return "Very Low"
    return "Unmapped"


def compute_confidence(candidates: list[Candidate]) -> dict[str, object]:
    if not candidates:
        return {"score": 0.0, "label": "Unmapped"}
    best = candidates[0]
    semantic = best.score
    mq = _METHOD_Q.get(best.method, 0.5)
    if len(candidates) < 2:
        amb = 1.0
    else:
        gap = best.score - candidates[1].score
        amb = 0.6 if gap < 0.05 else 0.75 if gap < 0.10 else 0.88 if gap < 0.20 else 1.0
    score = max(0.0, min(1.0, 0.50 * semantic + 0.30 * mq + 0.20 * amb))
    return {"score": round(score, 3), "label": _label(score)}
