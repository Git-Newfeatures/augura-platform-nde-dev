"""Constantes cliniques de calibration (port de lucis-dashboard/src/config.js).

⚠️ Ne pas modifier sans sign-off — partagées entre le power analytique (LIVE) et
le bootstrap (run_bootstrap.py). Source : cohorte synthétique Lucis (N=824)."""

COHORT_N = 824
TREAT_PROP = 0.231  # HIGH engagers = quartile haut (split binaire HIGH vs REST, D1)
TRUE_EFFECT = -0.206  # ATT observé : réduction HbA1c HIGH vs REST

POWER_THRESHOLD = 80.0  # power minimale pour soumission réglementaire
POWER_MARGINAL_FLOOR = 70.0  # en-dessous → redesign, pas de soumission

# σ calibré pour que la formule analytique colle au bootstrap au baseline.
SIGMA_NOISE = {"low": 0.82, "medium": 1.05, "high": 1.38}

# Fix T4 — calibration σ PAR OUTCOME (défaut = medium ; valeurs réelles à affiner
# sur les cohortes partenaires, données non disponibles ici).
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
    """Résout le σ : explicite > calibration par outcome (T4) > medium par défaut."""
    if sigma is not None:
        return sigma
    if outcome and outcome in OUTCOME_SIGMA:
        return OUTCOME_SIGMA[outcome]
    return SIGMA_NOISE["medium"]
