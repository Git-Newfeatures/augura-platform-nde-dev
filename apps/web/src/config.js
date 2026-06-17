/**
 * Augura E2 — Regulatory UI configuration
 * =======================================
 * Presentational config only: the regulatory power thresholds. All numeric
 * study results now come from the live backend (fetchSimulationResults /
 * fetchCohort) — there are no fabricated cohort, effect, noise, bias, or
 * pre-computed scenario fallbacks here anymore. Estimator metadata and
 * eligibility are sourced from /reference/estimators.
 * (TENANT_ID retiré : le tenant est résolu côté backend depuis le JWT.
 *  cf. workspace/cohortData.js)
 */

// ── Regulatory thresholds (ICH E9 / HAS PECAN / DiGA BfArM) ─────────────────
export const POWER_THRESHOLD      = 80; // Minimum required power for regulatory submission
export const POWER_MARGINAL_FLOOR = 70; // Below this → study redesign, no submission path
