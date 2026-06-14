import { useState, useEffect } from "react";
import { ArrowLeft, ArrowRight, Target, Activity, Users, CornerDownLeft, Check, Edit3, GitCompare } from "lucide-react";
import { fetchCohort, engagementGroup } from "../workspace/cohortData";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoBar, Tag } from "../ui/components";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 2c: OUTCOME SELECTION
// ─────────────────────────────────────────────────────────────────────────────

// Outcome metadata keyed by Supabase column name
// Maps validation_biomarkers column → display metadata
const OUTCOME_CATALOG = {
  hba1c_pct: {
    key:"hba1c", label:"HbA1c change", unit:"%", primary:true,
    desc:"Gold-standard cardiometabolic endpoint. Widely accepted by DiGA, NICE DSP, and HAS for digital health interventions.",
    tags:[["g","In dataset ✓"],["g","DiGA · NICE · HAS"]], verdict:"g", verdictLabel:"★ Recommended",
  },
  ldl_mgdl: {
    key:"ldl", label:"LDL-C change", unit:"mg/dL", primary:true,
    desc:"Standard lipid endpoint. Note: medication changes are an uncontrolled confounder — sensitivity analysis required.",
    tags:[["g","In dataset ✓"],["a","Medication confounder"]], verdict:"b", verdictLabel:"Good option",
  },
  hs_crp_mgl: {
    key:"crp", label:"hs-CRP change", unit:"mg/L", primary:true,
    desc:"Inflammatory marker. High within-person variability limits precision as a primary endpoint — better as secondary.",
    tags:[["g","In dataset ✓"],["a","High variability"]], verdict:"a", verdictLabel:"Secondary preferred",
  },
  glucose_mmol: {
    key:"glucose", label:"Fasting glucose change", unit:"mmol/L", primary:true,
    desc:"Direct diabetes risk marker. Accepted by HAS and DiGA as a primary or co-primary endpoint.",
    tags:[["g","In dataset ✓"],["b","HAS · DiGA"]], verdict:"b", verdictLabel:"Good option",
  },
  bmi: {
    key:"bmi", label:"BMI change", unit:"kg/m²", primary:false,
    desc:"Anthropometric endpoint. Widely used as secondary in lifestyle intervention studies.",
    tags:[["g","In dataset ✓"],["b","Secondary / co-primary"]], verdict:"a", verdictLabel:"Secondary preferred",
  },
  weight_kg: {
    key:"weight", label:"Body weight change", unit:"kg", primary:false,
    desc:"Common secondary endpoint in lifestyle and digital health studies.",
    tags:[["g","In dataset ✓"],["b","Secondary"]], verdict:"a", verdictLabel:"Secondary preferred",
  },
  sbp_mmhg: {
    key:"sbp", label:"Systolic BP change", unit:"mmHg", primary:false,
    desc:"Cardiovascular endpoint. Suitable as co-primary for hypertension-adjacent populations.",
    tags:[["g","In dataset ✓"],["b","Cardiovascular"]], verdict:"a", verdictLabel:"Possible",
  },
  tg_mgdl: {
    key:"tg", label:"Triglycerides change", unit:"mg/dL", primary:false,
    desc:"Lipid panel component. Typically secondary alongside LDL-C.",
    tags:[["g","In dataset ✓"],["b","Secondary"]], verdict:"a", verdictLabel:"Secondary preferred",
  },
};

// Hardcoded fallback used only when no Supabase data is available
const FALLBACK_OUTCOMES = [
  { key:"hba1c", label:"HbA1c change", unit:"%", primary:true,
    desc:"Gold-standard cardiometabolic endpoint. Accepted by DiGA, NICE DSP, and HAS.",
    tags:[["b","Primary endpoint"],["g","DiGA · NICE · HAS"]], verdict:"g", verdictLabel:"★ Recommended", available:true },
  { key:"ldl",   label:"LDL-C change", unit:"mg/dL", primary:true,
    desc:"Standard lipid endpoint.",
    tags:[["b","Common endpoint"],["a","Medication confounder"]], verdict:"b", verdictLabel:"Good option", available:true },
  { key:"crp",   label:"hs-CRP change", unit:"mg/L", primary:false,
    desc:"Inflammatory marker — secondary preferred.",
    tags:[["b","Secondary preferred"]], verdict:"a", verdictLabel:"Secondary preferred", available:true },
];

