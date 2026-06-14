import React, { useState, useEffect } from "react";
import { Check, AlertTriangle, ChevronDown, ChevronUp, Database, Sparkles } from "lucide-react";
import { Card, Tag } from "../ui/components";
import { Button } from "@/components/ui/button";
import { useCollection } from "@/workspace/dataClient";
import { isMockEnabled } from "@/mocks/mockMode";
import { apiJson } from "@/api";

// Realistic cardiometabolic column pool — sliced to the selected dataset's column
// count so the agent classification matches it (e.g. a 47-col dataset → 47 columns).
const COHORT_COLUMN_POOL = [
  "member_id", "visit_date", "timepoint_months", "age", "sex", "bmi", "engagement_score",
  "hba1c_baseline", "hba1c_12m", "ldl_12m", "crp_12m",
  "rec_adherence_pct", "logins_per_month", "sessions_per_week", "repeat_test_flag", "recommendations_followed",
  "weight_kg", "height_cm", "waist_cm", "systolic_bp", "diastolic_bp",
  "ldl_baseline", "hdl_baseline", "hdl_12m", "triglycerides_baseline", "triglycerides_12m",
  "total_cholesterol_baseline", "total_cholesterol_12m", "glucose_fasting_baseline", "glucose_fasting_12m",
  "insulin_baseline", "homa_ir", "hs_crp_baseline", "egfr", "alt", "ast",
  "smoking_status", "alcohol_units_week", "physical_activity_min", "diet_quality", "sleep_hours",
  "perceived_stress", "household_income", "education_level", "employment_status", "country", "country_hdi",
  "comorbidity_count", "medication_count", "statin_use", "antihypertensive_use",
];
function cohortHeaders(nCols) {
  const n = Math.max(1, Number(nCols) || 11);
  const out = COHORT_COLUMN_POOL.slice(0, n);
  while (out.length < n) out.push(`feature_${out.length + 1}`);
  return out;
}

// ── PII column-name scan ──────────────────────────────────────────────────────
const PII_PATTERNS = [
  { rx: /\b(first_?name|last_?name|full_?name|given_?name|family_?name)\b/i, reason: "name field" },
  { rx: /\bemail|e_mail|e-mail\b/i,                                           reason: "email" },
  { rx: /\bphone|mobile|telephone\b/i,                                        reason: "phone" },
  { rx: /\baddress|street|postal|zip_?code|postcode\b/i,                      reason: "postal address" },
  { rx: /\b(dob|date_?of_?birth|birth_?date|birthday)\b/i,                   reason: "date of birth" },
  { rx: /\b(ssn|social_?security|national_?id|nhs_?number|nin)\b/i,          reason: "government ID" },
  { rx: /\bpassport\b/i,                                                      reason: "passport" },
  { rx: /\bip_?address\b/i,                                                   reason: "IP address" },
  { rx: /\bdevice_?id\b/i,                                                    reason: "device ID" },
];
function scanForPII(sheets) {
  const flagged = [];
  for (const sheet of sheets || []) {
    for (const h of sheet.headers || []) {
      const name = String(h || "").toLowerCase().trim();
      if (!name) continue;
      for (const p of PII_PATTERNS) {
        if (p.rx.test(name)) { flagged.push({ sheet: sheet.name, column: h, reason: p.reason }); break; }
      }
    }
  }
  return { status: flagged.length ? "error" : "ok", flagged };
}

// ── Group definitions (aligned with Augura spec Q5–Q8) ────────────────────────
const GROUPS = [
  { id: "outcomes",       label: "Outcomes",                 tagColor: "b", description: "Dependent variables measured at follow-up" },
  { id: "exposure",       label: "Exposure / intervention",  tagColor: "g", description: "Primary treatment or intervention variable" },
  { id: "engagement",     label: "Engagement & environment", tagColor: "p", description: "App usage, adherence, login, recommendation completion; geography, socioeconomic context, and healthcare system variables" },
  { id: "administrative", label: "Administrative",           tagColor: "b", description: "Patient / member IDs, record keys, visit dates, timepoints, and columns not relevant to this study" },
  { id: "other",          label: "Other / unclassified",     tagColor: "r", description: "Cannot be confidently classified" },
];

