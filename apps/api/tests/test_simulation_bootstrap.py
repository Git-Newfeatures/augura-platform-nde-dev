"""Tests for the Monte-Carlo bootstrap (VALIDATED mode) — pure numpy compute, no database.

Checks: determinism (seed), result shape (scenarios × estimators), calibration
consistency (baseline LME close to the submission threshold), efficiency order
(LME ≥ IPW), and recommendation.
"""

from augura_api.modules.simulation import calibration
from augura_api.modules.simulation.bootstrap import compute_bootstrap


def test_bootstrap_is_deterministic() -> None:
    a = compute_bootstrap({"cohort_name": "c", "n_boot": 400})
    b = compute_bootstrap({"cohort_name": "c", "n_boot": 400})
    assert a == b  # same seed → same result (reproducibility, spec §2)


def test_bootstrap_shape_scenarios_x_estimators() -> None:
    res = compute_bootstrap({"n_boot": 300})
    n_scen = len(res["scenarios"])
    n_est = len(res["estimators"])
    assert n_scen == 3
    assert n_est == len(calibration.ESTIMATORS)
    assert len(res["rows"]) == n_scen * n_est
    row = res["rows"][0]
    for key in (
        "scenario",
        "estimator",
        "effect_size",
        "ci_lower",
        "ci_upper",
        "power",
        "p_value",
        "bias",
        "variance",
        "mse",
        "n_total",
        "n_treatment",
        "dropout",
    ):
        assert key in row
    assert row["n_total"] > row["n_treatment"] > 0  # n_treat is a subset of n_eff


def test_bootstrap_ci_brackets_effect() -> None:
    res = compute_bootstrap({"n_boot": 800})
    for r in res["rows"]:
        assert r["ci_lower"] <= r["effect_size"] <= r["ci_upper"]
        assert 0.0 <= r["power"] <= 100.0
        assert 0.0 <= r["p_value"] <= 1.0


def test_bootstrap_baseline_lme_has_high_power() -> None:
    res = compute_bootstrap({"n": 824, "n_boot": 1500})
    baseline = [r for r in res["rows"] if r["scenario"] == "baseline"]
    lme = next(r for r in baseline if r["estimator"] == "lme")
    ipw = next(r for r in baseline if r["estimator"] == "ipw")
    assert lme["power"] >= 70.0  # well-powered calibrated cohort
    assert lme["power"] >= ipw["power"]  # LME more efficient than IPW


def test_bootstrap_summary_recommends_estimator() -> None:
    res = compute_bootstrap({"n_boot": 500})
    summary = res["summary"]
    assert summary["recommended_estimator"] in res["estimators"]
    assert isinstance(summary["submission_ready"], bool)