// Per-endpoint display metadata. Used when the project's endpoints don't have
// Supabase biomarker rows (e.g. Bloomlife), so we can still surface domain-relevant
// candidate outcomes instead of falling back to Lucis cardiometabolic ones.
const ENDPOINT_METADATA = {
  hba1c:                 { label:"HbA1c change",          unit:"%",      desc:"Gold-standard cardiometabolic endpoint. Accepted by DiGA, NICE DSP, and HAS." },
  ldl:                   { label:"LDL-C change",          unit:"mg/dL",  desc:"Standard lipid endpoint. Medication changes are an uncontrolled confounder." },
  crp:                   { label:"hs-CRP change",         unit:"mg/L",   desc:"Inflammatory marker — high within-person variability." },
  contraction_frequency: { label:"Uterine contraction frequency", unit:"per hr", desc:"Primary signal for preterm labor surveillance. Continuously measured by Bloomlife sensor." },
  maternal_hr:           { label:"Maternal heart rate",    unit:"bpm",    desc:"Maternal vital sign — supports detection of cardiovascular complications." },
  fetal_movement:        { label:"Fetal movement",         unit:"events", desc:"Fetal wellbeing indicator. Combined with FHR for surveillance scoring." },
};

function buildOutcomesFromEndpoints(endpoints) {
  if (!endpoints?.length) return FALLBACK_OUTCOMES;
  return endpoints.map((key, i) => {
    const meta = ENDPOINT_METADATA[key] ?? { label: key, unit: "", desc: "Project-defined endpoint." };
    return {
      key, label: meta.label, unit: meta.unit, primary: true,
      desc: meta.desc,
      tags: i === 0 ? [["g","Primary endpoint"]] : [["b","Candidate endpoint"]],
      verdict: i === 0 ? "g" : "b",
      verdictLabel: i === 0 ? "★ Recommended" : "Good option",
      available: true,
    };
  });
}


const EXPOSURE_OPTIONS = [
  "Top quartile engagement score (Q4)",
  "High engagement (≥3 sessions/week)",
  "Any platform use vs none",
];

const POPULATION_OPTIONS = [
  { group:"Condition",  items:["Prediabetic (HbA1c 5.7–6.4)","T2D (HbA1c ≥6.5)","Overweight (BMI ≥25)"] },
  { group:"Country",    items:["France","UK","Ireland","Portugal"] },
  { group:"Age",        items:["Adults (18–65)","Older adults (≥65)"] },
];
const D1_OUTCOME_MAP = {
  hba1c:   "HbA1c % change at 12 months",
  ldl:     "LDL-C mg/dL change at 12 months",
  crp:     "hs-CRP mg/L change at 12 months",
  glucose: "Fasting glucose change at 12 months",
  bmi:     "BMI change at 12 months",
  weight:  "Body weight change at 12 months",
  sbp:     "Systolic BP change at 12 months",
  tg:      "Triglycerides change at 12 months",
};

// Contrast / comparator options — the comparison group definition (demo-only)
const CONTRAST_OPTIONS = [
  { value: "Low engagement (<30) with the same platform",
    label: "Low engagement Lucis users (<30)",
    sub: "Agent default · N=158 · same tool, lower use intensity · no external control needed" },
  { value: "External comparator — standard care, no digital tool",
    label: "External comparator (standard care)",
    sub: "Stronger claim · requires careful matching · reference dataset available" },
  { value: "Pre-post comparison — same users before vs after platform access",
    label: "Pre-post comparison (before vs after access)",
    sub: "Requires baseline period data · susceptible to secular trends" },
];

