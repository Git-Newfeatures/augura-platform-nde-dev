// cockpitData.js — workflow step map + cockpit study shape (no JSX)
import { slugify } from '@/lib/utils';

export const STEP_TO_VIEW = {
  input:     "assistant",
  profiling: "profile",
  question:  "outcomes",
  dag:       "causal",
  verify:    "datacheck",
  design:    "studytype",
  sim:       "simulation",
  results:   "results",
  sens:      "sensitivity",
  report:    "report",
};

// 10 canonical workflow steps (shared shape, no per-study state)
export const STEP_DEFS = [
  { n: 1,  key: "input",     label: "Data input",     icon: "upload",   sub: "Cohort upload · column verification" },
  { n: 2,  key: "profiling", label: "Profiling",       icon: "brain",    sub: "Agentic product & corpus profiling" },
  { n: 3,  key: "question",  label: "Causal question", icon: "target",   sub: "Population · exposure · outcome" },
  { n: 4,  key: "dag",       label: "Causal model",    icon: "network",  sub: "DAG · confounder set" },
  { n: 5,  key: "verify",    label: "Verification",    icon: "datasets", sub: "Variable availability gate" },
  { n: 6,  key: "design",    label: "Study design",    icon: "ruler",    sub: "Estimand · analysis plan" },
  { n: 7,  key: "sim",       label: "Simulation",      icon: "flask",    sub: "Digital-twin power simulation" },
  { n: 8,  key: "results",   label: "Results",         icon: "statsup",  sub: "Effect estimates · forest plot" },
  { n: 9,  key: "sens",      label: "Sensitivity",     icon: "shield",   sub: "E-values · robustness" },
  { n: 10, key: "report",    label: "Report",          icon: "page",     sub: "Submission-ready dossier" },
];

/** Returns the view id for a step key (e.g. "dag" → "causal"). */
export function viewForStepKey(key) {
  return STEP_TO_VIEW[key];
}

/** Returns the view id for a 1-based step number. */
export function viewForStepNumber(n) {
  const def = STEP_DEFS[n - 1];
  return def ? STEP_TO_VIEW[def.key] : undefined;
}

// Generic blank study scaffold for a projectId (cockpit shape).
function makeDefault(projectId) {
  return {
    id: projectId,
    initial: (projectId[0] || "?").toUpperCase(),
    name: projectId,
    tagline: "Evidence study",
    category: "—",
    framework: "—",
    n: 0,
    lead: "—",
    steps: STEP_DEFS.map((s, i) => ({
      ...s,
      state: i === 0 ? "active" : "pending",
    })),
    done: 0,
    total: 10,
    activeStep: 1,
    question: {
      population: "—",
      exposure: "—",
      outcome: "—",
      nNote: "",
    },
    readiness: 5,
    readinessRows: [
      { label: "Causal question",       state: "active" },
      { label: "DAG confounder set",    state: "locked" },
      { label: "Variable availability", state: "locked" },
      { label: "Estimator locked",      state: "locked" },
      { label: "Dossier compiled",      state: "locked" },
    ],
    actions: [],
  };
}

// Normalize a raw Supabase study row (which lacks the workflow-progress fields:
// steps, activeStep, done, total, readiness…) to the full cockpit shape, so the
// dashboard cards and rail render without crashing in real (non-demo) mode.
export function studyFromRow(row) {
  if (!row || typeof row !== 'object') return makeDefault('study');
  const id = row.id || slugify(row.name || 'study');
  const base = makeDefault(id);
  return {
    ...base,
    id,
    name: row.name ?? base.name,
    initial: String((row.name || base.name || '?')[0] || '?').toUpperCase(),
    tagline: row.tagline ?? row.description ?? base.tagline,
    category: row.category ?? base.category,
    framework: row.framework ?? base.framework,
    n: row.n ?? row.cohort_n ?? base.n,
    lead: row.lead ?? base.lead,
    updated: row.updated ?? base.updated,
  };
}

/** Returns the cockpit study shape for a projectId. The studies list is sourced
 *  live from the backend (see workspace/dataClient); the cockpit detail builds a
 *  blank scaffold for the id (no per-study backend fetch wired yet). */
export function getCockpitStudy(projectId) {
  return makeDefault(projectId);
}
