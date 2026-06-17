// Single source of truth for workflow navigation.
// StepNav (left rail) + each view's own Back/Next footer consume this.

// Canonical linear order across all views.
export const VIEW_ORDER = [
  "assistant",
  "dataset_verify",
  "profiling_run",
  "profile",
  "outcomes",
  "causal",
  "datacheck",
  "studytype",
  "design",
  "simulation",
  "results",
  "sensitivity",
  "report",
  "monitoring",
];

// Per-view display label (used by per-view "Back: <label>" / "Next: <label>" buttons).
export const VIEW_LABEL = {
  assistant:      "1a · Product & research question",
  dataset_verify: "1b · Dataset & structure",
  profiling_run:  "Profiling Run",
  profile:        "Benchmark Profiling",
  outcomes:       "Causal Definition",
  causal:         "Causal model",
  datacheck:      "Variable availability",
  studytype:      "Study design",
  design:         "Statistical Analysis",
  simulation:     "Simulation",
  results:        "Results",
  sensitivity:    "Sensitivity",
  report:         "Report",
  monitoring:     "Monitoring",
};

export function prevView(view) {
  const i = VIEW_ORDER.indexOf(view);
  return i > 0 ? VIEW_ORDER[i - 1] : null;
}

export function nextView(view) {
  const i = VIEW_ORDER.indexOf(view);
  return i >= 0 && i < VIEW_ORDER.length - 1 ? VIEW_ORDER[i + 1] : null;
}

// Whether a view is reachable given current app state.
// Mirrors the gating logic already in LucisApp (tabAccessible + phase locks).
export function isViewAccessible(view, ctx) {
  const { hasDataset, profileReady, completedTab, lockedEstimator, tabAccessible } = ctx;

  // Data input is always accessible.
  if (view === "assistant") return true;

  // Dataset & structure is always reachable — it's the page where you upload.
  if (view === "dataset_verify") return true;

  // Profiling sub-tabs use the existing sequential gate from LucisApp.
  if (view === "profiling_run") return profileReady;
  if (["profile","outcomes","causal","datacheck","studytype","design"].includes(view)) {
    return tabAccessible ? tabAccessible(view) : false;
  }

  // Downstream phases gate on study-design completion + lockedEstimator.
  if (view === "simulation")  return completedTab === "design" && hasDataset;
  if (view === "results")     return !!lockedEstimator && hasDataset;
  if (view === "sensitivity") return !!lockedEstimator && hasDataset;
  if (view === "report")      return !!lockedEstimator && hasDataset;
  if (view === "monitoring")  return !!lockedEstimator && hasDataset;

  return false;
}

// ── Unified workflow model (single source for StepNav map + rail) ───────────
// Each step groups one or more VIEW_ORDER ids. `primaryView` is where a step
// click lands. Icon names resolve via cockpit/icons.jsx <Ico/>.
export const WORKFLOW = [
  { key: "input",     label: "Data input",      icon: "upload",   sub: "Cohort upload · column verification", views: ["assistant", "dataset_verify"], primaryView: "assistant" },
  // Profiling is agent-first: the step lands on the
  // agent-run log, which offers a Run button when no run happened yet; the
  // populated Benchmark Profiling (profile) is the next view in the sequence.
  { key: "profiling", label: "Profiling",       icon: "brain",    sub: "Agentic product & corpus profiling",  views: ["profiling_run", "profile"],     primaryView: "profiling_run" },
  { key: "question",  label: "Causal question", icon: "target",   sub: "Population · exposure · outcome",      views: ["outcomes"],                     primaryView: "outcomes" },
  { key: "dag",       label: "Causal model",    icon: "network",  sub: "DAG · confounder set",                views: ["causal"],                       primaryView: "causal" },
  { key: "verify",    label: "Verification",    icon: "datasets", sub: "Variable availability gate",          views: ["datacheck"],                    primaryView: "datacheck" },
  { key: "design",    label: "Study design",    icon: "ruler",    sub: "Estimand · analysis plan",            views: ["studytype", "design"],          primaryView: "studytype" },
  { key: "sim",       label: "Simulation",      icon: "flask",    sub: "Digital-twin power simulation",       views: ["simulation"],                   primaryView: "simulation" },
  { key: "results",   label: "Results",         icon: "statsup",  sub: "Effect estimates · forest plot",      views: ["results"],                      primaryView: "results" },
  { key: "sens",      label: "Sensitivity",     icon: "shield",   sub: "E-values · robustness",               views: ["sensitivity"],                  primaryView: "sensitivity" },
  { key: "report",    label: "Report",          icon: "page",     sub: "Submission-ready dossier",            views: ["report", "monitoring"],         primaryView: "report" },
];

// view id → its step object (or null)
export function stepForView(view) {
  return WORKFLOW.find((s) => s.views.includes(view)) || null;
}

// is this a known workflow view?
export function isWorkflowView(view) {
  return VIEW_ORDER.includes(view);
}

// Map a step's lifecycle to a display state, given app ctx + the cockpit study's
// own per-step state as a fallback. Mirrors Sidebar.groupStatus but keyed by
// WORKFLOW step.key.
export function stepStateFor(stepKey, ctx, studyStepState) {
  const { hasDataset, profileReady, completedTab, lockedEstimator, currentView } = ctx;
  const step = WORKFLOW.find((s) => s.key === stepKey);
  const isCurrent = step && currentView && step.views.includes(currentView);
  if (isCurrent) return "active";
  if (stepKey === "input")     return hasDataset ? "done" : "ready";
  if (stepKey === "profiling") return profileReady ? (completedTab ? "done" : "ready") : (hasDataset ? "ready" : "locked");
  if (["question", "dag", "verify", "design"].includes(stepKey)) {
    return profileReady ? "ready" : "locked";
  }
  if (["sim", "results", "sens", "report"].includes(stepKey)) {
    return lockedEstimator && hasDataset ? "ready" : "locked";
  }
  return studyStepState || "locked";
}