// Per-element "agent rationale" lines, keyed by element id (P / A / Y / C)
const ELEMENT_RATIONALE = {
  exposure:   "Proposed from your dataset's engagement_score column (0% missing) + the product brief's mechanism of action (adherence to recommendations → metabolic improvement).",
  outcome:    "Proposed from your dataset's hba1c_t12 column + the prediabetes inclusion window, cross-checked against the DiGA · NICE · HAS benchmarking corpus.",
  population: "Proposed from the eligible cohort after applying the HbA1c eligibility filter and ≥12-month follow-up criterion, matched to the product brief's target population.",
  contrast:   "Proposed from your dataset structure: no unexposed control group is present — all users have platform access, so low-engagement users are the most defensible natural comparator.",
};

// Multi-select pill toggle helper
function MultiPill({ options, selected, onToggle }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(o => {
        const active = selected.includes(o);
        return (
          <div key={o} onClick={() => onToggle(o)}
            className={`cursor-pointer rounded-full border px-3 py-1.5 text-[12px] transition-colors ${
              active ? "border-primary bg-secondary font-medium text-primary" : "border-border font-normal text-muted-foreground hover:border-primary/40"
            }`}>
            {o}
          </div>
        );
      })}
    </div>
  );
}

// ── Per-element header: title + icon, agent rationale line, Confirm / Edit toggle ──
// `editing` gates the visibility of the existing selector below (passed as children
// by the caller). When confirmed (not editing), the caller renders a compact summary.
function ElementHeader({ icon: Icon, label, accent, rationale, editing, onEdit, onConfirm }) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <Icon size={15} style={{ color: accent }} />
          {label}
        </div>
        <div className="flex items-start gap-1.5 text-[11px] italic leading-snug text-muted-foreground">
          <span className="not-italic" aria-hidden>🤖</span>
          <span>{rationale}</span>
        </div>
      </div>
      <div className="flex flex-shrink-0 items-center gap-1.5">
        <button type="button" onClick={onConfirm}
          className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors ${
            editing
              ? "border-border bg-card text-muted-foreground hover:border-primary/40"
              : "border-primary bg-secondary text-primary"
          }`}>
          <Check size={12} /> {editing ? "Confirm" : "Confirmed"}
        </button>
        <button type="button" onClick={onEdit}
          className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors ${
            editing
              ? "border-primary bg-secondary text-primary"
              : "border-border bg-card text-muted-foreground hover:border-primary/40"
          }`}>
          <Edit3 size={12} /> Edit
        </button>
      </div>
    </div>
  );
}

