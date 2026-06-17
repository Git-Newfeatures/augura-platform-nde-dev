/**
 * Augura E2 — Simulation Engine
 * ================================
 * Simulation Workspace layout:
 *   - Scenario tabs derived from the LIVE backend results (fetchSimulationResults)
 *   - Left panel: simulation parameters (read-only)
 *   - Right panel: estimator comparison table + Bias vs MSE scatter chart
 *   - Expandable: digital twin concept explanation
 *   - Regulatory verdict + simulation assistant chat
 *
 * Data source:
 *   LIVE — pre-computed bootstrap results served by the backend (Supabase via
 *          fetchSimulationResults). When no live rows are available, the
 *          Results area renders an empty state — no fabricated fallbacks.
 *
 * Parameters pre-populated from E1 output (e1Profile prop).
 */

import { useState, useEffect, useRef } from "react";
import { ArrowLeft, ArrowRight, Lock, FlaskConical } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { fetchCohort, fetchSimulationResults, engagementGroup } from "./workspace/cohortData";
import {
  POWER_THRESHOLD, POWER_MARGINAL_FLOOR,
  ESTIMATORS, ESTIMATOR_FILTER,
} from "./config";

// ── Tokens ────────────────────────────────────────────────────────────────────
// Layout/containers use Tailwind tokens; C is retained for values consumed inside
// the SVG charts (axis strokes, fills, dot colours) and a few dynamic inline styles.
const FONT = "'Geist Variable', 'Geist', system-ui, sans-serif";
const MONO = "'Geist Mono Variable', 'Geist Mono', monospace";
const C = {
  bg: "#F6F4F1", surface: "#ffffff", s2: "#f9f8f5",
  border: "#D8D6CE", border2: "#e8e6df",
  text: "#1C1C1A", muted: "#444441", sub: "#5F5E5A", faint: "#888780",
  green: "#047857", green2: "#1D9E75", greenLt: "#E1F5EE", greenMd: "#5DCAA5",
  blue: "#3172B0", blueLt: "#E6F1FB", orange: "#B98900", orangeLt: "#FFF8E6",
  red: "#C0392B", redLt: "#FEF1F1",
};

// Estimator dot colours for scatter chart
const EST_COLORS = {
  lme: "#0C447C", ols: "#1D9E75", ipw: "#854F0B",
  mediation: "#E24B4A", tmle: "#4B3070", did: "#0F6E56",
};

