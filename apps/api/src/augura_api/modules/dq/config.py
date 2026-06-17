"""Constantes DQ — profils de poids, dimensions, seuils, déductions (MVP dq-config.js)."""

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "exploratory": {
        "completeness": 0.25,
        "validity": 0.25,
        "consistency": 0.20,
        "coherence": 0.15,
        "labelling": 0.15,
    },
    "regulatory": {
        "completeness": 0.20,
        "validity": 0.35,
        "consistency": 0.30,
        "coherence": 0.10,
        "labelling": 0.05,
    },
}
DIMENSION_CATEGORIES: dict[str, list[str]] = {
    "completeness": ["missing"],
    "validity": ["type", "unit", "range"],
    "consistency": ["consistency"],
    "coherence": ["coherence"],
    "labelling": ["labelling"],
}
THRESHOLDS = {"mostly_missing": 0.70, "outlier_iqr_factor": 3.0, "max_evidence_rows": 10}
SEVERITY_DEDUCTIONS = {"hard": 0.10, "soft": 0.03, "info": 0.0}
POLICY_VERSION = "1.0.0"