// Remap legacy / API-returned group IDs to the consolidated set above.
// Confounders, colliders, and mediators are intentionally excluded from 1b —
// they are handled at the DAG stage.
const GROUP_REMAP = {
  environment:    "engagement",      // merged into Engagement & environment
  user_variables: "other",           // no longer a separate causal group
  mediators:      "other",           // causal role decided at DAG stage
  measured_confounder:   "other",
  unmeasured_confounder: "other",
  collider:       "other",
  identifiers:    "administrative",
  time:           "administrative",
  unused:         "administrative",
};

const ROLES = ["outcome", "exposure", "exposure_component", "effect_modifier", "id", "time", "unused", "other"];
const ROLE_LABEL = {
  outcome: "Outcome", exposure: "Exposure", exposure_component: "Exposure component",
  measured_confounder: "Measured confounder", unmeasured_confounder: "Unmeasured confounder",
  mediator: "Mediator", effect_modifier: "Effect modifier", collider: "Collider",
  id: "ID", time: "Time", unused: "Unused", other: "Other",
};
const ROLE_TAG = {
  outcome: "b", exposure: "g", exposure_component: "g",
  measured_confounder: "a", unmeasured_confounder: "r",
  mediator: "p", effect_modifier: "p", collider: "r",
  id: "b", time: "b", unused: "r", other: "r",
};

const LOW_CONFIDENCE = 0.7;

// ── Launch progress stages (estimated — the API is a single round-trip) ────────
const STAGES = [
  { key: "scan",      label: "Scanning columns" },
  { key: "classify",  label: "Classifying variables" },
  { key: "structure", label: "Inferring study structure" },
];

// ── DQ badges ─────────────────────────────────────────────────────────────────
function DQBadges({ stat }) {
  if (!stat) return null;
  const nullPct = stat.null_pct ?? 0;
  const nullClass = nullPct >= 0.3 ? "text-[#C0392B]" : nullPct >= 0.1 ? "text-[#C47F0A]" : "text-muted-foreground";
  return (
    <div className="flex flex-wrap gap-1.5 font-mono text-[12px] text-muted-foreground">
      <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
        {stat.value_kind}
      </span>
      <span className={`rounded-full border border-border bg-secondary/40 px-2 py-0.5 ${nullClass}`}>
        null {(nullPct*100).toFixed(1)}%
      </span>
      {stat.n_distinct != null && (
        <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
          {stat.n_distinct} distinct
        </span>
      )}
      {stat.value_kind === "numeric" && stat.min != null && (
        <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
          {stat.min}–{stat.max}
        </span>
      )}
    </div>
  );
}

// ── Confidence bar ────────────────────────────────────────────────────────────
function ConfBar({ value }) {
  const pct = Math.max(0, Math.min(1, value || 0));
  const color = pct >= 0.8 ? "#047857" : pct >= LOW_CONFIDENCE ? "#C47F0A" : "#C0392B";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-12 overflow-hidden rounded-full border border-border bg-secondary/40">
        <div className="h-full" style={{ width:`${pct*100}%`, background:color }} />
      </div>
      <span className="font-mono text-[12px] font-semibold" style={{ color }}>{(pct*100).toFixed(0)}%</span>
    </div>
  );
}