// Human-readable scenario tab labels (keyed by the backend `scenario` value).
// Unknown scenarios fall back to a title-cased version of their raw key.
const SCENARIO_LABELS = {
  baseline:     "Baseline",
  conservative: "Conservative",
  high_risk:    "Optimized",
  optimised:    "Optimized",
  optimized:    "Optimized",
};
function scenarioLabel(key) {
  if (SCENARIO_LABELS[key]) return SCENARIO_LABELS[key];
  return String(key)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Verdict for each estimator ────────────────────────────────────────────────
// "Essential" = the estimator is needed to understand the mechanism (mediation),
//               regardless of its raw statistical performance.
// "Good/Excellent" = statistical performance thresholds.
function estimatorVerdict(estKey, r) {
  if (!r) return null;
  if (estKey === "mediation") return {
    label: "Essential", color: C.orange, bg: C.orangeLt, border: "#EF9F27",
    tip: "Required to decompose direct vs indirect effects (mechanism analysis)",
  };
  if (r.bias < 0.012 && r.mse < 0.050) return {
    label: "Excellent", color: "#085041", bg: C.greenLt, border: C.greenMd,
    tip: "Lowest bias and MSE among compared estimators",
  };
  if (r.bias < 0.020 && r.mse < 0.060) return {
    label: "Good", color: "#27500A", bg: "#E8F5E9", border: "#66BB6A",
    tip: "Acceptable bias and MSE for regulatory submission",
  };
  if (r.bias < 0.030 && r.mse < 0.080) return {
    label: "Adequate", color: C.blue, bg: C.blueLt, border: "#85B7EB",
    tip: "Acceptable performance; some bias — may require justification",
  };
  return {
    label: "Marginal", color: C.orange, bg: C.orangeLt, border: "#EF9F27",
    tip: "Higher bias or variance — not recommended for primary analysis",
  };
}

// ── Power helpers ─────────────────────────────────────────────────────────────
function powerColor(p) {
  return p >= POWER_THRESHOLD ? C.green2 : p >= POWER_MARGINAL_FLOOR ? "#EF9F27" : "#E24B4A";
}
function powerLabel(p) {
  return p >= POWER_THRESHOLD ? "Above threshold" : p >= POWER_MARGINAL_FLOOR ? "Marginal" : "Below threshold";
}

// ── Regulatory verdict ────────────────────────────────────────────────────────
function verdictFor(power, dropout) {
  const gap = (POWER_THRESHOLD - power).toFixed(1);
  if (power >= POWER_THRESHOLD) return {
    icon: "✅", title: "Meets HAS / DiGA requirements",
    body: `Power of ${power}% exceeds the 80% regulatory minimum (ICH E9 / HAS PECAN). This study design supports submission to HAS or DiGA under current assumptions.`,
    bg: C.greenLt, border: C.greenMd, titleColor: "#085041", bodyColor: "#3a7d5e",
  };
  if (power >= POWER_MARGINAL_FLOOR) return {
    icon: "⚠️", title: "Marginal — additional justification needed",
    body: `Power of ${power}% is ${gap} pp below the 80% threshold. Reviewers may accept with protocol-level justification. Recommended: ${
      dropout != null ? `reduce dropout below ${Math.round(dropout * 100 - 5)}%` : "reduce dropout"
    } or use the Optimized subgroup scenario.`,
    bg: "#FFF8E6", border: "#EF9F27", titleColor: "#633806", bodyColor: "#7A4A10",
  };
  return {
    icon: "❌", title: "Below regulatory threshold",
    body: `Power of ${power}% is ${gap} pp below the minimum required. This design cannot support an HAS/DiGA submission as-is. Options: target a higher-risk subgroup, reduce expected dropout, or extend follow-up.`,
    bg: "#FEF1F1", border: "#E24B4A", titleColor: "#7A2020", bodyColor: "#8B3030",
  };
}

// ── Bias vs MSE Scatter Chart (SVG, no deps) ──────────────────────────────────
function ScatterChart({ rows, estimators, activeKey, onSelect }) {
  const W = 580, H = 200;
  const pad = { top: 14, right: 20, bottom: 38, left: 50 };
  const iW = W - pad.left - pad.right;
  const iH = H - pad.top - pad.bottom;

  const biases = estimators.map(e => rows[e.key]?.bias ?? 0).filter(v => v > 0);
  const mses   = estimators.map(e => rows[e.key]?.mse  ?? 0).filter(v => v > 0);
  const maxB   = biases.length ? Math.max(...biases) * 1.5 + 0.005 : 0.05;
  const maxM   = mses.length   ? Math.max(...mses)   * 1.5 + 0.005 : 0.08;

  function px(b) { return pad.left + (b / maxB) * iW; }
  function py(m) { return pad.top  + iH - (m / maxM) * iH; }

  // Nice tick values
  function niceSteps(max, count) {
    const step = max / count;
    const mag  = Math.pow(10, Math.floor(Math.log10(step)));
    const nice = [1, 2, 5, 10].find(f => f * mag >= step) * mag;
    const ticks = [];
    for (let v = 0; v <= max * 1.05; v = +(v + nice).toFixed(10)) ticks.push(+v.toFixed(4));
    return ticks;
  }
  const xTicks = niceSteps(maxB, 4);
  const yTicks = niceSteps(maxM, 4);

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible" }}>
        {/* Gridlines */}
        {yTicks.map(v => (
          <line key={`gy${v}`} x1={pad.left} x2={pad.left + iW} y1={py(v)} y2={py(v)}
            stroke="#e8e6df" strokeWidth={1} strokeDasharray={v === 0 ? "none" : "3,3"} />
        ))}
        {xTicks.map(v => (
          <line key={`gx${v}`} x1={px(v)} x2={px(v)} y1={pad.top} y2={pad.top + iH}
            stroke="#e8e6df" strokeWidth={1} strokeDasharray={v === 0 ? "none" : "3,3"} />
        ))}

        {/* Axes */}
        <line x1={pad.left} x2={pad.left + iW} y1={pad.top + iH} y2={pad.top + iH}
          stroke={C.border} strokeWidth={1} />
        <line x1={pad.left} x2={pad.left} y1={pad.top} y2={pad.top + iH}
          stroke={C.border} strokeWidth={1} />

        {/* X ticks + labels */}
        {xTicks.map(v => (
          <g key={`xt${v}`}>
            <line x1={px(v)} x2={px(v)} y1={pad.top + iH} y2={pad.top + iH + 4}
              stroke={C.border} strokeWidth={1} />
            <text x={px(v)} y={pad.top + iH + 14} textAnchor="middle"
              fontSize={9} fill={C.faint} fontFamily={MONO}>
              {v.toFixed(3)}
            </text>
          </g>
        ))}

        {/* Y ticks + labels */}
        {yTicks.map(v => (
          <g key={`yt${v}`}>
            <line x1={pad.left - 4} x2={pad.left} y1={py(v)} y2={py(v)}
              stroke={C.border} strokeWidth={1} />
            <text x={pad.left - 8} y={py(v) + 3.5} textAnchor="end"
              fontSize={9} fill={C.faint} fontFamily={MONO}>
              {v.toFixed(3)}
            </text>
          </g>
        ))}

        {/* Axis labels */}
        <text x={pad.left + iW / 2} y={H - 2} textAnchor="middle"
          fontSize={10} fill={C.sub} fontFamily={FONT}>Bias</text>
        <text x={11} y={pad.top + iH / 2} textAnchor="middle"
          fontSize={10} fill={C.sub} fontFamily={FONT}
          transform={`rotate(-90, 11, ${pad.top + iH / 2})`}>MSE</text>

        {/* "Lower-left is better" annotation */}
        <text x={pad.left + 6} y={pad.top + iH - 5} fontSize={8} fill={C.faint} fontFamily={FONT}>
          ← lower-left = better
        </text>

        {/* Data points */}
        {estimators.map(e => {
          const r = rows[e.key];
          if (!r) return null;
          const isActive = e.key === activeKey;
          const r2 = isActive ? 7 : 5;
          return (
            <g key={e.key} onClick={() => onSelect(e.key)} style={{ cursor: "pointer" }}>
              {isActive && (
                <>
                  <circle cx={px(r.bias)} cy={py(r.mse)} r={r2 + 5}
                    fill={EST_COLORS[e.key] || C.faint} opacity={0.12} />
                  <text x={px(r.bias) + r2 + 7} y={py(r.mse) - r2 - 4}
                    fontSize={8} fill={C.faint} fontFamily={FONT}
                    style={{ pointerEvents: "none" }}>
                    95% CI zone
                  </text>
                </>
              )}
              <circle cx={px(r.bias)} cy={py(r.mse)} r={r2}
                fill={EST_COLORS[e.key] || C.faint}
                stroke={isActive ? "#fff" : "transparent"} strokeWidth={1.5}
                opacity={isActive ? 1 : 0.75} />
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="mt-1.5 flex flex-wrap gap-3.5" style={{ paddingLeft: pad.left }}>
        {estimators.map(e => {
          const isActive = e.key === activeKey;
          return (
            <div key={e.key} onClick={() => onSelect(e.key)}
              className={`flex cursor-pointer items-center gap-1.5 ${isActive ? "opacity-100" : "opacity-60"}`}>
              <div className="h-2.5 w-2.5 rounded-full"
                style={{ background: EST_COLORS[e.key] || C.faint }} />
              <span className={`text-[11px] text-muted-foreground ${isActive ? "font-semibold" : "font-normal"}`}>
                {e.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Outcome label map (mirrors Outcome Selection in E1) ───────────────────────
const OUTCOME_LABELS = {
  hba1c: "HbA1c change · 12 months",
  ldl:   "LDL cholesterol · 12 months",
  crp:   "hs-CRP (inflammation) · 12 months",
};

// ── Study-type label ──────────────────────────────────────────────────────────
const STUDY_TYPE_LABELS = {
  retro: "Retrospective observational",
  prosp: "Prospective / RCT",
};

// ── Interpretability stars ────────────────────────────────────────────────────
function stars(n) { return "★".repeat(n) + "☆".repeat(5 - n); }

// ── Empty state ────────────────────────────────────────────────────────────────
// Shown whenever the live backend (fetchSimulationResults) returns no rows.
// There are no fabricated fallback numbers — the UI stays honest about the
// absence of validated results rather than rendering demo data.
function EmptyState({ icon, title, body }) {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 rounded-[10px] border-dashed border-border bg-muted/40 px-6 py-12 text-center">
      <div className="flex items-center gap-2 text-[14px] font-semibold text-foreground">
        {icon ?? <FlaskConical size={16} style={{ color: C.faint }} />} {title}
      </div>
      <div className="max-w-md text-[12px] leading-relaxed text-muted-foreground">
        {body}
      </div>
    </Card>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function SimulationEngine({
  onBack, onNext, e1Profile, studyType,
  selectedEstimators, selectedCohort = "",
  selectedOutcome,   // key from E1 Outcome Selection: "hba1c" | "ldl" | "crp"
  uploadedRowCount,  // row count from uploaded Excel file — highest-priority N override
  partnerLabel = 'Partner',
}) {
  // ── Cohort — live from the validation dataset (fetchCohort) only ──────────────
  // No COHORT_N fallback: when the backend returns no cohort, liveCohort stays
  // null and the UI guards for the missing N rather than fabricating one.
  const [liveCohort, setLiveCohort] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchCohort(selectedCohort).then(({ members, biomarkers }) => {
      if (!alive || !members.length) return;
      const total  = members.length;
      const highN  = members.filter(m => engagementGroup(m) === "high").length;
      const treatP = Math.round((highN / total) * 1000) / 1000;

      // Observed ATT derived from the live biomarkers (null when unavailable).
      let att = null;
      if (biomarkers.length) {
        const groupMap = Object.fromEntries(members.map(m => [m.member_id, engagementGroup(m)]));
        const t0map    = Object.fromEntries(
          biomarkers.filter(b => b.timepoint_months === 0).map(b => [b.member_id, b.hba1c_pct])
        );
        const t12rows  = biomarkers.filter(b => b.timepoint_months === 12 && b.hba1c_pct != null);
        const deltas   = t12rows.map(b => ({
          delta: b.hba1c_pct - (t0map[b.member_id] ?? b.hba1c_pct),
          group: groupMap[b.member_id],
        }));
        const highD = deltas.filter(d => d.group === "high").map(d => d.delta);
        const restD = deltas.filter(d => d.group !== "high").map(d => d.delta);
        if (highD.length && restD.length) {
          const mean = arr => arr.reduce((s, v) => s + v, 0) / arr.length;
          att = Math.round((mean(highD) - mean(restD)) * 1000) / 1000;
        }
      }
      setLiveCohort({ total, highN, treatP, att });
    });
    return () => { alive = false; };
  }, [selectedCohort]);

  // Live N only — may be null until the cohort (or an uploaded file) is available.
  const cohortN = uploadedRowCount ?? liveCohort?.total ?? null;

  // Priority: selectedOutcome key (from E1 Outcome Selection)
  //   > e1Profile.primary_outcome_label (from E1 agent)
  //   > assume HbA1c (safe default)
  const isHbA1c = selectedOutcome
    ? selectedOutcome === "hba1c"
    : !e1Profile?.primary_outcome_label ||
      /hba1c|hb\s*a1c|glycat|a1c/i.test(e1Profile.primary_outcome_label);

  const outcomeLabel = OUTCOME_LABELS[selectedOutcome]
    ?? e1Profile?.primary_outcome_label
    ?? "HbA1c change · 12 months";

  // ── Estimator filtering ───────────────────────────────────────────────────────
  const allowedKeys        = ESTIMATOR_FILTER[studyType] || ESTIMATOR_FILTER.retro;
  const userKeys           = selectedEstimators?.length ? selectedEstimators : allowedKeys;
  const filteredEstimators = ESTIMATORS.filter(
    e => allowedKeys.includes(e.key) && userKeys.includes(e.key)
  );
  // Fallback: if nothing selected, show all allowed
  const compEstimators = filteredEstimators.length
    ? filteredEstimators
    : ESTIMATORS.filter(e => allowedKeys.includes(e.key));

  // ── Scenario parameters (mirrored from the active live scenario, if provided) ─
  // These come from the backend rows when present; they are null otherwise and
  // simply render as "—" rather than defaulting to fabricated demo values.
  const [dropout,       setDropout] = useState(null);
  const [effectAssumed, setEffect]  = useState(null);

  const defaultEst = compEstimators.find(e => e.recommended)?.key
    ?? compEstimators[0]?.key ?? "lme";
  const [estimator,     setEstimator] = useState(defaultEst);

  // ── Results (live, read-model) ────────────────────────────────────────────────
  const [result,       setResult]       = useState(null);
  const [activeScenario, setActiveScenario] = useState(null);
  const [liveData,     setLiveData]     = useState(null);

  // ── Locking gate ─────────────────────────────────────────────────────────────
  const [lockedEstimator, setLockedEstimator] = useState(null);
  const [showLockWarning, setShowLockWarning] = useState(false);

  // ── UI toggles ────────────────────────────────────────────────────────────────
  const [showConcept,    setShowConcept]    = useState(false);
  const [showChat,       setShowChat]       = useState(false);

  // ── Chat ──────────────────────────────────────────────────────────────────────
  const chatRef = useRef(null);
  const [msgs, setMsgs]           = useState([{
    role: "assistant",
    text: "I'm the Augura simulation assistant. Ask me about power, estimator choice, dropout sensitivity, or regulatory thresholds.",
  }]);
  const [inp,         setInp]         = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // ── Backend: live bootstrap results (read-model, scopé tenant) ────────────────
  useEffect(() => {
    let alive = true;
    fetchSimulationResults(selectedCohort).then((rows) => {
      if (alive) setLiveData(Array.isArray(rows) ? rows : []);
    });
    return () => { alive = false; };
  }, [selectedCohort]);

  // Distinct scenarios present in the live rows, in first-seen order.
  const scenarioKeys = liveData
    ? [...new Set(liveData.map(r => r.scenario).filter(Boolean))]
    : [];
  const hasLiveResults = scenarioKeys.length > 0;

  // Load the first live scenario once data arrives (or re-sync when it changes).
  useEffect(() => {
    if (!hasLiveResults) {
      setResult(null);
      setActiveScenario(null);
      return;
    }
    const next = scenarioKeys.includes(activeScenario) ? activeScenario : scenarioKeys[0];
    loadScenario(next);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveData]);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [msgs]);

  // ── Load a live scenario (from fetchSimulationResults rows) ───────────────────
  // Builds the per-estimator result map straight from the backend contract
  // (SimulationResultOut: scenario · estimator · power · effect_size · ci_*).
  // Fields the read-model does not carry (bias/variance/mse) are left null and
  // render as "—" — never reconstructed from removed demo coefficients.
  function loadScenario(key) {
    setActiveScenario(key);

    const rows = liveData?.filter(r => r.scenario === key) ?? [];
    if (!rows.length) {
      setResult(null);
      setDropout(null);
      setEffect(null);
      return;
    }

    // Scenario-level params come from the rows when present (read-model may omit them).
    const refRow = rows.find(r => r.estimator === "lme") ?? rows[0];
    setDropout(refRow?.dropout ?? null);
    setEffect(refRow?.effect_size != null ? Math.abs(refRow.effect_size) : null);

    const all  = {};
    for (const est of ESTIMATORS) {
      const row = rows.find(r => r.estimator === est.key);
      all[est.key] = row
        ? {
            power:    row.power ?? null,
            bias:     row.bias ?? null,
            variance: row.variance ?? null,
            mse:      row.mse ?? null,
            effect:   row.effect_size ?? null,
            ci:       [row.ci_lower ?? null, row.ci_upper ?? null],
          }
        : null;
    }
    setResult({
      all, timestamp: new Date(),
      source: "live",
      // The bootstrap's own N when the read-model reports it; otherwise null and
      // the display falls back to the live cohort N (never a hardcoded value).
      bootstrapN: refRow?.n_total ?? null,
      bootstrapNTreatment: refRow?.n_treatment ?? null,
    });
  }

  // ── Chat ──────────────────────────────────────────────────────────────────────
  async function sendChat() {
    const q = inp.trim();
    if (!q || chatLoading) return;
    setInp("");
    setMsgs(m => [...m, { role: "user", text: q }]);
    setChatLoading(true);
    const cur2 = result?.all?.[estimator];
    try {
      const res = await window.fetch("/api/anthropic", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-haiku-4-5-20251001", max_tokens: 200,
          system: `Augura E2 simulation assistant. ${partnerLabel} (N=${cohortN ?? "unknown"}).
Current: ${estimator} estimator${dropout != null ? `, ${Math.round(dropout * 100)}% dropout` : ""}${effectAssumed != null ? `, effect assumed ${effectAssumed}` : ""}.
Result: power ${cur2?.power ?? "n/a"}%, MSE ${cur2?.mse != null ? cur2.mse.toFixed(4) : "n/a"}, bias ${cur2?.bias != null ? cur2.bias.toFixed(4) : "n/a"}.
Source: live backend results. Regulatory target: HAS/DiGA (80% power threshold).
Answer in under 90 words. Be direct. Use plain language (no jargon without explanation).`,
          messages: [{ role: "user", content: q }],
        }),
      });
      const d    = await res.json();
      const text = d.content?.filter(b => b.type === "text").map(b => b.text).join("") || "Engine unavailable.";
      setMsgs(m => [...m, { role: "assistant", text }]);
    } catch {
      setMsgs(m => [...m, { role: "assistant", text: "Chat unavailable locally — works on deployed Vercel." }]);
    }
    setChatLoading(false);
  }

  // ── Derived ───────────────────────────────────────────────────────────────────
  const cur     = result?.all?.[estimator];
  const allRows = result?.all ?? {};
  const pcol    = cur?.power != null ? powerColor(cur.power) : C.faint;

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col">

      {/* ── HEADER ── */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="mb-0.5 text-[20px] font-bold text-foreground">
            Simulation workspace
          </div>
          <div className="text-[12px] text-muted-foreground">
            Digital twin studies · Estimator comparison
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="rounded-full border-border bg-muted/40 px-2.5 py-[3px] text-[11px] font-medium text-muted-foreground">
            {partnerLabel} dataset
          </Badge>
          <Badge variant="outline" className="rounded-full border-border bg-muted/40 px-2.5 py-[3px] text-[11px] font-medium text-muted-foreground">
            {compEstimators.length} estimator{compEstimators.length !== 1 ? "s" : ""} selected
          </Badge>
          {result?.source === "live" && (
            <Badge variant="outline" className="rounded-full border-secondary bg-secondary px-2 py-0.5 text-[10px] font-medium text-[#085041]">
              ● live
            </Badge>
          )}
        </div>
      </div>

      {/* ── E1 CONTEXT BANNER ── */}
      {/* Shows what E1 decided so you can immediately see what's driving E2 */}
      <div className={`mb-3.5 flex flex-wrap items-center gap-1.5 rounded-lg border-[0.5px] px-3 py-2 ${
        e1Profile ? "border-[#97C459] bg-[#EAF3DE]" : "border-border bg-muted/40"}`}>
        <span className={`mr-1 font-mono text-[10px] font-bold uppercase tracking-[0.06em] ${
          e1Profile ? "text-[#27500A]" : "text-muted-foreground/60"}`}>
          From E1
        </span>

        {/* Outcome */}
        <span className={`rounded-full border-[0.5px] px-[9px] py-0.5 text-[11px] ${
          e1Profile ? "border-[#97C459] bg-card text-[#085041]" : "border-border bg-border text-muted-foreground/60"}`}
          title="Outcome selected in E1 → Outcome Selection">
          📊 {outcomeLabel}
        </span>

        {/* Study type */}
        <span className={`rounded-full border-[0.5px] px-[9px] py-0.5 text-[11px] ${
          e1Profile ? "border-[#85B7EB] bg-card text-[#3172B0]" : "border-border bg-border text-muted-foreground/60"}`}
          title="Study type selected in E1 → Study Type">
          🔬 {STUDY_TYPE_LABELS[studyType] ?? studyType ?? "Retrospective"}
          {studyType === "prosp" && (
            <span className="ml-1 text-[9px] text-[#B98900]">
              · IPW &amp; DID excluded
            </span>
          )}
        </span>

        {/* Estimators */}
        {compEstimators.map(e => (
          <span key={e.key} className={`rounded-full border-[0.5px] px-[9px] py-0.5 text-[11px] ${
            e1Profile ? "border-border bg-card text-foreground" : "border-border bg-border text-muted-foreground/60"}`}
            title={`${e.label} — selected in E1 → Study Design. ${e.tooltip ?? ""}`}>
            {e.short}
          </span>
        ))}

        {!e1Profile && (
          <span className="ml-1 text-[10px] italic text-muted-foreground/60">
            Complete E1 profiling for personalised parameters
          </span>
        )}
      </div>

      {/* ── EMPTY STATE — no live results ── */}
      {/* When the backend (fetchSimulationResults) returns no rows, we render an
          honest empty state instead of fabricated demo scenarios/numbers. */}
      {!hasLiveResults ? (
        <EmptyState
          title="No validated simulation results yet"
          body={`Once a bootstrap run has been validated for the ${partnerLabel} cohort, its scenarios and estimator comparison will appear here. Nothing is shown until live results are available.`}
        />
      ) : (
      <>

      {/* ── SCENARIO TABS — derived from live backend results ── */}
      <div className="mb-2 flex flex-wrap gap-2">
        {scenarioKeys.map((key) => {
          const isSel = activeScenario === key;
          return (
            <button key={key} onClick={() => loadScenario(key)}
              className={`rounded-full border-[1.5px] px-[18px] py-[7px] text-[12px] transition-all ${
                isSel
                  ? "border-foreground bg-foreground font-semibold text-white"
                  : "border-border bg-card font-normal text-muted-foreground"}`}>
              {scenarioLabel(key)}
            </button>
          );
        })}
      </div>

      {/* Scenario parameter summary — only the values the read-model actually carries */}
      <Card className="mb-3.5 gap-0 rounded-[10px] border-border bg-muted/40 p-[10px_14px]">
        <div className="flex flex-wrap gap-2">
          {[
            { label: "Sample size (N)", value: cohortN != null ? cohortN.toLocaleString() : "—" },
            { label: "Assumed dropout", value: dropout != null ? `${Math.round(dropout * 100)}%` : "—" },
            { label: "Assumed effect (ATT)", value: effectAssumed != null ? `−${effectAssumed} HbA1c units` : "—" },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-[7px] border-[0.5px] border-border bg-card p-[5px_10px]">
              <div className="mb-0.5 font-mono text-[9px] uppercase tracking-[0.06em] text-muted-foreground/60">{label}</div>
              <div className="font-mono text-[12px] font-semibold text-foreground">{value}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── CONCEPT EXPLANATION (expandable) ── */}
      <Card className="mb-3.5 gap-0 overflow-hidden rounded-[10px] border-border bg-muted/40 p-0">
        <button
          onClick={() => setShowConcept(v => !v)}
          className="flex w-full items-center justify-between border-none bg-transparent p-[10px_14px]">
          <span className="text-[12px] font-medium text-muted-foreground">
            💡 What is a digital twin study? What do these numbers mean?
          </span>
          <span className="text-[11px] text-muted-foreground/60">{showConcept ? "▲" : "▼"}</span>
        </button>
        {showConcept && (
          <div className="grid grid-cols-3 gap-2.5 p-[0_14px_14px]">
            {[
              {
                icon: "🧬",
                title: "Digital twin",
                body: `We fit statistical models to the real ${partnerLabel} dataset${cohortN != null ? ` (N=${cohortN.toLocaleString()} patients)` : ""}. These capture the distribution of age, BMI, HbA1c, and treatment response. We then generate virtual patients who statistically mirror your real cohort — this is the "digital twin". It lets us run experiments we can't run on real patients.`,
              },
              {
                icon: "🔁",
                title: "Repeated studies",
                body: `We run the full study many times on the digital twin, each time drawing a random sample. Each "study" runs every estimator and records whether it detected the real effect at p<0.05. The power % = how often the estimator succeeded. This is more reliable than a formula because it uses your actual data distribution.`,
              },
              {
                icon: "📊",
                title: "Bias, Variance, MSE",
                body: `Bias = how far the estimator is from the true effect on average across all runs. Variance = how much results fluctuate. MSE (mean squared error) = bias² + variance — the single best summary of estimator quality. Lower = better. The scatter chart shows both at a glance: lower-left estimators are more accurate and consistent.`,
              },
            ].map(({ icon, title, body }) => (
              <div key={title} className="rounded-lg border-[0.5px] border-border bg-card p-[10px_12px]">
                <div className="mb-1.5 text-[12px] font-bold text-foreground">
                  {icon} {title}
                </div>
                <div className="text-[11px] leading-relaxed text-muted-foreground">{body}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ── TWO-COLUMN LAYOUT ── */}
      <div className="grid grid-cols-1 items-start gap-3.5 lg:grid-cols-[310px_1fr]">

        {/* ════════════ LEFT: Simulation parameters ════════════ */}
        <Card className="gap-0 rounded-[10px] border-border bg-card p-[14px_16px]">

          <div className="mb-3 text-[12px] font-bold text-foreground">
            Simulation parameters
          </div>

          {/* Parameters list — live values only; unknowns render as "—" */}
          {[
            {
              label: "Source cohort",
              value: (result?.bootstrapN ?? cohortN) != null
                ? `Prediabetes N=${(result?.bootstrapN ?? cohortN).toLocaleString()}`
                : "—",
              tip: result?.bootstrapN && result.bootstrapN !== cohortN
                ? `Bootstrap ran on N=${result.bootstrapN} (subgroup filter applied)${cohortN != null ? `. Full cohort is N=${cohortN}.` : "."}`
                : `Real-world ${partnerLabel} validation dataset`,
            },
            {
              label: "Follow-up window",
              value: "12 months",
              tip: "Baseline (T0) → 12-month (T12) HbA1c measurement",
            },
            {
              label: `Assumed ${selectedOutcome === "ldl" ? "LDL" : selectedOutcome === "crp" ? "CRP" : "HbA1c"} effect`,
              value: effectAssumed != null ? `-${effectAssumed.toFixed(2)} units` : "—",
              tip: `Expected ATT — average ${outcomeLabel} reduction for High-engagers vs Rest`,
            },
            {
              label: "Dropout rate",
              value: dropout != null ? `${Math.round(dropout * 100)}%` : "—",
              orange: dropout != null && dropout > 0.25,
              tip: "Patients lost to follow-up before T12 — highlighted in orange above 25%",
            },
          ].map(({ label, value, orange, tip }) => (
            <div key={label}
              className="flex items-center justify-between border-b-[0.5px] border-border py-[7px]"
              title={tip}>
              <span className="text-[11px] text-muted-foreground">{label}</span>
              <span className={`font-mono text-[12px] font-semibold ${orange ? "text-[#B98900]" : "text-foreground"}`}>{value}</span>
            </div>
          ))}

          {/* Selected estimator box */}
          <div className={`mt-3.5 rounded-lg border-[0.5px] p-[10px_12px] ${
            lockedEstimator ? "border-secondary bg-secondary" : "border-border bg-muted/40"}`}>
            <div className={`mb-1 font-mono text-[10px] uppercase tracking-[0.05em] ${
              lockedEstimator ? "text-[#3a7d5e]" : "text-muted-foreground/60"}`}>
              Selected estimator
            </div>
            <div className={`text-[15px] font-bold ${lockedEstimator ? "text-[#085041]" : "text-foreground"}`}>
              {ESTIMATORS.find(e => e.key === (lockedEstimator || estimator))?.short ?? "—"}
            </div>
            <div className={`mt-0.5 text-[10px] ${lockedEstimator ? "text-[#3a7d5e]" : "text-muted-foreground/60"}`}>
              {lockedEstimator
                ? "🔒 Locked for regulatory submission"
                : "Click a row in the table to select."}
            </div>
            {lockedEstimator && (
              <Button variant="outline" size="xs"
                onClick={() => { setLockedEstimator(null); setShowLockWarning(false); }}
                className="mt-1.5 h-auto rounded-md border-border bg-transparent px-[9px] py-0.5 text-[10px] font-normal text-muted-foreground/60">
                Unlock
              </Button>
            )}
          </div>

          {showLockWarning && (
            <div className="mt-2 rounded-[7px] border-[0.5px] border-[#EF9F27] bg-[#FFF8E6] p-[7px_9px] text-[10px] text-[#633806]">
              Estimator is locked. Click <strong>Unlock</strong> to change.
            </div>
          )}

          {/* Power summary */}
          {cur?.power != null && (
            <div className="mt-3 border-t-[0.5px] border-dashed border-border pt-2.5">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="font-mono text-[10px] uppercase tracking-[0.05em] text-muted-foreground/60">
                  Statistical power
                  {estimator && (
                    <span className="ml-1.5 font-bold"
                      style={{ color: EST_COLORS[estimator] ?? C.faint }}>
                      — {ESTIMATORS.find(e => e.key === estimator)?.short}
                    </span>
                  )}
                </span>
                <span className="text-[10px] font-semibold" style={{ color: pcol }}>
                  {powerLabel(cur.power)}
                </span>
              </div>
              <div className="relative mb-1.5 h-1.5 overflow-hidden rounded-[3px] bg-muted">
                <div className="h-full rounded-[3px] transition-[width] duration-500 ease-out"
                  style={{ width: `${cur.power}%`, background: pcol }} />
                <div className="absolute bottom-0 top-0 w-[1.5px]"
                  style={{ left: "80%", background: "rgba(0,0,0,0.3)" }} />
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-[26px] font-bold leading-none" style={{ color: pcol }}>
                  {cur.power}%
                </span>
                <span className="text-right font-mono text-[9px] text-muted-foreground/60">
                  HAS/DiGA<br/>threshold 80%
                </span>
              </div>
              {/* Effect + CI */}
              <div className="mt-2 flex gap-2">
                <div className="flex-1 rounded-md bg-muted/40 p-[5px_8px]">
                  <div className="font-mono text-[9px] uppercase text-muted-foreground/60">Effect</div>
                  <div className="mt-px font-mono text-[11px] font-semibold text-foreground">
                    {cur.effect != null ? `${cur.effect} HbA1c` : "—"}
                  </div>
                </div>
                <div className="flex-1 rounded-md bg-muted/40 p-[5px_8px]">
                  <div className="font-mono text-[9px] uppercase text-muted-foreground/60">95% CI</div>
                  <div className="mt-px font-mono text-[11px] font-semibold text-foreground">
                    {cur.ci?.[0] != null && cur.ci?.[1] != null ? `[${cur.ci[0]}, ${cur.ci[1]}]` : "—"}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>

        {/* ════════════ RIGHT: Table + Chart ════════════ */}
        <div className="flex flex-col gap-3">

          {/* ── Estimator comparison table ── */}
          <Card className="gap-0 rounded-[10px] border-border bg-card p-[14px_16px]">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[13px] font-semibold text-foreground">
                Estimator comparison
              </div>
              <span className="text-[10.5px] italic text-muted-foreground/60">
                Click row to select
              </span>
            </div>

            {/* Table header */}
            <div className="grid border-b border-border p-[4px_10px_6px]"
              style={{ gridTemplateColumns: "1fr 72px 72px 72px 90px" }}>
              {["Estimator", "Bias", "Variance", "MSE", "Verdict"].map(h => (
                <span key={h} className={`font-mono text-[9.5px] uppercase tracking-[0.07em] text-muted-foreground/60 ${
                  h === "Estimator" ? "text-left" : "text-center"}`}>
                  {h}
                </span>
              ))}
            </div>

            {/* Rows */}
            <div className="mt-1">
              {compEstimators.map(e => {
                const r    = allRows[e.key];
                const isSel = e.key === estimator;
                const verd  = estimatorVerdict(e.key, r);
                return (
                  <div key={e.key}
                    onClick={() => {
                      if (lockedEstimator) { setShowLockWarning(true); return; }
                      setEstimator(e.key);
                      setShowLockWarning(false);
                    }}
                    title={verd?.tip ?? ""}
                    className={`mb-0.5 grid cursor-pointer rounded-lg border-[0.5px] p-[9px_10px] transition-all ${
                      isSel ? "border-[#85B7EB] bg-[#F3F6FF]" : "border-transparent bg-transparent"}`}
                    style={{ gridTemplateColumns: "1fr 72px 72px 72px 90px" }}>

                    {/* Estimator name */}
                    <div className="flex items-center gap-2">
                      <div className="flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded-full border-[1.5px]"
                        style={{
                          borderColor: isSel ? (EST_COLORS[e.key] || C.green) : C.border,
                          background: isSel ? (EST_COLORS[e.key] || C.green) : "transparent" }}>
                        {isSel && <div className="h-[5px] w-[5px] rounded-full bg-white" />}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-[12px] text-foreground ${isSel ? "font-semibold" : "font-normal"}`}>
                          {e.label}
                        </span>
                        {e.recommended && (
                          <span className="rounded-lg bg-[#EAF3DE] px-[5px] py-px text-[8px] font-semibold text-[#27500A]">REC</span>
                        )}
                        {/* ⓘ hover tooltip — plain-English explanation from config.js */}
                        <span
                          title={[
                            e.tooltip,
                            `Interpretability: ${stars(e.interpretability ?? 3)} (${e.interpretability ?? "?"}/5)`,
                            e.bootstrapPending ? "⏳ Bootstrap pending — analytical approximation only" : "✓ Bootstrap validated",
                          ].join("\n\n")}
                          className="flex-shrink-0 cursor-help select-none text-[11px] leading-none text-muted-foreground/60">
                          ⓘ
                        </span>
                      </div>
                    </div>

                    {/* Bias */}
                    <span className="self-center text-center font-mono text-[12px] text-foreground">
                      {r?.bias != null ? r.bias.toFixed(4) : "—"}
                    </span>

                    {/* Variance */}
                    <span className="self-center text-center font-mono text-[12px] text-foreground">
                      {r?.variance != null ? r.variance.toFixed(4) : "—"}
                    </span>

                    {/* MSE */}
                    <span className="self-center text-center font-mono text-[12px] text-foreground">
                      {r?.mse != null ? r.mse.toFixed(4) : "—"}
                    </span>

                    {/* Verdict */}
                    <div className="self-center text-center">
                      {verd ? (
                        <span className="whitespace-nowrap rounded-xl border-[0.5px] px-[9px] py-0.5 text-[10.5px] font-semibold"
                          style={{ background: verd.bg, color: verd.color, borderColor: verd.border }}>
                          {verd.label}
                        </span>
                      ) : <span className="text-muted-foreground/60">—</span>}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Footer note */}
            <div className="mt-2 border-t-[0.5px] border-border pt-2 text-[10px] italic text-muted-foreground/60">
              Pre-computed parametric bootstrap — validated results served from the backend
              {result?.source === "live" && " · ● live data"}
            </div>
          </Card>

          {/* ── Bias vs MSE scatter chart ── */}
          <Card className="gap-0 rounded-[10px] border-border bg-card p-[14px_16px]">
            <div className="mb-2">
              <div className="text-[13px] font-semibold text-foreground">
                Bias vs MSE — Estimator comparison
              </div>
              <div className="mt-0.5 text-[11px] text-muted-foreground/60">
                Lower-left = better performance. Click a point to select the estimator.
              </div>
            </div>
            <ScatterChart
              rows={allRows}
              estimators={compEstimators}
              activeKey={estimator}
              onSelect={key => {
                if (!lockedEstimator) setEstimator(key);
                else setShowLockWarning(true);
              }}
            />
          </Card>

        </div>
      </div>

      {/* ── REGULATORY VERDICT ── */}
      {cur?.power != null && (() => {
        const v = verdictFor(cur.power, dropout);
        return (
          <div className="mt-3.5 rounded-[10px] border-[0.5px] p-[12px_16px]"
            style={{ background: v.bg, borderColor: v.border }}>
            <div className="mb-1 text-[14px] font-bold" style={{ color: v.titleColor }}>
              {v.icon} {v.title}
            </div>
            <div className="text-[12px] leading-relaxed" style={{ color: v.bodyColor }}>{v.body}</div>
          </div>
        );
      })()}

      {/* ── NON-HbA1c WARNING ── */}
      {!isHbA1c && (
        <div className="mt-2.5 rounded-[10px] border-[0.5px] border-[#EF9F27] bg-[#FFF8E6] p-[10px_14px]">
          <div className="mb-0.5 text-[11px] font-bold text-[#633806]">
            ⚠ Simulation calibrated for HbA1c only
          </div>
          <div className="text-[10.5px] leading-snug text-[#7A4A10]">
            The σ, effect size, and power estimates are validated against the {partnerLabel} dataset.
            Results for other outcomes are <em>exploratory</em> until their effect-size and noise
            parameters are validated.
          </div>
        </div>
      )}

      </>
      )}

      {/* ── SIMULATION ASSISTANT CHAT (collapsible) — always available ── */}
      <Card className="mt-3 gap-0 overflow-hidden rounded-[10px] border-border bg-card p-0">
        <button onClick={() => setShowChat(v => !v)}
          className="flex w-full items-center justify-between border-none bg-transparent p-[11px_14px]">
          <div className="flex items-center gap-2.5">
            <span className="text-[12px] font-semibold text-foreground">
              Simulation assistant
            </span>
            <span className="text-[10.5px] text-muted-foreground/60">
              Ask about power, estimators, or regulatory thresholds
            </span>
          </div>
          <span className="text-[11px] text-muted-foreground/60">{showChat ? "▲" : "▼"}</span>
        </button>
        {showChat && (
          <div className="p-[0_14px_14px]">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {["Why TMLE?", "What N gives 90% power?", "How does dropout affect bias?",
                "Is 87% enough for HAS?"].map(q => (
                <button key={q} onClick={() => setInp(q)}
                  className="rounded-full border-[0.5px] border-border bg-muted/40 px-[9px] py-[3px] text-[10.5px] text-muted-foreground">
                  {q}
                </button>
              ))}
            </div>
            <div ref={chatRef} className="mb-2 flex max-h-[180px] flex-col gap-1.5 overflow-y-auto">
              {msgs.map((m, i) => (
                <div key={i}
                  className={`max-w-[88%] p-[8px_11px] text-[11.5px] leading-relaxed ${
                    m.role === "user"
                      ? "self-end bg-secondary text-[#085041]"
                      : "self-start bg-muted/40 text-muted-foreground"}`}
                  style={{ borderRadius: m.role === "user" ? "10px 3px 10px 10px" : "3px 10px 10px 10px" }}>
                  {m.text}
                </div>
              ))}
              {chatLoading && (
                <div className="self-start bg-muted/40 p-[8px_11px] text-[11px] italic text-muted-foreground/60"
                  style={{ borderRadius: "3px 10px 10px 10px" }}>
                  Querying engine…
                </div>
              )}
            </div>
            <div className="flex gap-1.5">
              <input value={inp} onChange={e => setInp(e.target.value)}
                onKeyDown={e => e.key === "Enter" && sendChat()}
                placeholder="Ask about these simulation results…"
                className="flex-1 rounded-[7px] border-[0.5px] border-border bg-muted/40 p-[8px_11px] text-[12px] text-foreground outline-none" />
              <Button onClick={sendChat}
                className="h-auto rounded-[7px] border-[0.5px] border-secondary bg-secondary px-3.5 py-2 text-[12px] font-medium text-[#085041] hover:bg-secondary/80">
                Send
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* ── NAVIGATION ── */}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t-[0.5px] border-border pt-4">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft size={15} /> Back to profiling
        </Button>

        {!lockedEstimator && (
          <Button onClick={() => { setLockedEstimator(estimator); setShowLockWarning(false); }}>
            <Lock size={14} /> Confirm &amp; lock estimator
          </Button>
        )}

        {onNext && (
          <Button
            onClick={() => lockedEstimator && onNext({
              estimator: lockedEstimator,
              estimatorLabel: ESTIMATORS.find(e => e.key === lockedEstimator)?.short ?? lockedEstimator,
              n: cohortN,
              result: result?.all?.[lockedEstimator]
                ? { ...result.all[lockedEstimator],
                    ciLower: result.all[lockedEstimator].ci?.[0],
                    ciUpper: result.all[lockedEstimator].ci?.[1] }
                : null,
              mode: "live",
              source: result?.source ?? "live",
            })}
            disabled={!lockedEstimator}
            title={!lockedEstimator ? "Lock an estimator first" : ""}>
            Proceed to results with{" "}
            {lockedEstimator
              ? ESTIMATORS.find(e => e.key === lockedEstimator)?.short
              : "…"} <ArrowRight size={15} />
          </Button>
        )}
      </div>

      {/* ── FOOTER ── */}
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-1.5">
        <span className="font-mono text-[10px] text-muted-foreground/60">
          Bootstrap validation · results served from the backend
        </span>
        {result?.timestamp && (
          <span className="font-mono text-[10px] text-muted-foreground/60">
            Loaded {result.timestamp.toLocaleTimeString()}
          </span>
        )}
      </div>

    </div>
  );
}
