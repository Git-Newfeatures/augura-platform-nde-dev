"""Monte-Carlo bootstrap (VALIDATED mode) — real scientific computation.

Where `power.py` gives a closed-form analytical power (LIVE mode, synchronous), this
module runs a real resampling simulation: for each scenario × estimator it draws
`n_boot` replicates of a calibrated synthetic cohort (constants shared with
`calibration.py`), computes the estimated effect + its standard error (Welch), and
derives the mean effect, percentile CI (2.5/97.5), empirical power (fraction of
replicates rejecting H0) and a representative p-value.

PURE and DETERMINISTIC function (fixed seed) → testable without a database, network or key.
The worker (jobs/) calls it then persists the result (simulation_runs.results +
read-model simulation_results). This is the computation that will run in a numpy/scipy
Modal job.
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np

from augura_api.modules.simulation import calibration

# Default scenarios: factors applied to the baseline (effect, dropout, σ).
DEFAULT_SCENARIOS: list[dict[str, Any]] = [
    {"name": "baseline", "effect_mult": 1.0, "dropout_add": 0.0, "sigma_mult": 1.0},
    {"name": "conservative", "effect_mult": 0.7, "dropout_add": 0.10, "sigma_mult": 1.0},
    {"name": "high_risk", "effect_mult": 0.5, "dropout_add": 0.15, "sigma_mult": 1.2},
]

_Z_95 = 1.959963984540054  # two-sided 95% normal quantile
DEFAULT_N_BOOT = 2000
DEFAULT_SEED = 42
# Default design effect (MDES) — aligned with power.PowerRequest.effect so that
# VALIDATED mode (bootstrap) and LIVE mode (analytical power) coincide at the baseline.
DEFAULT_EFFECT = 0.30


def _phi(z: float) -> float:
    """Normal CDF (Abramowitz-Stegun) — aligned with power.normal_cdf on the LIVE side."""
    import math

    t = 1 / (1 + 0.2316419 * abs(z))
    d = 0.3989423 * math.exp(-z * z / 2)
    p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
    return 1 - p if z > 0 else p


def compute_bootstrap(params: dict[str, Any]) -> dict[str, Any]:
    """Run the bootstrap for all scenarios × estimators and return a serializable
    dict (JSONB-friendly). `params` comes from the /simulations request."""
    n = int(params.get("n") or calibration.COHORT_N)
    base_dropout = float(params.get("dropout", 0.20))
    base_effect = float(params.get("effect", DEFAULT_EFFECT))
    sigma = calibration.sigma_for(sigma=params.get("sigma"), outcome=params.get("outcome"))
    estimators: list[str] = list(params.get("estimators") or calibration.ESTIMATORS)
    scenarios: list[dict[str, Any]] = list(params.get("scenarios") or DEFAULT_SCENARIOS)
    n_boot = int(params.get("n_boot") or DEFAULT_N_BOOT)
    seed = int(params.get("seed") or DEFAULT_SEED)
    cohort_name = str(params.get("cohort_name") or "cohort")

    rows: list[dict[str, Any]] = []
    for s_idx, scenario in enumerate(scenarios):
        name = str(scenario.get("name", f"scenario_{s_idx}"))
        effect = base_effect * float(scenario.get("effect_mult", 1.0))
        dropout = min(0.95, base_dropout + float(scenario.get("dropout_add", 0.0)))
        s_sigma = sigma * float(scenario.get("sigma_mult", 1.0))

        n_eff = n * (1 - dropout)
        n_treat = max(2, int(round(n_eff * calibration.TREAT_PROP)))
        n_ctrl = max(2, int(round(n_eff - n_treat)))

        for e_idx, est in enumerate(estimators):
            rng = np.random.default_rng(seed + s_idx * 100 + e_idx)
            efficiency = calibration.EST_EFFICIENCY.get(est, 1.0)
            bias_mag = calibration.BASE_BIAS.get(est, 0.015) * (1 + dropout * 1.6)
            var_mult = 1.3 if est == "ipw" else 0.9 if est == "lme" else 1.0

            # Vectorized replicates: the effect reduces the outcome → treated centered on -effect.
            treat = rng.normal(-effect, s_sigma, size=(n_boot, n_treat))
            ctrl = rng.normal(0.0, s_sigma, size=(n_boot, n_ctrl))
            diff = treat.mean(axis=1) - ctrl.mean(axis=1)
            se = np.sqrt(treat.var(axis=1, ddof=1) / n_treat + ctrl.var(axis=1, ddof=1) / n_ctrl)
            # Estimator efficiency: more efficient ⇒ lower SE ⇒ more power.
            se_est = se * np.sqrt(var_mult) / np.sqrt(efficiency)
            diff_est = diff - bias_mag  # bias (oriented in the direction of the effect)

            reject = np.abs(diff_est) / se_est > _Z_95
            effect_size = cast(float, np.mean(diff_est))
            ci_lower = cast(float, np.percentile(diff_est, 2.5))
            ci_upper = cast(float, np.percentile(diff_est, 97.5))
            power = cast(float, np.mean(reject)) * 100.0
            se_mean = cast(float, np.mean(se_est)) or 1e-9
            z_mean = abs(effect_size) / se_mean
            p_value = max(0.0, min(1.0, 2.0 * (1.0 - _phi(z_mean))))
            variance = cast(float, np.var(diff_est, ddof=1))

            rows.append(
                {
                    "scenario": name,
                    "estimator": est,
                    "effect_size": round(effect_size, 4),
                    "ci_lower": round(ci_lower, 4),
                    "ci_upper": round(ci_upper, 4),
                    "power": round(power, 1),
                    "p_value": round(p_value, 4),
                    "bias": round(bias_mag, 4),
                    "variance": round(variance, 4),
                    "mse": round(bias_mag * bias_mag + variance, 4),
                    # Scenario-level cohort parameters (read by SimulationEngine for the
                    # parameter panel + bootstrap-N display).
                    "n_total": int(round(n_eff)),
                    "n_treatment": n_treat,
                    "dropout": round(dropout, 4),
                }
            )

    # Recommendation: best estimator of the baseline scenario (max power, MSE tie-break).
    baseline_rows = [r for r in rows if r["scenario"] == (scenarios[0].get("name", "baseline"))]
    best = max(baseline_rows, key=lambda r: (r["power"], -r["mse"])) if baseline_rows else None
    summary = {
        "cohort_name": cohort_name,
        "n": n,
        "n_boot": n_boot,
        "power_threshold": calibration.POWER_THRESHOLD,
        "recommended_estimator": best["estimator"] if best else None,
        "recommended_power": best["power"] if best else None,
        "submission_ready": bool(best and best["power"] >= calibration.POWER_THRESHOLD),
    }
    return {
        "cohort_name": cohort_name,
        "n_boot": n_boot,
        "seed": seed,
        "scenarios": [str(s.get("name")) for s in scenarios],
        "estimators": estimators,
        "rows": rows,
        "summary": summary,
    }
