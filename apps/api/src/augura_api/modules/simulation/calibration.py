"""Clinical calibration constants (port of lucis-dashboard/src/config.js).

⚠️ Do not modify without sign-off — shared between the analytical power (LIVE) and
the bootstrap (run_bootstrap.py). Source: Lucis synthetic cohort (N=824)."""

COHORT_N = 824
TREAT_PROP = 0.231  # HIGH engagers = top quartile (binary HIGH vs REST split, D1)
TRUE_EFFECT = -0.206  # observed ATT: HbA1c reduction HIGH vs REST

POWER_THRESHOLD = 80.0  # minimum power for regulatory submission
POWER_MARGINAL_FLOOR = 70.0  # below → redesign, no submission

# σ calibrated so the analytical formula matches the bootstrap at the baseline.
SIGMA_NOISE = {"low": 0.82, "medium": 1.05, "high": 1.38}

# Fix T4 — PER-OUTCOME σ calibration (default = medium; real values to be refined
# on partner cohorts, data not available here).
OUTCOME_SIGMA = {
    "hba1c": 1.05,
    "hba1c_12m": 1.05,
    "ldl": 1.18,
    "ldl_12m": 1.18,
    "crp": 1.34,
    "crp_12m": 1.34,
}

BASE_BIAS = {
    "lme": 0.010,
    "ols": 0.018,
    "ipw": 0.021,
    "mediation": 0.012,
    "tmle": 0.009,
    "did": 0.015,
}

EST_EFFICIENCY = {
    "lme": 1.00,
    "ols": 0.95,
    "ipw": 0.88,
    "mediation": 0.98,
    "tmle": 0.96,
    "did": 0.90,
}

ESTIMATORS = ["lme", "ols", "ipw", "mediation", "tmle", "did"]


def sigma_for(*, sigma: float | None, outcome: str | None) -> float:
    """Resolve σ: explicit > per-outcome calibration (T4) > medium by default."""
    if sigma is not None:
        return sigma
    if outcome and outcome in OUTCOME_SIGMA:
        return OUTCOME_SIGMA[outcome]
    return SIGMA_NOISE["medium"]
