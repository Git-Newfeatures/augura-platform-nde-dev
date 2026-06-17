/**
 * Augura E2 — Estimator / regulatory UI configuration
 * ====================================================
 * Presentational config only: estimator labels, tooltips, eligibility, and the
 * regulatory power thresholds. All numeric study results now come from the live
 * backend (fetchSimulationResults / fetchCohort) — there are no fabricated
 * cohort, effect, noise, bias, or pre-computed scenario fallbacks here anymore.
 * (TENANT_ID retiré : le tenant est résolu côté backend depuis le JWT.
 *  cf. workspace/cohortData.js)
 */

// ── Regulatory thresholds (ICH E9 / HAS PECAN / DiGA BfArM) ─────────────────
export const POWER_THRESHOLD      = 80; // Minimum required power for regulatory submission
export const POWER_MARGINAL_FLOOR = 70; // Below this → study redesign, no submission path

// ── Estimator configuration ───────────────────────────────────────────────────
// D2 decision: ATT estimand (Average Treatment effect on the Treated)
// D3 decision: minimal confounders — age, sex, BMI, hba1c_t0

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
