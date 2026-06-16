// workspaceData.js — faithful copy of window.DATA fixtures from the design reference (data.jsx).
// Shared with HomePage (Brick 2f) and future Brick 2g list pages.

export const RUNS = [
  { id: "r1", study: "Lucis",     kind: "Power simulation",   estimator: "TMLE",                  mode: "VALIDATED", power: 0.86, when: "2h ago",   state: "done"    },
  { id: "r2", study: "Lucis",     kind: "Estimator sweep",    estimator: "LME · OLS · IPW · TMLE", mode: "LIVE",      power: 0.81, when: "5h ago",   state: "done"    },
  { id: "r3", study: "Bloomlife", kind: "Profiling run",      estimator: "—",                      mode: "LIVE",      power: null, when: "Just now", state: "running" },
  { id: "r4", study: "Lucis",     kind: "Bootstrap (2,000×)", estimator: "TMLE",                  mode: "VALIDATED", power: 0.84, when: "Yesterday", state: "done"   },
];

export const DATASETS = [
  { id: "d1", name: "lucis_synthetic_N8400",  rows: "8,400", cols: 47, study: "Lucis",     state: "verified", when: "2d ago"   },
  { id: "d2", name: "lucis_study_cohort",      rows: "824",   cols: 31, study: "Lucis",     state: "flag",     flags: 2, when: "2h ago" },
  { id: "d3", name: "bloomlife_rpm_2025",      rows: "1,240", cols: 38, study: "Bloomlife", state: "verified", when: "Just now" },
  { id: "d4", name: "validation_holdout",      rows: "2,100", cols: 31, study: "Lucis",     state: "verified", when: "1w ago"   },
];

export const CORPUS = {
  total: "1,248",
  sources: [
    { name: "PubMed",             count: 642,  icon: "book"   },
    { name: "ClinicalTrials.gov", count: 318,  icon: "flask"  },
    { name: "MAUDE",              count: 196,  icon: "shield" },
    { name: "FDA Guidance",       count: 92,   icon: "page"   },
  ],
};

export const DOSSIERS = [
  { id: "do1", name: "Lucis — DiGA evidence dossier",  framework: "DiGA",        state: "draft",  pct: 62, when: "2h ago" },
  { id: "do2", name: "Lucis — CONSORT-AI checklist",    framework: "CONSORT-AI",  state: "locked", pct: 0,  when: "—"      },
  { id: "do3", name: "Bloomlife — EUnetHTA brief",      framework: "EUnetHTA",    state: "locked", pct: 0,  when: "—"      },
];

export const VARIABLES = [
  { v: "engagement_score",    role: "Exposure",   study: "Lucis",     type: "continuous", ok: true  },
  { v: "rec_adherence_pct",   role: "Mechanism",  study: "Lucis",     type: "continuous", ok: true  },
  { v: "hba1c_12m",           role: "Outcome",    study: "Lucis",     type: "continuous", ok: true  },
  { v: "diet_quality",        role: "Confounder", study: "Lucis",     type: "—",          ok: false },
  { v: "household_income",    role: "Confounder", study: "Lucis",     type: "—",          ok: false },
  { v: "rpm_adherence_nights", role: "Exposure",  study: "Bloomlife", type: "count",      ok: true  },
  { v: "preterm_birth_37w",   role: "Outcome",    study: "Bloomlife", type: "binary",     ok: true  },
];

export const CORPUS_COVERAGE = [
  { label: "Preventive biomarkers · Lucis",    pct: 78, color: "#047857" },
  { label: "Maternal-fetal RPM · Bloomlife",   pct: 54, color: "#3172B0" },
  { label: "Glycemic outcomes",                pct: 91, color: "#047857" },
];
