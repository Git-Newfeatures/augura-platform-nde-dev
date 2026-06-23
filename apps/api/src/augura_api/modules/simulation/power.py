"""Analytical power (LIVE mode) — faithful port of SimulationEngine.computeAnalytical.

Synchronous, without scientific dependencies (the API image stays lightweight; the
numpy/scipy/statsmodels bootstrap runs in a separate Modal job). Calibrated per outcome
(fix T4) via calibration.sigma_for.
"""

import math
from dataclasses import dataclass

from augura_api.modules.simulation import calibration


def normal_cdf(z: float) -> float:
    """Abramowitz-Stegun approximation (identical to the frontend for aligned values)."""
    t = 1 / (1 + 0.2316419 * abs(z))
    d = 0.3989423 * math.exp(-z * z / 2)
    p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
    return 1 - p if z > 0 else p


@dataclass(frozen=True)
class EstimatorPower:
    estimator: str
    power: float
    bias: float
    variance: float
    mse: float
    effect: float
    ci_lower: float
    ci_upper: float


def compute_power(
    *,
    n: int,
    dropout: float,
    effect: float,
    sigma: float,
    estimators: list[str] | None = None,
) -> list[EstimatorPower]:
    """Power/bias/variance per estimator. Raises if the groups are too small."""
    n_eff = n * (1 - dropout)
    n_treat = n_eff * calibration.TREAT_PROP
    n_ctrl = n_eff * (1 - calibration.TREAT_PROP)
    if n_treat < 5 or n_ctrl < 5:
        raise ValueError("groups too small (n_treat or n_ctrl < 5)")

    se = sigma / math.sqrt(n_eff * calibration.TREAT_PROP * (1 - calibration.TREAT_PROP))
    z_eff = abs(effect) / se
    raw_power = normal_cdf(z_eff - 1.96) * 100
    half_ci = 1.96 * se
    point = -abs(effect)

    keys = estimators or calibration.ESTIMATORS
    out: list[EstimatorPower] = []
    for key in keys:
        efficiency = calibration.EST_EFFICIENCY.get(key, 1.0)
        bias = calibration.BASE_BIAS.get(key, 0.015) * (1 + dropout * 1.6)
        var_mult = 1.3 if key == "ipw" else 0.9 if key == "lme" else 1.0
        variance = se * se * var_mult
        out.append(
            EstimatorPower(
                estimator=key,
                power=round(min(99.9, max(0.1, raw_power * efficiency)) * 10) / 10,
                bias=round(bias, 4),
                variance=round(variance, 4),
                mse=round(bias * bias + variance, 4),
                effect=round(point, 3),
                ci_lower=round(point - half_ci, 3),
                ci_upper=round(point + half_ci, 3),
            )
        )
    return out
