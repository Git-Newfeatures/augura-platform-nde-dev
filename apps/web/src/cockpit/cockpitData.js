// cockpitData.js — data + STEP_TO_VIEW map (no JSX)
import { isMockEnabled } from '../mocks/mockMode';
import { getNewStudy, getNewStudies, slugify } from '../workspace/newStudies';

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

// ── Per-study state maps (from data.jsx) ──────────────────────────────────
const lucisStates = {
  input: "done", profiling: "done", question: "done", dag: "active",
  verify: "pending", design: "locked", sim: "locked", results: "locked",
  sens: "locked", report: "locked",
};

const bloomStates = {
  input: "done", profiling: "active", question: "locked", dag: "locked",
  verify: "locked", design: "locked", sim: "locked", results: "locked",
  sens: "locked", report: "locked",
};

function withState(stateMap) {
  return STEP_DEFS.map(s => ({ ...s, state: stateMap[s.key] }));
}

// ── Fixtures ──────────────────────────────────────────────────────────────
const STUDIES = {
  lucis: {
    id: "lucis",
    initial: "L",
    name: "Lucis",
    tagline: "Preventive biomarker platform",
    category: "Consumer wellness",
    framework: "DiGA · CONSORT-AI",
    n: 824,
    lead: "Dr. Romain Pirracchio",
    updated: "2 hours ago",
    steps: withState(lucisStates),
    done: 3,
    total: 10,
    activeStep: 4,
    question: {
      population: "Adults with prediabetes (HbA1c 5.7–6.4) · ≥12 months follow-up",
      exposure: "Lucis engagement — High (>70) vs Low (<30) composite score",
      outcome: "Change in HbA1c at 12 months",
      nNote: "N = 824 after eligibility filtering",
    },
    readiness: 62,
    readinessRows: [
      { label: "Causal question",      state: "done" },
      { label: "DAG confounder set",   state: "flag", note: "2 of 9 confounders unmeasured" },
      { label: "Variable availability", state: "flag", note: "2 soft flags on cohort" },
      { label: "Estimator locked",     state: "locked" },
      { label: "Dossier compiled",     state: "locked" },
    ],
    actions: [
      { id: "a1", tone: "amber",    icon: "flag",    title: "Triage 2 soft flags on the Lucis cohort",          meta: "Step 5 · Verification gate",  step: 5 },
      { id: "a2", tone: "amber",    icon: "network", title: "Resolve 2 unmeasured confounders in the DAG",      meta: "Step 4 · Causal model",       step: 4 },
      { id: "a3", tone: "bluecorn", icon: "check",   title: "Confirm causal question to lock the design",       meta: "Step 3 → Step 6",             step: 3 },
    ],
  },

  bloomlife: {
    id: "bloomlife",
    initial: "B",
    name: "Bloomlife",
    tagline: "High-risk pregnancy · remote fetal monitoring",
    category: "Maternal-fetal RPM",
    framework: "EU MDR · NICE DSP",
    n: 1240,
    lead: "Dr. Matthieu Legrand",
    isNew: true,
    updated: "Just now",
    steps: withState(bloomStates),
    done: 1,
    total: 10,
    activeStep: 2,
    question: {
      population: "Pregnancies ≥ 28 weeks flagged high-risk",
      exposure: "Continuous RPM adherence ≥ 5 nights/week",
      outcome: "Preterm delivery before 37 weeks",
      nNote: "N = 1,240 enrolled",
    },
    readiness: 18,
    readinessRows: [
      { label: "Causal question",       state: "active" },
      { label: "DAG confounder set",    state: "locked" },
      { label: "Variable availability", state: "locked" },
      { label: "Estimator locked",      state: "locked" },
      { label: "Dossier compiled",      state: "locked" },
    ],
    actions: [
      { id: "b1", tone: "bluecorn", icon: "brain", title: "Review the product profile draft", meta: "Step 2 · Profiling", step: 2 },
    ],
  },
};

// Generic default for any unknown projectId
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

// Build a full study object (cockpit shape) from a New-study record.
function studyFromCreated(created) {
  const base = makeDefault(created.id);
  return {
    ...base,
    name: created.name,
    initial: (created.name[0] || '?').toUpperCase(),
    tagline: created.tagline || base.tagline,
    category: created.category || base.category,
    framework: created.framework || base.framework,
    n: created.n ?? base.n,
    isNew: true,
    updated: 'Just now',
  };
}

// In demo mode the whole flow is walkable — unlock any "locked" steps so all 10
// steps can be clicked through end to end (the bounce-guard is also skipped in demo).
function unlockForDemo(study) {
  return {
    ...study,
    steps: study.steps.map((s) => (s.state === 'locked' ? { ...s, state: 'ready' } : s)),
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

/** Returns the fixture for a known projectId, or a generic default.
 *  Priority: a study created via the New-study flow → demo fixture (when
 *  Demo-data is ON) → a blank default. */
export function getCockpitStudy(projectId) {
  const created = getNewStudy(projectId);
  if (created) return isMockEnabled() ? unlockForDemo(studyFromCreated(created)) : studyFromCreated(created);
  if (!isMockEnabled()) return makeDefault(projectId);
  return unlockForDemo(STUDIES[projectId] || makeDefault(projectId));
}

/** Returns all studies for the dashboard: ones created via the New-study flow
 *  (newest first) followed by the demo fixtures. */
export function getAllStudies() {
  const created = Object.values(getNewStudies())
    .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))
    .map(studyFromCreated);
  const demo = ['lucis', 'bloomlife'].map((id) => STUDIES[id]);
  return [...created, ...demo];
}
