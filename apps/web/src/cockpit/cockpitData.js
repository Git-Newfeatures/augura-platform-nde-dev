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
 *  blank scaffold for the id when no live row/progress is available. */
export function getCockpitStudy(projectId) {
  return makeDefault(projectId);
}

// completedTab scale (LucisApp.TAB_ORDER) → which workflow steps are "done".
const TAB_ORDER = ["profile", "outcomes", "causal", "datacheck", "studytype", "design"];

function tabReached(completedTab, tab) {
  return TAB_ORDER.indexOf(completedTab) >= TAB_ORDER.indexOf(tab);
}

// Live state of one workflow step, derived from the app's real progress.
function stepStateFromProgress(key, p, isCurrent) {
  if (isCurrent) return "active";
  const afterProfiling = p.profileReady ? "ready" : p.hasDataset ? "pending" : "locked";
  switch (key) {
    case "input":     return p.hasDataset ? "done" : "active";
    case "profiling": return p.profileReady ? "done" : p.hasDataset ? "ready" : "pending";
    case "question":  return tabReached(p.completedTab, "outcomes") ? "done" : afterProfiling;
    case "dag":       return tabReached(p.completedTab, "causal") ? "done" : afterProfiling;
    case "verify":    return tabReached(p.completedTab, "datacheck") ? "done" : afterProfiling;
    case "design":    return tabReached(p.completedTab, "design") ? "done" : afterProfiling;
    case "sim":       return p.simResults ? "done" : p.lockedEstimator ? "ready" : "locked";
    case "results":   return p.simResults ? "done" : "locked";
    case "sens":      return p.simResults ? "ready" : "locked";
    case "report":    return p.simResults ? "ready" : "locked";
    default:          return "locked";
  }
}

/**
 * Builds the full cockpit study shape from the LIVE backend study row + the app's
 * real workflow progress. `row` is the GET /studies/:id payload (or null → scaffold);
 * `progress` carries { hasDataset, profileReady, completedTab, lockedEstimator,
 * simResults, currentView, question }.
 */
export function buildCockpitStudy(projectId, row, progress = {}) {
  const base = row ? studyFromRow({ ...row, n: row.n_subjects ?? row.n }) : makeDefault(projectId);
  const p = progress;

  const steps = STEP_DEFS.map((s) => ({
    ...s,
    state: stepStateFromProgress(s.key, p, STEP_TO_VIEW[s.key] === p.currentView),
  }));
  const done = steps.filter((s) => s.state === "done").length;
  const activeIdx = steps.findIndex((s) => s.state === "active");
  const activeStep = activeIdx >= 0 ? activeIdx + 1 : Math.min(done + 1, STEP_DEFS.length);

  const q = p.question || {};
  const readinessRows = [
    { label: "Causal question",       done: tabReached(p.completedTab, "outcomes") },
    { label: "DAG confounder set",    done: tabReached(p.completedTab, "causal") },
    { label: "Variable availability", done: tabReached(p.completedTab, "datacheck") },
    { label: "Estimator locked",      done: !!p.lockedEstimator },
    { label: "Dossier compiled",      done: !!p.simResults },
  ];
  const doneRows = readinessRows.filter((r) => r.done).length;

  // Single contextual "needs attention" action — the next thing to do.
  const actions = [];
  if (!p.hasDataset) actions.push({ step: 1, label: "Upload your cohort to begin" });
  else if (!p.profileReady) actions.push({ step: 2, label: "Run the profiling agent" });
  else if (!tabReached(p.completedTab, "design")) actions.push({ step: 6, label: "Complete the study design" });
  else if (!p.lockedEstimator) actions.push({ step: 7, label: "Run the simulation and lock an estimator" });
  else if (!p.simResults) actions.push({ step: 8, label: "Review results" });

  return {
    ...base,
    id: projectId,
    steps,
    done,
    total: STEP_DEFS.length,
    activeStep,
    question: {
      population: q.population || "—",
      exposure: q.exposure || "—",
      outcome: q.outcome || "—",
      nNote: base.n ? `N = ${base.n}` : "",
    },
    readiness: Math.max(5, Math.round((doneRows / readinessRows.length) * 100)),
    readinessRows: readinessRows.map((r, i) => ({
      label: r.label,
      state: r.done ? "done" : i === doneRows ? "active" : "locked",
    })),
    actions,
  };
}