export default function OutcomeSelection({ selectedOutcome, setSelectedOutcome, selectedCohort = '', cqExposure, setCqExposure, cqPopulation, setCqPopulation, partnerLabel = 'Partner', hasEngagementCol = true, projectEndpoints = [], chatProps = {} }) {
  const [sel, setSel]         = useState(selectedOutcome ?? "hba1c");
  const [liveStats, setLiveStats] = useState(null);

  // ── Contrast / comparator (DEMO-ONLY local state) ──────────────────────────
  // The comparison-group definition. Does not feed downstream — surfaced in the
  // live causal-question banner and as a confirmable agent-proposed element.
  const [cqContrast, setCqContrast]       = useState(CONTRAST_OPTIONS[0].value);
  const [contrastCustom, setContrastCustom] = useState("");

  // ── Per-element agent-proposes → Confirm / Edit affordance ──────────────────
  // Each element starts CONFIRMED (agent proposal accepted). Clicking Edit reveals
  // the existing selector/inputs for that element; Confirm collapses back to the
  // read-only summary. Visibility-only — the underlying handlers are untouched.
  const [editing, setEditing] = useState({
    exposure: false, outcome: false, population: false, contrast: false,
  });
  const startEdit  = (k) => setEditing(prev => ({ ...prev, [k]: true }));
  const confirmEl  = (k) => setEditing(prev => ({ ...prev, [k]: false }));

  function togglePop(item) {
    setCqPopulation(prev => prev.includes(item) ? prev.filter(p => p !== item) : [...prev, item]);
  }

  // Build outcome list from Supabase data — keys present in liveStats are "in dataset"
  // Falls back to FALLBACK_OUTCOMES until Supabase query resolves
  const OUTCOMES = liveStats
    ? (() => {
        // Columns queried from validation_biomarkers, in desired display order
        const COL_ORDER = ["hba1c_pct","ldl_mgdl","hs_crp_mgl","glucose_mmol","bmi","weight_kg","sbp_mmhg","tg_mgdl"];
        const statKey   = { hba1c_pct:"hba1c", ldl_mgdl:"ldl", hs_crp_mgl:"crp", glucose_mmol:"glucose",
                             bmi:"bmi", weight_kg:"weight", sbp_mmhg:"sbp", tg_mgdl:"tg" };
        const found = COL_ORDER
          .filter(col => OUTCOME_CATALOG[col] && liveStats[statKey[col]] != null)
          .map(col => ({ ...OUTCOME_CATALOG[col], available: true }));
        // Add composite if all three main biomarkers present
        const keys = found.map(f => f.key);
        if (["hba1c","ldl","crp"].every(k => keys.includes(k))) {
          found.push({
            key:"composite", label:"Composite metabolic score", unit:"", primary:true,
            desc:"Composite of HbA1c + LDL-C + hs-CRP. Stronger HTA narrative. Requires pre-specified threshold.",
            tags:[["g","In dataset ✓"],["b","EUnetHTA aligned"],["a","Complex definition"]],
            verdict:"a", verdictLabel:"Possible", available:true,
          });
        }
        return found.length > 0 ? found : buildOutcomesFromEndpoints(projectEndpoints);
      })()
    : buildOutcomesFromEndpoints(projectEndpoints);

  // If current sel is not in the loaded outcome list, fall back to first available
  const selected = OUTCOMES.find(o=>o.key===sel) ?? OUTCOMES[0];
  // Keep sel in sync if it fell back
  useEffect(() => {
    if (selected && selected.key !== sel) setSel(selected.key);
  }, [selected?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync lifted state whenever local selection changes
  useEffect(() => { setSelectedOutcome?.(sel); }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let alive = true;
    fetchCohort(selectedCohort).then(({ members, biomarkers, name }) => {
      if (!alive || !members.length || !biomarkers.length) return;

      const groupMap = Object.fromEntries(members.map(m => [m.member_id, engagementGroup(m)]));
      const t0map    = Object.fromEntries(
        biomarkers.filter(b => b.timepoint_months === 0).map(b => [b.member_id, b])
      );
      const t12rows  = biomarkers.filter(b => b.timepoint_months === 12);

      function computeEffect(col) {
        const out = {};
        // clés d'affichage capitalisées (contrat inchangé) ↔ groupe backend minuscule
        [["High", "high"], ["Medium", "medium"], ["Low", "low"]].forEach(([outKey, grp]) => {
          const matched = t12rows.filter(b =>
            groupMap[b.member_id] === grp &&
            t0map[b.member_id]?.[col] != null &&
            b[col] != null
          );
          if (matched.length) {
            const delta = matched.reduce((s, b) => s + (b[col] - t0map[b.member_id][col]), 0) / matched.length;
            out[outKey] = Math.round(delta * 100) / 100;
          }
        });
        out.n = new Set(t12rows.filter(b => b[col] != null).map(b => b.member_id)).size;
        return out;
      }

      setLiveStats({
        totalN:     members.length,
        cohortName: name,
        hba1c:      computeEffect("hba1c_pct"),
        ldl:        computeEffect("ldl_mgdl"),
        crp:        computeEffect("hs_crp_mgl"),
      });
    });
    return () => { alive = false; };
  }, [selectedCohort]);

  const cqOutcome  = D1_OUTCOME_MAP[sel] || "HbA1c % change at 12 months";
  const cqPopStr   = cqPopulation.length ? cqPopulation.join(" · ") : "—";
  const cqContrastStr = (contrastCustom.trim() || cqContrast || "—");

  return (
    <div className="flex flex-col gap-4">
      <InfoBar sources={[`${partnerLabel} dataset`,"DiGA · NICE · HAS criteria"]}>
        <strong>Definition of the causal question.</strong> Define your exposure, primary outcome, and target population. The causal question regenerates dynamically. Regulatory acceptability is mapped to DiGA, NICE, and HAS frameworks and is <strong>indicative only</strong> — validate with your regulatory affairs team.
      </InfoBar>

      {/* ── Causal question banner (live, larger) ─────────────────────────── */}
      <Card className="gap-0 rounded-xl bg-secondary/40 p-5">
        <div className="mb-3 text-[13px] font-semibold text-foreground">
          Causal question → sent to DAG agent
        </div>
        <div className="text-[17px] font-medium italic leading-[1.65] text-foreground">
          "Does <strong className="not-italic text-primary">{cqExposure}</strong> cause
          {" "}a reduction in <strong className="not-italic text-primary">{cqOutcome}</strong> in
          {" "}<strong className="not-italic text-muted-foreground">{cqPopStr}</strong>,
          {" "}compared to <strong className="not-italic" style={{ color: "#3C3489" }}>{cqContrastStr}</strong>?"
        </div>
      </Card>

      {/* ── Exposure (A) | Outcome (Y) — two columns ──────────────────────── */}
      <div className="grid grid-cols-2 gap-3.5">
        {/* Exposure column */}
        <Card className="gap-0 p-5">
          <ElementHeader
            icon={Activity} label="Exposure (A)" accent="#0F6E56"
            rationale={ELEMENT_RATIONALE.exposure}
            editing={editing.exposure}
            onEdit={() => startEdit("exposure")}
            onConfirm={() => confirmEl("exposure")}
          />

          {/* Confirmed summary (read-only) — shown when NOT editing */}
          {!editing.exposure && (
            <div className="flex items-start gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5">
              <Check size={14} className="mt-0.5 flex-shrink-0 text-primary" />
              <div className="flex-1">
                <div className="text-[12.5px] font-medium text-foreground">{cqExposure || "—"}</div>
                <div className="mt-0.5 text-[11px] font-medium text-primary">Confirmed</div>
              </div>
            </div>
          )}

          {/* Existing selector — visibility gated behind Edit. Handlers untouched. */}
          {editing.exposure && (
          <div className="flex flex-col gap-2">
            {hasEngagementCol
              ? EXPOSURE_OPTIONS.map((o, i) => {
                  const active = cqExposure === o;
                  return (
                    <div key={o} onClick={() => setCqExposure(o)}
                      className={`flex cursor-pointer items-center justify-between rounded-lg border px-3.5 py-2.5 text-[12.5px] transition-colors ${
                        active ? "border-primary bg-secondary font-medium text-primary" : "border-border font-normal text-foreground hover:border-primary/40"
                      }`}>
                      <span>{o}</span>
                      {i === 0 && <Tag color="g">Reco</Tag>}
                    </div>
                  );
                })
              : (
                <div className="rounded-lg border border-[#EF9F27] bg-[#FAEEDA] px-3.5 py-2.5 text-[12px] leading-relaxed text-muted-foreground">
                  No engagement column detected in the uploaded dataset — define your exposure below.
                </div>
              )}
            {/* Custom exposure input — always available */}
            <div className="mt-1.5">
              <div className="mb-1.5 text-[12px] text-muted-foreground">Or enter your own</div>
              <input type="text" value={EXPOSURE_OPTIONS.includes(cqExposure) ? "" : (cqExposure || "")}
                onChange={(e) => setCqExposure(e.target.value)}
                placeholder="e.g. Top quartile platform usage"
                className="w-full rounded-lg border border-border bg-card px-3 py-2.5 text-[12.5px] text-foreground outline-none focus:border-primary/40" />
            </div>
          </div>
          )}
        </Card>

        {/* Outcome column */}
        <Card className="gap-0 p-5">
          <ElementHeader
            icon={Target} label="Outcome (Y) — Primary" accent="#0C447C"
            rationale={ELEMENT_RATIONALE.outcome}
            editing={editing.outcome}
            onEdit={() => startEdit("outcome")}
            onConfirm={() => confirmEl("outcome")}
          />

          {/* Confirmed summary (read-only) — shown when NOT editing */}
          {!editing.outcome && (
            <div className="flex items-start gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5">
              <Check size={14} className="mt-0.5 flex-shrink-0 text-primary" />
              <div className="flex-1">
                <div className="text-[12.5px] font-medium text-foreground">
                  {selected ? `${selected.label}${selected.unit ? ` (${selected.unit})` : ""}` : "—"}
                </div>
                <div className="mt-0.5 text-[11px] font-medium text-primary">Confirmed as primary outcome</div>
              </div>
            </div>
          )}

          {/* Existing selector — visibility gated behind Edit. Handlers untouched. */}
          {editing.outcome && (
          <>
          <div className="mb-2 text-[12px] text-muted-foreground">Click to set as primary</div>
          {/* Primary outcomes */}
          <div className="flex flex-col gap-2">
            {OUTCOMES.filter(o => o.primary).map(o => {
              const active = sel === o.key;
              return (
                <div key={o.key} onClick={()=>setSel(o.key)}
                  className={`cursor-pointer rounded-lg border px-3.5 py-3 transition-colors ${
                    active ? "border-primary bg-secondary" : "border-border hover:border-primary/40"
                  }`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className={`mb-1 text-[12.5px] font-semibold ${active ? "text-primary" : "text-foreground"}`}>
                        {o.label}{o.unit ? ` (${o.unit})` : ""}
                      </div>
                      <div className="text-[12px] leading-snug text-muted-foreground">{o.desc}</div>
                    </div>
                    {o.verdict === "g" && <Tag color="g">★ Reco</Tag>}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Secondary outcomes — promotable to primary */}
          {OUTCOMES.filter(o => !o.primary).length > 0 && (
            <>
              <div className="mb-2 mt-4 text-[12px] text-muted-foreground">
                Secondary &amp; exploratory · click to promote to primary
              </div>
              <div className="flex flex-col gap-1.5">
                {OUTCOMES.filter(o => !o.primary).map(o=>(
                  <div key={o.key} onClick={()=>setSel(o.key)}
                    className="flex cursor-pointer items-center justify-between gap-2 rounded-lg border border-border px-3.5 py-2.5 transition-colors hover:border-primary/40">
                    <div className="text-[12px] font-medium text-foreground/80">
                      {o.label}{o.unit ? ` (${o.unit})` : ""}
                    </div>
                    <Tag color="b">Promotable to primary</Tag>
                  </div>
                ))}
              </div>
            </>
          )}
          </>
          )}
        </Card>
      </div>

      {/* ── Population (P) — full width, grouped ──────────────────────────── */}
      <Card className="gap-0 p-5">
        <ElementHeader
          icon={Users} label="Population (P)" accent="#854F0B"
          rationale={ELEMENT_RATIONALE.population}
          editing={editing.population}
          onEdit={() => startEdit("population")}
          onConfirm={() => confirmEl("population")}
        />

        {/* Confirmed summary (read-only) — shown when NOT editing */}
        {!editing.population && (
          <div className="flex items-start gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5">
            <Check size={14} className="mt-0.5 flex-shrink-0 text-primary" />
            <div className="flex-1">
              <div className="text-[12.5px] font-medium text-foreground">{cqPopStr}</div>
              <div className="mt-0.5 text-[11px] font-medium text-primary">
                {cqPopulation.length ? "Confirmed" : "No criteria selected yet"}
              </div>
            </div>
          </div>
        )}

        {/* Existing selector — visibility gated behind Edit. Handlers untouched. */}
        {editing.population && (
        <>
        {POPULATION_OPTIONS.map(g => (
          <div key={g.group} className="mb-3">
            <div className="mb-2 text-[12px] font-medium text-foreground/80">{g.group}</div>
            <MultiPill options={g.items} selected={cqPopulation} onToggle={togglePop} />
          </div>
        ))}
        {/* Custom population criterion input */}
        <div className="mt-3">
          <div className="mb-2 text-[12px] font-medium text-foreground/80">Custom criterion</div>
          <div className="flex items-center gap-2">
            <input type="text"
              placeholder="e.g. Adults aged 50–70 with chronic kidney disease"
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.currentTarget.value.trim()) {
                  const v = e.currentTarget.value.trim();
                  if (!cqPopulation.includes(v)) togglePop(v);
                  e.currentTarget.value = "";
                }
              }}
              className="flex-1 rounded-lg border border-border bg-card px-3 py-2.5 text-[12.5px] text-foreground outline-none focus:border-primary/40" />
            <span className="flex items-center gap-1 text-[12px] text-muted-foreground"><CornerDownLeft size={13} /> to add</span>
          </div>
        </div>
        {cqPopulation.length === 0 && (
          <div className="mt-2 text-[12px] text-muted-foreground">Select one or more population criteria above</div>
        )}
        </>
        )}
      </Card>

      {/* ── Contrast / comparator (C) — full width, DEMO-ONLY ─────────────── */}
      <Card className="gap-0 p-5">
        <ElementHeader
          icon={GitCompare} label="Contrast / comparator" accent="#3C3489"
          rationale={ELEMENT_RATIONALE.contrast}
          editing={editing.contrast}
          onEdit={() => startEdit("contrast")}
          onConfirm={() => confirmEl("contrast")}
        />

        {/* Confirmed summary (read-only) — shown when NOT editing */}
        {!editing.contrast && (
          <div className="flex items-start gap-2 rounded-lg border px-3.5 py-2.5"
            style={{ borderColor: "#AFA9EC", background: "#EEEDFE80" }}>
            <Check size={14} className="mt-0.5 flex-shrink-0" style={{ color: "#3C3489" }} />
            <div className="flex-1">
              <div className="text-[12.5px] font-medium text-foreground">{cqContrastStr}</div>
              <div className="mt-0.5 text-[11px] font-medium" style={{ color: "#3C3489" }}>Confirmed comparison group</div>
            </div>
          </div>
        )}

        {/* Editable control — revealed by Edit. Demo-only; does not feed downstream. */}
        {editing.contrast && (
          <div className="flex flex-col gap-2">
            {CONTRAST_OPTIONS.map(o => {
              const active = !contrastCustom.trim() && cqContrast === o.value;
              return (
                <div key={o.value}
                  onClick={() => { setCqContrast(o.value); setContrastCustom(""); }}
                  className={`cursor-pointer rounded-lg border px-3.5 py-2.5 transition-colors ${
                    active ? "bg-secondary/60" : "border-border hover:border-primary/40"
                  }`}
                  style={active ? { borderColor: "#AFA9EC", background: "#EEEDFE80" } : undefined}>
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded-full border-[1.5px]"
                      style={{ borderColor: active ? "#3C3489" : "#d3d1c7", background: active ? "#3C3489" : "transparent" }}>
                      {active && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                    </span>
                    <div>
                      <div className={`text-[12.5px] font-medium ${active ? "text-foreground" : "text-foreground/80"}`}>{o.label}</div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">{o.sub}</div>
                    </div>
                  </div>
                </div>
              );
            })}
            {/* Custom comparator input */}
            <div className="mt-1.5">
              <div className="mb-1.5 text-[12px] text-muted-foreground">Or describe a custom comparator</div>
              <input type="text" value={contrastCustom}
                onChange={(e) => setContrastCustom(e.target.value)}
                placeholder="e.g. Matched non-users from a national registry"
                className="w-full rounded-lg border border-border bg-card px-3 py-2.5 text-[12.5px] text-foreground outline-none focus:border-primary/40" />
            </div>
          </div>
        )}
      </Card>

      {/* ── Augura assistant — BOTTOM ─────────────────────────────────────── */}
      <InlineChatbot {...chatProps} />

    </div>
  );
}
