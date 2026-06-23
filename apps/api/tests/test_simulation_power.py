"""Local tests for the analytical power (LIVE mode) — pure compute, no database.

The calibration target: baseline (N=824, dropout 20%, effect 0.30, σ=1.05) ≈ 87%
power for LME (cf. config.js).
"""

import pytest

from augura_api.core.errors import BadRequestError
from augura_api.modules.simulation import calibration
from augura_api.modules.simulation.schemas import PowerRequest
from augura_api.modules.simulation.service import compute_power_response


def test_power_baseline_lme_near_calibration() -> None:
    resp = compute_power_response(PowerRequest(n=824, dropout=0.20, effect=0.30, sigma=1.05))
    lme = next(e for e in resp.estimators if e.estimator == "lme")
    assert 85.0 <= lme.power <= 89.0  # calibration target ≈ 87%
    assert resp.power_threshold == 80.0
    assert resp.sigma == 1.05


def test_power_ordering_lme_beats_ipw() -> None:
    resp = compute_power_response(PowerRequest())
    powers = {e.estimator: e.power for e in resp.estimators}
    assert powers["lme"] >= powers["ipw"]  # LME more efficient than IPW


def test_power_estimator_filter() -> None:
    resp = compute_power_response(PowerRequest(estimators=["lme", "ols"]))
    assert {e.estimator for e in resp.estimators} == {"lme", "ols"}


def test_power_small_groups_raises() -> None:
    with pytest.raises(BadRequestError):
        compute_power_response(PowerRequest(n=10))


def test_sigma_per_outcome_calibration() -> None:
    assert calibration.sigma_for(sigma=None, outcome="ldl") == 1.18
    assert calibration.sigma_for(sigma=0.5, outcome="ldl") == 0.5  # explicit wins
    assert calibration.sigma_for(sigma=None, outcome=None) == calibration.SIGMA_NOISE["medium"]
