/**
 * Augura E2 — Clinical constants and simulation configuration
 * ============================================================
 * Source: lucis_synthetic_study_cohort.csv
 *
 * ⚠️  Do not edit these numbers without sign-off.
 *    They are used by both SimulationEngine.jsx (UI) and
 *    simulation/run_bootstrap.py (Python bootstrap).
 */

// ── Cohort facts (from Lucis synthetic study cohort CSV) ─────────────────────
export const COHORT_N    = 824;      // Full cohort size
export const TREAT_PROP  = 0.231;    // HIGH engagers = top quartile of engagement score
// Note: ~23.1% (190/824) — not exactly 25% because the engagement distribution is skewed
// D1 decision: binary split HIGH vs REST (medium + low engagers combined)
export const TRUE_EFFECT = -0.206;   // Observed ATT: HbA1c reduction for HIGH vs REST
// (TENANT_ID retiré : le tenant est résolu côté backend depuis le JWT — plus de
//  lecture PostgREST directe avec un tenant codé en dur. cf. workspace/cohortData.js)

// ── Regulatory thresholds (ICH E9 / HAS PECAN / DiGA BfArM) ─────────────────
export const POWER_THRESHOLD      = 80; // Minimum required power for regulatory submission
export const POWER_MARGINAL_FLOOR = 70; // Below this → study redesign, no submission path

// ── Calibrated noise parameters ──────────────────────────────────────────────
// σ_eff calibrated so the analytical formula matches the bootstrap at baseline
// (87% power with medium noise, N=824, 20% dropout, effect=0.30)
export const SIGMA_NOISE = {
  low:    0.82,   // Well-controlled study, rich covariates, clean data
  medium: 1.05,   // Expected real-world conditions (calibrated reference)
  high:   1.38,   // Conservative — high confounding, data quality issues
};

// ── Estimator configuration ───────────────────────────────────────────────────
// D2 decision: ATT estimand (Average Treatment effect on the Treated)
// D3 decision: minimal confounders — age, sex, BMI, hba1c_t0

export const BASE_BIAS = {
  lme:       0.010,  // Linear mixed-effects — best for repeated measures
  ols:       0.018,  // Ordinary least squares — robustness check
  ipw:       0.021,  // Inverse probability weighting — handles selection bias
  mediation: 0.012,  // Causal mediation — decomposes direct/indirect effects
  tmle:      0.009,  // TMLE — doubly robust, placeholder (bootstrap pending)
  did:       0.015,  // DID — time-invariant confounders, placeholder (bootstrap pending)
};

export const EST_EFFICIENCY = {
  lme:       1.00,   // Reference — most efficient for longitudinal data
  ols:       0.95,   // Slight penalty (ignores within-patient correlation)
  ipw:       0.88,   // Less efficient but robust to unmeasured confounding
  mediation: 0.98,   // Near-equivalent to LME
  tmle:      0.96,   // Doubly robust — near-LME efficiency (placeholder)
  did:       0.90,   // DID — parallel trends required, modest efficiency loss (placeholder)
};

export const ESTIMATORS = [
  { key: "lme",       label: "Mixed-effects (LME)",          short: "LME",       recommended: true,  bootstrapPending: false,
    interpretability: 4, stability: true,
    tooltip: "Best fit for longitudinal data with repeated measurements per user. Accounts for individual variation over time. Recommended for Lucis because biomarkers are measured every 3–6 months." },
  { key: "ols",       label: "Linear regression (OLS)",      short: "OLS",       recommended: false, bootstrapPending: false,
    interpretability: 5, stability: true,
    tooltip: "Simple benchmark model. Easier to interpret but assumes one measurement per user. Useful to compare against LME — if results diverge, the repeated-measures structure matters." },
  { key: "ipw",       label: "Propensity weighting (IPW)",   short: "IPW",       recommended: false, bootstrapPending: false,
    interpretability: 3, stability: false,
    tooltip: "Reweights users so the HIGH and REST groups look comparable on observed characteristics (age, BMI, baseline HbA1c). Useful when the groups differ at baseline. Higher variance than LME." },
  { key: "mediation", label: "Causal mediation",             short: "Mediation", recommended: true,  bootstrapPending: false,
    interpretability: 3, stability: true,
    tooltip: "Splits the total effect into direct (platform → HbA1c) and indirect (platform → behaviour change → HbA1c). Quantifies how much of the benefit is driven by recommendation adherence." },
  { key: "tmle",      label: "TMLE (Doubly robust)",         short: "TMLE",      recommended: false, bootstrapPending: true,
    interpretability: 2, stability: true,
    tooltip: "Advanced method that combines outcome and propensity models. Remains valid even if one of the two models is misspecified. Most robust to confounding but requires larger samples." },
  { key: "did",       label: "Difference-in-differences",    short: "DID",       recommended: false, bootstrapPending: true,
    interpretability: 4, stability: false,
    tooltip: "Compares how much each group changed over time, rather than absolute levels. Controls for baseline differences that are stable over time. Requires that both groups would have evolved similarly without the intervention (parallel trends assumption)." },
];

