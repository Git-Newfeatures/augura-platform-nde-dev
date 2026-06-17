"""Tests du scorer DQ (déductions + score pondéré)."""

from augura_api.modules.dq.provenance import make_finding
from augura_api.modules.dq.scorer import compute_dq_score


def test_perfect_score_no_findings() -> None:
    s = compute_dq_score([], "exploratory")
    assert s["overall"] == 1.0
    assert s["dimensions"]["completeness"]["score"] == 1.0


def test_hard_missing_finding_deducts_completeness() -> None:
    f = make_finding(
        check_id="DQ_MISS_003", category="missing", scope="column", severity="hard", message="x"
    )
    s = compute_dq_score([f], "exploratory")
    # completeness loses 0.10 → 0.90; overall = 0.90*0.25 + 1.0*(0.75)
    assert s["dimensions"]["completeness"]["score"] == 0.9
    assert abs(s["overall"] - (0.9 * 0.25 + 1.0 * 0.75)) < 1e-6