// ── Single column row (inside an expanded group) ──────────────────────────────
function ColumnRow({ match, stat, decision, onDecide }) {
  const [expanded, setExpanded] = useState(false);
  const role = decision?.final_role || match.proposed_role;
  const status = decision?.user_decision;

  const dotColor = status === "agreed" ? "#047857" : status === "corrected" ? "#C47F0A" :
                   status === "rejected" ? "#C0392B" : "#C4C2BA";

  return (
    <div
      className={`border-b border-border last:border-b-0 ${role === "unused" ? "bg-secondary/40 opacity-70" : "bg-card opacity-100"}`}
    >
      {/* Compact row */}
      <div className="flex cursor-pointer items-center gap-2.5 px-4 py-2.5" onClick={() => setExpanded(v => !v)}>
        {/* Status dot */}
        <div className="h-2 w-2 flex-shrink-0 rounded-full" style={{ background: dotColor }} />
        {/* Column name */}
        <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[12px] font-medium text-foreground">
          {match.column}
        </span>
        {/* Role tag */}
        <Tag color={ROLE_TAG[role]}>{ROLE_LABEL[role]}</Tag>
        {match.proposed_canonical_label && (
          <span className="max-w-[140px] overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-muted-foreground">
            → {match.proposed_canonical_label}
          </span>
        )}
        <ConfBar value={match.confidence} />
        {expanded
          ? <ChevronUp size={15} className="text-muted-foreground/60" />
          : <ChevronDown size={15} className="text-muted-foreground/60" />}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border bg-secondary/40 px-4 pb-4 pl-9 pt-3">
          <DQBadges stat={stat} />
          {match.rationale && (
            <div className="mt-2 rounded-md border-l-2 border-l-[#3172B0] bg-card px-3 py-2 text-[12.5px] leading-relaxed text-muted-foreground">
              {match.rationale}
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="sm" variant={status !== "agreed" ? "default" : "outline"}
              className="text-xs font-medium"
              onClick={() => onDecide({ user_decision:"agreed", final_role:match.proposed_role, final_canonical_id:match.proposed_canonical_id })}
              style={{ opacity: status === "agreed" ? 0.6 : 1 }}>
              {status === "agreed" ? <><Check size={13} className="mr-1" />Agreed</> : "Agree"}
            </Button>
            <select
              value={status === "corrected" ? decision.final_role : ""}
              onChange={e => e.target.value && onDecide({ user_decision:"corrected", final_role:e.target.value, final_canonical_id: e.target.value === "outcome" ? match.proposed_canonical_id : null })}
              className="cursor-pointer rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground">
              <option value="">Reassign role…</option>
              {ROLES.filter(r => r !== match.proposed_role).map(r => (
                <option key={r} value={r}>{ROLE_LABEL[r]}</option>
              ))}
            </select>
            <Button size="sm" variant="outline" className="text-xs font-medium"
              onClick={() => onDecide({ user_decision:"corrected", final_role:"unused", final_canonical_id:null })}>
              Mark unused
            </Button>
            {match.alternatives?.length > 0 && (
              <span className="text-[12px] italic text-muted-foreground">
                alt: {match.alternatives.join(", ")}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Group accordion ───────────────────────────────────────────────────────────
function GroupAccordion({ group, matches, statFor, variableMappings, onDecide, onAgreeAll, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  if (!matches.length) return null;

  const decided = matches.filter(m => {
    const d = variableMappings?.[`${m.sheet}::${m.column}`];
    return d?.user_decision && d.user_decision !== "pending";
  }).length;
  const allDone = decided === matches.length;

  function agreeAll() {
    onAgreeAll(matches);
  }

  const tagColor = group.tagColor;

  return (
    <Card className={`gap-0 overflow-hidden p-0 ${allDone ? "border-[#5DCAA5]" : ""}`}>
      {/* Group header */}
      <div className={`flex cursor-pointer items-center gap-3 px-4 py-3 ${allDone ? "bg-secondary" : "bg-card"}`}
        onClick={() => setOpen(v => !v)}>
        <Tag color={tagColor}>{matches.length}</Tag>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-foreground">{group.label}</div>
          <div className="mt-0.5 text-[12px] text-muted-foreground">{group.description}</div>
        </div>
        <div className="flex items-center gap-2.5">
          {allDone ? (
            <span className="flex items-center gap-1 text-[12px] font-semibold text-primary"><Check size={13} /> All confirmed</span>
          ) : (
            <span className="font-mono text-[12px] text-muted-foreground">{decided}/{matches.length} confirmed</span>
          )}
          {!allDone && (
            <Button size="sm" className="text-xs font-medium" onClick={e => { e.stopPropagation(); agreeAll(); }}>
              Agree all
            </Button>
          )}
          {open
            ? <ChevronUp size={15} className="text-muted-foreground/60" />
            : <ChevronDown size={15} className="text-muted-foreground/60" />}
        </div>
      </div>

      {/* Column rows */}
      {open && (
        <div className="border-t border-border">
          {matches.map(m => {
            const key = `${m.sheet}::${m.column}`;
            return (
              <ColumnRow
                key={key}
                match={m}
                stat={statFor(m.sheet, m.column)}
                decision={variableMappings?.[key]}
                onDecide={patch => onDecide(m, patch)}
              />
            );
          })}
        </div>
      )}
    </Card>
  );
}

// ── Dataset-level questions (DGM Q1–Q4) ──────────────────────────────────────
const DATASET_Q_LABELS = {
  study_type:          "How was this data collected?",
  temporal_structure:  "Is this data cross-sectional or longitudinal?",
  exposure_assignment: "How were users assigned to the exposure?",
  control_group:       "Is there an unexposed control group?",
};

function DatasetQuestionCard({ q }) {
  const [decision, setDecision] = useState({ status:"pending", answer:q.answer });
  return (
    <Card className={`gap-2 p-4 ${decision.status === "agreed" ? "border-[#5DCAA5]" : ""}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-[13px] font-semibold text-foreground">
          {DATASET_Q_LABELS[q.question_code] || q.question_code}
        </div>
        {decision.status === "agreed" && (
          <span className="flex items-center gap-1 rounded-full border border-[#5DCAA5] bg-secondary px-2.5 py-0.5 text-[12px] font-semibold text-primary"><Check size={12} /> Agreed</span>
        )}
        {decision.status === "corrected" && (
          <span className="rounded-full border border-[#EF9F27] bg-[#FAEEDA] px-2.5 py-0.5 text-[12px] font-semibold text-[#854F0B]">Corrected</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12px] font-medium text-muted-foreground">Agent answer</span>
        <Tag color="b">{decision.answer}</Tag>
        <span className="font-mono text-[12px] text-muted-foreground">
          {(q.confidence*100).toFixed(0)}% confidence
        </span>
      </div>
      {q.rationale && (
        <div className="rounded-md border-l-2 border-l-[#3172B0] bg-secondary/40 px-3 py-2 text-[12.5px] leading-relaxed text-muted-foreground">
          {q.rationale}
          {q.evidence_columns?.length > 0 && (
            <div className="mt-1 font-mono text-[12px] text-muted-foreground/70">
              evidence: {q.evidence_columns.slice(0,6).join(" · ")}
            </div>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={decision.status !== "agreed" ? "default" : "outline"}
          className="text-xs font-medium"
          onClick={() => setDecision({ status:"agreed", answer:q.answer })}
          style={{ opacity: decision.status === "agreed" ? 0.6 : 1 }}>
          {decision.status === "agreed" ? <><Check size={13} className="mr-1" />Agreed</> : "Agree"}
        </Button>
        {q.options?.length > 0 && (
          <select
            value={decision.status === "corrected" ? decision.answer : ""}
            onChange={e => e.target.value && setDecision({ status:"corrected", answer:e.target.value })}
            className="cursor-pointer rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground">
            <option value="">Choose a different answer…</option>
            {q.options.filter(o => o !== q.answer).map(o => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        )}
      </div>
    </Card>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────
export default function DatasetVerification({
  uploadedData, onUploadData,
  product, users, outcome,
  tenantSlug,
  selectedCohort, onCohortSelect,
  variableMappings, setVariableMappings,
  variableCheckResult, setVariableCheckResult,
  onRunProfiling,
}) {
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);

  // Animate an estimated progress curve while the agent runs. Eases toward 0.92
  // and never reaches 1 until the response lands (set in runCheck's finally).
  useEffect(() => {
    if (!loading) return;
    setProgress(0.05);
    const started = Date.now();
    const EST_MS = 14000; // typical run after parallelization + haiku
    const id = setInterval(() => {
      const t = (Date.now() - started) / EST_MS;
      setProgress(Math.min(0.92, 1 - Math.exp(-2.3 * t)));
    }, 150);
    return () => clearInterval(id);
  }, [loading]);
  const [error, setError] = useState(null);

  const result = variableCheckResult;
  function setResult(data) { setVariableCheckResult(data); }

  const piiScan = uploadedData ? scanForPII(uploadedData.sheets) : null;

  const { data: datasets } = useCollection("datasets");
  const [pickedId, setPickedId] = useState("");
  // Reflect the active dataset in the picker even if local pick state is lost
  // (e.g. StrictMode remount) — match the attached cohort name back to its dataset.
  const selectedDatasetId = pickedId || (uploadedData ? (datasets.find(d => d.name === selectedCohort)?.id ?? "") : "");

  const productDescription = [
    product  && `PRODUCT:\n${product}`,
    users    && `USERS:\n${users}`,
    outcome  && `OUTCOMES OF INTEREST:\n${outcome}`,
  ].filter(Boolean).join("\n\n");

  function statFor(sheetName, column) {
    const sheet = uploadedData?.sheets?.find(s => s.name === sheetName);
    return sheet?.column_stats?.find(s => s.column === column);
  }

  function handleUpload(data) {
    onUploadData(data);
    if (!data) setResult(null);
    setError(null);
    if (data && onCohortSelect) {
      const name = data.filename.replace(/\.(xlsx?|csv)$/i,"").replace(/\s+/g,"_").toLowerCase();
      const rowCount = data.sheets.reduce((a,s) => a+(s.data?.length??0), 0);
      onCohortSelect(name, rowCount);
    }
    if (!data && onCohortSelect) onCohortSelect(selectedCohort, null);
  }

  async function runCheck() {
    if (!uploadedData) return;
    setLoading(true); setError(null);
    try {
      // Simulated agent latency in demo so the "Analysing…" / Re-run state is visible.
      if (isMockEnabled()) await new Promise(r => setTimeout(r, 1100));
      const payload = {
        projectId: tenantSlug,
        product_description: productDescription,
        sheets: uploadedData.sheets.map(s => ({
          name: s.name, headers: s.headers,
          sample: s.data?.slice(0,5) || [],
          column_stats: s.column_stats || [],
        })),
      };
      const data = await apiJson("/agents/variable-check", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(data);
      // Seed decisions — keep any existing decisions, only seed missing ones
      const seed = { ...(variableMappings || {}) };
      for (const m of data.matches) {
        const key = `${m.sheet}::${m.column}`;
        if (!seed[key]) {
          seed[key] = { user_decision:"pending", final_role:m.proposed_role, final_canonical_id:m.proposed_canonical_id };
        }
      }
      setVariableMappings(seed);
      setProgress(1);
    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Auto-run on first upload if no cached result
  const [autoRan, setAutoRan] = useState(false);
  useEffect(() => {
    if (uploadedData && !result && !loading && !error && piiScan?.status === "ok" && !autoRan) {
      setAutoRan(true);
      runCheck();
    }
  }, [uploadedData, result, loading, error, piiScan, autoRan]); // eslint-disable-line react-hooks/exhaustive-deps

  // Selecting a dataset feeds canned cohort columns to the variable-check agent —
  // the demo flow replaces file upload with picking an existing cohort dataset.
  function handleDatasetSelect(id) {
    setPickedId(id);
    if (!id) { handleUpload(null); return; }
    const ds = datasets.find(d => d.id === id);
    const rowCount = parseInt(String(ds?.rows ?? "").replace(/[^\d]/g, ""), 10) || null;
    setResult(null); setError(null); setAutoRan(false);
    onUploadData({ filename: `${ds?.name ?? "cohort"}.csv`, sheets: [{ name: "cohort", headers: cohortHeaders(ds?.cols), data: [], column_stats: [] }] });
    if (onCohortSelect) onCohortSelect(ds?.name ?? "cohort", rowCount);
  }

  // Pre-select the Lucis cohort in demo so 1b lands populated (no upload needed).
  useEffect(() => {
    if (isMockEnabled() && !uploadedData && !pickedId && datasets.length) {
      const lucis = datasets.find(d => /lucis_study_cohort/i.test(d.name)) || datasets.find(d => /lucis/i.test(d.name)) || datasets[0];
      if (lucis) handleDatasetSelect(lucis.id);
    }
  }, [datasets]); // eslint-disable-line react-hooks/exhaustive-deps

  function onDecide(match, patch) {
    const key = `${match.sheet}::${match.column}`;
    setVariableMappings({ ...(variableMappings||{}), [key]: { ...(variableMappings?.[key]||{}), ...patch } });
  }

  function onAgreeAll(groupMatches) {
    const batch = { ...(variableMappings || {}) };
    for (const m of groupMatches) {
      batch[`${m.sheet}::${m.column}`] = {
        user_decision: "agreed",
        final_role: m.proposed_role,
        final_canonical_id: m.proposed_canonical_id,
      };
    }
    setVariableMappings(batch);
  }

  // Master agree-all: accept every agent proposal across all groups in one click.
  function onAgreeAllGlobal() {
    onAgreeAll(result?.matches || []);
  }

  // ── Derived data ────────────────────────────────────────────────────────────
  const matches = result?.matches || [];
  const nTotal = matches.length;
  const nDecided = Object.values(variableMappings || {})
    .filter(d => d.user_decision && d.user_decision !== "pending").length;

  // Needs review: low confidence AND not yet decided
  const needsReview = matches.filter(m => {
    const key = `${m.sheet}::${m.column}`;
    const decided = variableMappings?.[key]?.user_decision;
    return m.confidence < LOW_CONFIDENCE && (!decided || decided === "pending");
  });

  // Group matches — apply GROUP_REMAP so API-returned legacy group IDs
  // land in the correct consolidated accordion.
  const byGroup = {};
  for (const g of GROUPS) byGroup[g.id] = [];
  for (const m of matches) {
    const raw = m.proposed_group || "other";
    const g = GROUP_REMAP[raw] ?? raw;
    if (byGroup[g]) byGroup[g].push(m);
    else byGroup["other"].push(m);
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <div className="text-[13px] font-semibold text-primary">1b · Dataset & data structure</div>
        <div className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
          Select the cohort dataset to profile. The agent maps each column to a canonical outcome or proposes its causal role, grouped by type. Confirm or correct — then run profiling.
        </div>
      </div>

      {/* Upload card */}
      <Card className="gap-4 rounded-xl p-5">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <Database size={15} className="text-muted-foreground" /> Cohort dataset
        </div>
        <div className="text-[12.5px] text-muted-foreground">Attach the cohort dataset the agent should profile. Columns are classified below.</div>
        <select
          value={selectedDatasetId}
          onChange={(e) => handleDatasetSelect(e.target.value)}
          className="w-full rounded-lg border border-border bg-card px-3 py-2.5 text-[13px] text-foreground outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15"
        >
          <option value="">— Select a dataset —</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>{d.name} · {d.rows} rows · {d.cols} cols</option>
          ))}
        </select>

        {uploadedData && (
          <div className="flex flex-col gap-2">
            {selectedCohort && (
              <div className="flex items-center gap-2 rounded-md border border-[#5DCAA5] bg-[#E1F5EE] px-3 py-2 text-[12px] text-primary">
                <Check size={14} className="flex-shrink-0" />
                <span>Cohort matched: <strong>{selectedCohort}</strong></span>
              </div>
            )}
            {piiScan?.status === "ok" && (
              <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-3 py-2 text-[12px] text-muted-foreground">
                <Check size={14} className="flex-shrink-0 text-primary" />
                <span>No PII / PHI column names detected.</span>
              </div>
            )}
            {piiScan?.status === "error" && (
              <div className="rounded-md border border-[#F09595] bg-[#FCEBEB] px-3 py-2.5 text-[12.5px] text-[#C0392B]">
                <strong className="flex items-center gap-1.5"><AlertTriangle size={14} className="flex-shrink-0" /> PII / PHI columns detected — remove before running variable check:</strong>
                <ul className="ml-5 mt-1.5 list-disc p-0">
                  {piiScan.flagged.map((f,i) => (
                    <li key={i}><code className="font-mono">{f.column}</code> ({f.reason}) in <em>{f.sheet}</em></li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {uploadedData && (
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" className="text-xs font-medium" onClick={runCheck}
              disabled={loading || (piiScan?.status === "error")}>
              {loading ? "Analysing…" : result ? "Re-run variable check" : "Run variable check"}
            </Button>
            {result && (
              <span className="text-[12px] text-muted-foreground">
                domain: <strong className="font-mono">{result.clinical_domain || "—"}</strong>
                {" · "}<span className="font-mono">{result.total_columns}</span> columns
                {result.batches > 1 && <> · <span className="font-mono">{result.batches}</span> batches</>}
              </span>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-md border border-[#F09595] bg-[#FCEBEB] px-3 py-2 text-[12.5px] text-[#C0392B]">
            {error}
          </div>
        )}
      </Card>

      {/* Loading — horizontal stepper with estimated progress */}
      {loading && (() => {
        const activeIdx = progress < 0.4 ? 0 : progress < 0.8 ? 1 : 2;
        const totalCols = uploadedData?.sheets?.reduce((a,s) => a+(s.headers?.length||0), 0);
        return (
          <Card className="gap-4 rounded-xl p-5">
            <div className="flex flex-col gap-4">
              {/* node + connector row */}
              <div className="flex items-start">
                {STAGES.map((s, i) => {
                  const done = i < activeIdx;
                  const active = i === activeIdx;
                  const tint = done ? "#047857" : active ? "#3172B0" : "#D8D6CE";
                  return (
                    <React.Fragment key={s.key}>
                      <div className="flex min-w-[96px] flex-col items-center gap-2">
                        <div
                          className="flex h-6 w-6 items-center justify-center rounded-full font-mono text-[12px] font-semibold transition-all"
                          style={{
                            background: done ? "#047857" : active ? "#3172B0" : "#F9F8F5",
                            color: (done || active) ? "#fff" : "#888780",
                            border:`1px solid ${tint}`,
                          }}>
                          {done ? <Check size={13} /> : i + 1}
                        </div>
                        <span className={`text-center text-[12px] leading-snug ${active ? "text-foreground" : done ? "text-muted-foreground" : "text-muted-foreground/60"}`}>
                          {s.label}{active ? "…" : ""}
                        </span>
                      </div>
                      {i < STAGES.length - 1 && (
                        <div className="relative mt-[11px] h-0.5 flex-1 rounded-full bg-secondary/60">
                          <div className="absolute inset-0 rounded-full transition-[width] duration-[400ms]"
                            style={{ width: i < activeIdx ? "100%" : "0%", background:"#047857" }} />
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
              {/* overall progress bar */}
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary/60">
                <div className="h-full rounded-full transition-[width] duration-[250ms] ease-linear"
                  style={{ background:"#3172B0", width:`${Math.round(progress*100)}%` }} />
              </div>
              <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                <Sparkles size={13} className="text-[#3172B0]" />
                Agent reviewing <span className="font-mono">{totalCols}</span> columns…
              </div>
            </div>
          </Card>
        );
      })()}

      {/* Results */}
      {result && !loading && (
        <>
          {/* Summary strip */}
          <Card className="rounded-xl p-5">
            <div className="flex flex-wrap items-center gap-4">
              <div>
                <div className="text-[12px] font-medium text-muted-foreground">Decisions</div>
                <div className="mt-0.5 font-mono text-[22px] font-semibold text-foreground">
                  {nDecided}<span className="text-[13px] text-muted-foreground"> / {nTotal}</span>
                </div>
              </div>
              <div className="h-8 w-px bg-border" />
              {GROUPS.map(g => byGroup[g.id]?.length ? (
                <div key={g.id} className="flex items-center gap-1.5">
                  <Tag color={g.tagColor}>{g.label}</Tag>
                  <span className="font-mono text-[13px] font-semibold text-foreground">{byGroup[g.id].length}</span>
                </div>
              ) : null)}
              <div className="flex-1" />
              <Button size="sm" className="text-xs font-medium" onClick={onAgreeAllGlobal} disabled={nDecided === nTotal}>
                {nDecided === nTotal ? <><Check size={13} className="mr-1" />All agreed</> : `Agree all (${nTotal})`}
              </Button>
            </div>
          </Card>

          {/* Dataset structure questions */}
          {result.dataset_questions?.length > 0 && (
            <Card className="gap-4 rounded-xl p-5">
              <div className="text-[13px] font-semibold text-foreground">
                Dataset structure — agent inferences
              </div>
              <div className="flex flex-col gap-3">
                {result.dataset_questions.map((q,i) => (
                  <DatasetQuestionCard key={q.question_code||i} q={q} />
                ))}
              </div>
            </Card>
          )}

          {/* Needs review — always open */}
          {needsReview.length > 0 && (
            <Card className="gap-0 overflow-hidden rounded-xl border-[#EF9F27] p-0">
              <div className="flex items-center gap-3 bg-[#FAEEDA] px-4 py-3">
                <AlertTriangle size={16} className="flex-shrink-0 text-[#B98900]" />
                <div className="flex-1">
                  <div className="text-[13px] font-semibold text-[#633806]">
                    Needs review — {needsReview.length} column{needsReview.length===1?"":"s"} with low confidence
                  </div>
                  <div className="mt-0.5 text-[12px] text-[#854F0B]">
                    Agent confidence below 70% — review these before bulk-confirming groups
                  </div>
                </div>
              </div>
              <div className="border-t border-border bg-card">
                {needsReview.map(m => {
                  const key = `${m.sheet}::${m.column}`;
                  return (
                    <ColumnRow
                      key={key} match={m} stat={statFor(m.sheet, m.column)}
                      decision={variableMappings?.[key]}
                      onDecide={patch => onDecide(m, patch)}
                    />
                  );
                })}
              </div>
            </Card>
          )}

          {/* Groups */}
          {GROUPS.map(g => (
            <GroupAccordion
              key={g.id}
              group={g}
              matches={byGroup[g.id] || []}
              statFor={statFor}
              variableMappings={variableMappings}
              onDecide={onDecide}
              onAgreeAll={onAgreeAll}
              defaultOpen={false}
            />
          ))}

          {/* Pending count + Back / Run-profiling footer */}
          <div className="mt-1 flex items-center justify-between gap-3 border-t border-border pt-4">
            <div className="flex items-center gap-3">
              {nDecided < nTotal && (
                <span className="text-[12px] italic text-[#854F0B]">
                  {nTotal - nDecided} column{nTotal - nDecided===1?"":"s"} still pending
                </span>
              )}
              <Button className="text-xs font-medium" disabled={nDecided !== nTotal} onClick={() => onRunProfiling?.()}>
                {nDecided === nTotal ? "Run profiling →" : "Confirm all columns first"}
              </Button>
            </div>
          </div>
        </>
      )}

      {!uploadedData && (
        <Card className="rounded-xl p-5">
          <div className="text-[12.5px] leading-relaxed text-muted-foreground">
            Select a dataset above to begin. The agent will identify each column's role
            and group — outcomes matched against <strong>cesl_outcome</strong>,
            engagement / demographics / confounders grouped automatically.
            Light data-quality signals (missingness, value type, range) feed the agent's confidence.
          </div>
        </Card>
      )}

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