// ── Estimator eligibility per study type ─────────────────────────────────────
// Used by both CausalModel (LucisApp) and SimulationEngine to show only the
// statistically appropriate estimators for the chosen E1 study type.
export const ESTIMATOR_FILTER = {
  // Observational/retrospective: all estimators applicable
  retro: ["lme", "ols", "ipw", "mediation", "tmle", "did"],
  // Prospective/RCT: IPW not needed (enrolment controls selection bias); DID requires parallel trends unlikely in RCT
  prosp: ["lme", "ols", "mediation", "tmle"],
};

// ── Pre-computed validated scenarios ─────────────────────────────────────────
// Source: simulation/run_bootstrap.py — N=1,000 iterations, Python 3.12, scikit-learn 1.4
// These represent the regulatory stress-test submitted to HAS/DiGA
// To refresh: run `python simulation/run_bootstrap.py` after D1-D3 final sign-off
export const VALIDATED = {
  baseline: {
    label: "Baseline", n: 824, dropout: 0.20, effect: 0.30, noise: "medium",
    description: "Expected real-world conditions",
    results: {
      //                                                                ci_coverage: estimated (†) — per-iteration CI tracking not in current bootstrap output
      lme:       { power: 87, bias: 0.010, variance: 0.034, mse: 0.035, effect: -0.36, ci: [-0.42, -0.26], ci_coverage: 94 },
      ols:       { power: 82, bias: 0.018, variance: 0.041, mse: 0.043, effect: -0.33, ci: [-0.40, -0.24], ci_coverage: 92 },
      ipw:       { power: 79, bias: 0.021, variance: 0.052, mse: 0.056, effect: -0.31, ci: [-0.44, -0.22], ci_coverage: 90 },
      mediation: { power: 85, bias: 0.012, variance: 0.038, mse: 0.038, effect: -0.34, ci: [-0.40, -0.26], ci_coverage: 93 },
    },
  },
  conservative: {
    label: "Conservative", n: 824, dropout: 0.27, effect: 0.20, noise: "high",
    description: "Pessimistic — regulatory stress test",
    results: {
      lme:       { power: 61, bias: 0.024, variance: 0.061, mse: 0.062, effect: -0.20, ci: [-0.38, -0.10], ci_coverage: 91 },
      ols:       { power: 54, bias: 0.031, variance: 0.074, mse: 0.075, effect: -0.18, ci: [-0.36, -0.08], ci_coverage: 89 },
      ipw:       { power: 48, bias: 0.038, variance: 0.089, mse: 0.091, effect: -0.16, ci: [-0.40, -0.04], ci_coverage: 87 },
      mediation: { power: 58, bias: 0.026, variance: 0.065, mse: 0.066, effect: -0.19, ci: [-0.37, -0.09], ci_coverage: 90 },
    },
  },
  high_risk: {
    label: "Optimised", n: 510, dropout: 0.15, effect: 0.40, noise: "medium",
    description: "High-risk subgroup (hba1c_t0 > 6.0)",
    results: {
      lme:       { power: 93, bias: 0.008, variance: 0.028, mse: 0.028, effect: -0.40, ci: [-0.52, -0.30], ci_coverage: 95 },
      ols:       { power: 89, bias: 0.014, variance: 0.034, mse: 0.034, effect: -0.38, ci: [-0.50, -0.28], ci_coverage: 93 },
      ipw:       { power: 85, bias: 0.017, variance: 0.042, mse: 0.043, effect: -0.36, ci: [-0.53, -0.26], ci_coverage: 91 },
      mediation: { power: 91, bias: 0.010, variance: 0.031, mse: 0.031, effect: -0.39, ci: [-0.51, -0.31], ci_coverage: 94 },
    },
  },
};
