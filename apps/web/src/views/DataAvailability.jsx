import { useState, useEffect } from "react";
import { Check, X, AlertTriangle, ArrowLeft, ArrowRight, Users, Filter, Network } from "lucide-react";
import { supabase } from "../supabase";
import { TENANT_ID } from "../config";
import { InfoBar, Btn, Tag } from "../ui/components";
import { Card } from "@/components/ui/card";
import { SubTabs } from "@/cockpit/SubTabs";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 2d: DATA AVAILABILITY / VERIFICATION
// Sub-tabs mirror the navigation sketch (5a Population · 5b Outcomes ·
// 5c Intervention · 5d Missing data). The original availability checklist is
// preserved verbatim under the "Outcomes" tab; the three new tabs add demo
// content matching the sketch structure in the clean shadcn aesthetic.
// ─────────────────────────────────────────────────────────────────────────────
const DATA_VARS = [
  { label:"HbA1c change at 12 months (primary outcome)", sub:"hba1c_t12 · N=824 prediabetes eligible · lab-measured", status:"green", pct:100, icon:"✓" },
  { label:"Engagement score (primary exposure)",          sub:"recommendations_followed_pct · 92.5% coverage · composite of adherence, logins, test completion", status:"green", pct:93, icon:"✓" },
];
const CONFOUNDERS = [
  { label:"Age",                          sub:"age · 99.9% · mean 44.8 years · range 35–65", pct:100, status:"green", icon:"✓" },
  { label:"Sex",                          sub:"sex · 100% · 52% female · binary variable", pct:100, status:"green", icon:"✓" },
  { label:"BMI",                          sub:"bmi · 99.4% · mean 27.6 · self-reported — measurement error possible", pct:99, status:"green", icon:"✓" },
  { label:"Baseline HbA1c",              sub:"hba1c_t0 · 100% in study cohort · lab-measured · mean 6.05 ± 0.19", pct:100, status:"green", icon:"✓" },
  { label:"Medication changes during follow-up", sub:"NOT in dataset · key confounder for LDL-C · self-report supplementation possible", pct:0, status:"red", icon:"✗" },
  { label:"Health motivation / literacy", sub:"Unmeasured by design · residual confounding risk · reported as limitation", pct:0, status:"amber", icon:"~" },
];
const MEDIATORS = [
  { label:"Recommendation adherence % (primary mediator)", sub:"recommendations_followed_pct · 92.5% coverage · composite variable", pct:93, status:"green", icon:"✓" },
  { label:"Activity & lifestyle data (secondary mediator)", sub:"activity_freq, sleep_quality · 100% in synthetic dataset · partial in real data", pct:62, status:"amber", icon:"⚠" },
];

// Status tones for the variable rows (availability signal palette).
const STATUS_TONE = {
  green: { wrap: "border-[#97C459] bg-secondary", text: "text-[#27500A]" },
  red:   { wrap: "border-[#F09595] bg-[#FCEBEB]",  text: "text-[#791F1F]" },
  amber: { wrap: "border-[#EF9F27] bg-[#FAEEDA]",  text: "text-[#854F0B]" },
};

// Map the data-provided status glyph to a semantic lucide icon.
const STATUS_ICON = { "✓": Check, "✗": X };
function StatusIcon({ icon, className }) {
  const Lucide = STATUS_ICON[icon] ?? AlertTriangle;
  return <Lucide size={14} className={className} strokeWidth={2.5} />;
}

function VarRow({ label, sub, pct, status, icon }) {
  const tone = STATUS_TONE[status] ?? { wrap: "border-border bg-card", text: "text-foreground" };
  return (
    <div className={`mb-2 flex items-start gap-2.5 rounded-lg border px-3 py-2.5 ${tone.wrap}`}>
      <div className={`flex w-4 flex-shrink-0 items-center justify-center pt-px ${tone.text}`}>
        <StatusIcon icon={icon} />
      </div>
      <div className="flex-1">
        <div className="mb-0.5 text-[12.5px] font-semibold text-foreground">{label}</div>
        <div className="text-[12px] leading-[1.45] text-muted-foreground">{sub}</div>
      </div>
      {pct > 0 && (
        <div className={`flex-shrink-0 font-mono text-[12px] font-semibold ${tone.text}`}>{pct}%</div>
      )}
    </div>
  );
}

// ── Verification row: name + column + meta + an alignment/role tag ────────────
const VERIFY_TONE = {
  ok:      { wrap: "border-[#97C459] bg-secondary",      tag: "g" },
  partial: { wrap: "border-[#EF9F27] bg-[#FAEEDA]",       tag: "a" },
  missing: { wrap: "border-[#F09595] bg-[#FCEBEB]",       tag: "r" },
  plain:   { wrap: "border-border bg-card",               tag: "b" },
};
function VerifyRow({ name, col, meta, tag, tone = "ok" }) {
  const t = VERIFY_TONE[tone] ?? VERIFY_TONE.plain;
  return (
    <div className={`flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5 ${t.wrap}`}>
      <div className="min-w-0 flex-1">
        <div className="text-[12.5px] font-semibold text-foreground">{name}</div>
        {col && <div className="font-mono text-[11.5px] text-muted-foreground">{col}</div>}
        {meta && <div className="mt-0.5 text-[12px] leading-[1.45] text-muted-foreground">{meta}</div>}
      </div>
      {tag && <Tag color={t.tag}>{tag}</Tag>}
    </div>
  );
}

// ── Horizontal missingness bar (variable · track · %) ─────────────────────────
function MissRow({ name, pct }) {
  const high = pct >= 10;
  return (
    <div className="flex items-center gap-3 border-b border-border py-1.5 last:border-b-0">
      <span className="min-w-[200px] text-[12px] font-medium text-foreground">{name}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.max(pct, 1.5)}%`, background: pct === 0 ? "#97C459" : high ? "#C0392B" : "#EF9F27" }}
        />
      </div>
      <span
        className="min-w-[40px] text-right font-mono text-[11.5px] font-semibold"
        style={{ color: pct === 0 ? "#27500A" : high ? "#C0392B" : "#854F0B" }}
      >
        {pct}%
      </span>
    </div>
  );
}

// Section heading helper — sentence-case, small semibold.
function SectionLabel({ children }) {
  return <div className="mb-2 text-[13px] font-semibold text-foreground">{children}</div>;
}

export default function DataAvailability({ selectedOutcome = "hba1c", selectedCohort = "", partnerLabel = 'Partner', hasEngagementCol = true, chatProps = {} }) {
  const [cohort, setCohort] = useState(null);
  const [sub, setSub] = useState("population");

  useEffect(() => {
    const url = import.meta.env.VITE_SUPABASE_URL;
    const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
    if (!url || !key) return;
    const client = supabase;

    Promise.all([
      client.from("validation_members")
        .select("member_id, age, sex, bmi")
        .eq("tenant_id", TENANT_ID)
        .eq("cohort_name", selectedCohort),
      client.from("validation_biomarkers")
        .select("member_id, hba1c_pct, ldl_mgdl, hs_crp_mgl, adherence_pct")
        .eq("tenant_id", TENANT_ID)
        .eq("cohort_name", selectedCohort)
        .eq("timepoint_months", 0),
      client.from("validation_biomarkers")
        .select("member_id, hba1c_pct, ldl_mgdl, hs_crp_mgl")
        .eq("tenant_id", TENANT_ID)
        .eq("cohort_name", selectedCohort)
        .eq("timepoint_months", 12),
    ]).then(([{ data: members }, { data: t0 }, { data: t12 }]) => {
      if (!members?.length) return;
      const N = members.length;
      const pct = (n) => Math.round(n / N * 100);

      const ageSexN      = members.filter(m => m.age != null && m.sex != null).length;
      const bmiN         = members.filter(m => m.bmi != null).length;
      const adherenceN   = t0?.filter(b => b.adherence_pct != null).length ?? 0;
      const hba1cT0N     = t0?.filter(b => b.hba1c_pct != null).length ?? 0;
      const hba1cT12N    = t12?.filter(b => b.hba1c_pct != null).length ?? 0;
      const ldlT12N      = t12?.filter(b => b.ldl_mgdl != null).length ?? 0;
      const crpT12N      = t12?.filter(b => b.hs_crp_mgl != null).length ?? 0;

      setCohort({
        total: N,
        ageSexPct:    pct(ageSexN),
        bmiPct:       pct(bmiN),
        adherencePct: adherenceN > 0 ? pct(adherenceN) : null,
        hba1cT0Pct:   pct(hba1cT0N),
        hba1cT12Pct:  pct(hba1cT12N),
        ldlT12Pct:    pct(ldlT12N),
        crpT12Pct:    pct(crpT12N),
        hba1cT12N,
        ldlT12N,
        crpT12N,
      });
    });
  }, []);

  // ── Dynamic content driven by selected outcome ────────────────────────────
  const PRIMARY_OUTCOME_ROW = {
    hba1c: { label:"HbA1c change at 12 months (primary outcome)", icon:"✓", status:"green",
      pct: cohort?.hba1cT12Pct ?? 100,
      sub: `hba1c_t12 · N=${cohort?.hba1cT12N ?? "…"} eligible · lab-measured` },
    ldl:   { label:"LDL-C change at 12 months (primary outcome)", icon:"✓", status:"green",
      pct: cohort?.ldlT12Pct ?? 100,
      sub: `ldl_t12 · N=${cohort?.ldlT12N ?? "…"} eligible · medication confounder unmeasured — critical` },
    crp:   { label:"hs-CRP change at 12 months (primary outcome)", icon:"✓", status:"green",
      pct: cohort?.crpT12Pct ?? 100,
      sub: `hs_crp_t12 · N=${cohort?.crpT12N ?? "…"} eligible · high within-person variability` },
  };

  const DYNAMIC_SECONDARIES = {
    hba1c: [
      { label:"LDL-C change at 12M",      icon:"✓", status:"green", pct: cohort?.ldlT12Pct   ?? 100, sub:`ldl_t12 · N=${cohort?.ldlT12N ?? "…"} · medication confounder unmeasured` },
      { label:"hs-CRP change at 12M",     icon:"✓", status:"green", pct: cohort?.crpT12Pct   ?? 100, sub:`hs_crp_t12 · N=${cohort?.crpT12N ?? "…"} · high within-person variability` },
      { label:"Diabetes progression flag",icon:"✓", status:"green", pct:100,                          sub:"Derived from HbA1c ≥6.5% · binary · 100% coverage" },
    ],
    ldl: [
      { label:"HbA1c change at 12M",      icon:"✓", status:"green", pct: cohort?.hba1cT12Pct ?? 100, sub:`hba1c_t12 · N=${cohort?.hba1cT12N ?? "…"} · lab-measured` },
      { label:"hs-CRP change at 12M",     icon:"✓", status:"green", pct: cohort?.crpT12Pct   ?? 100, sub:`hs_crp_t12 · N=${cohort?.crpT12N ?? "…"} · high within-person variability` },
    ],
    crp: [
      { label:"HbA1c change at 12M",      icon:"✓", status:"green", pct: cohort?.hba1cT12Pct ?? 100, sub:`hba1c_t12 · N=${cohort?.hba1cT12N ?? "…"} · lab-measured` },
      { label:"LDL-C change at 12M",      icon:"✓", status:"green", pct: cohort?.ldlT12Pct   ?? 100, sub:`ldl_t12 · N=${cohort?.ldlT12N ?? "…"} · medication confounder unmeasured` },
    ],
  };

  const medConfounder = selectedOutcome === "ldl"
    ? { label:"Medication changes during follow-up", icon:"✗", status:"red",  pct:0,
        sub:"NOT in dataset · CRITICAL confounder for LDL-C primary endpoint · self-report supplementation required" }
    : { label:"Medication changes during follow-up", icon:"~", status:"amber", pct:0,
        sub:"NOT in dataset · key confounder for LDL-C (secondary) · self-report supplementation possible" };

  const dynamicConfounders = CONFOUNDERS.map(c =>
    c.label.startsWith("Medication") ? medConfounder : c
  );

  const primaryRow     = PRIMARY_OUTCOME_ROW[selectedOutcome] ?? PRIMARY_OUTCOME_ROW.hba1c;
  const secondaryRows  = DYNAMIC_SECONDARIES[selectedOutcome]  ?? DYNAMIC_SECONDARIES.hba1c;
  const eligibleN      = selectedOutcome === "ldl" ? cohort?.ldlT12N : selectedOutcome === "crp" ? cohort?.crpT12N : cohort?.hba1cT12N;

  // Final eligible N drives the population funnel terminal step. Falls back to
  // the sketch's canonical 824 when the live cohort hasn't loaded.
  const finalN = eligibleN ?? cohort?.total ?? 824;

  // ── Population eligibility cascade (demo) ──────────────────────────────────
  const CASCADE = [
    { label:"Enrolled in cohort",                 col:"all_members",                  n:1204, note:"Full uploaded dataset" },
    { label:"HbA1c at baseline 5.7–6.4%",          col:"hba1c_baseline BETWEEN 5.7 AND 6.4", n:1041, note:"Prediabetes inclusion window" },
    { label:"≥12-month follow-up",                 col:"followup_months ≥ 12",          n:912,  note:"Sufficient observation period" },
    { label:"No exclusion medications",            col:"exclusion_meds = 0",            n:868,  note:"GLP-1 / insulin starters removed" },
    { label:"Primary outcome at 12M present",      col:"hba1c_12m IS NOT NULL",          n:finalN, note:"Final analysis population" },
  ];
  const enrolled = CASCADE[0].n;

  // ── DAG ↔ dataset alignment (demo) ─────────────────────────────────────────
  const DAG_ALIGNMENT = [
    { name:"Intervention · engagement score",                    col:"engagement_score",                    meta:"Exposure (A) · Missing 0%",       tag:"Aligned",       tone:"ok" },
    { name:"Primary outcome · HbA1c change at 12M",              col:"hba1c_change_12m",                    meta:"Outcome (Y) · Missing 6.1%",      tag:"Aligned",       tone:"ok" },
    { name:"Mediator · recommendation adherence",               col:"rec_adherence_pct",                   meta:"Mediator (M1) · Missing 0%",      tag:"Aligned",       tone:"ok" },
    { name:"Mediator · lifestyle behavior change",              col:"wearable_activity_score",             meta:"Mediator (M2) · 38% wearable coverage", tag:"Partial", tone:"partial" },
    { name:"Measured confounders · age, sex, BMI, baseline",    col:"age · sex · bmi · hba1c_baseline",    meta:"Confounders (W) · Missing <0.5%", tag:"Aligned",       tone:"ok" },
    { name:"Unmeasured confounders (3)",                        col:"— not in dataset —",                  meta:"Motivation · medication changes · literacy → E-value", tag:"Not available", tone:"missing" },
    { name:"Effect modifiers · age group, baseline HbA1c, sex", col:"age · hba1c_baseline · sex",          meta:"Pre-specified subgroups",         tag:"Aligned",       tone:"ok" },
  ];

  // ── Intervention component variables (demo) ────────────────────────────────
  const INTERVENTION_VARS = [
    { name:"Recommendation adherence rate", col:"rec_adherence_pct", meta:"Continuous · % · weight 0.5 · primary engagement metric · Missing 0%", tag:"Confirmed",  tone:"ok" },
    { name:"Logins per month",              col:"logins_per_month",  meta:"Count · weight 0.3 · usage intensity · Missing 0%",                    tag:"Confirmed",  tone:"ok" },
    { name:"Repeat test completion",        col:"repeat_test_flag",  meta:"Binary · weight 0.2 · re-test behaviour · Missing 0%",                 tag:"Confirmed",  tone:"ok" },
  ];

  // ── Missing data per-variable + imputation strategy (demo) ─────────────────
  const MISSINGNESS = [
    { name:"hba1c_change_12m (primary)",     pct:6.1 },
    { name:"ldl_change_12m",                 pct:5.6 },
    { name:"crp_change_12m",                 pct:6.7 },
    { name:"diabetes_progression_flag",      pct:0 },
    { name:"engagement_score",               pct:0 },
    { name:"wearable_activity_score (M2)",   pct:38 },
  ];
  const IMPUTATION = [
    { strat:"Multiple imputation", tone:"ok",      label:"Multiple imputation (primary)",
      desc:`Preserves all ${finalN} observations. M=20 imputed datasets, Rubin's rules. Imputation model: age, sex, BMI, baseline HbA1c, engagement score, country.`,
      tags:[["g","★ Locked"],["b","MAR assumption"]] },
    { strat:"Complete-case", tone:"partial", label:"Complete case (sensitivity only)",
      desc:"N=748 with no missing data on any analysis variable. Reserved for the sensitivity engine, not the primary analysis.",
      tags:[["a","Sensitivity only"]] },
    { strat:"None", tone:"plain", label:"No imputation (wearable M2)",
      desc:"wearable_activity_score (38% missing) is excluded from the primary adjustment set rather than imputed — used only in the mediation sensitivity branch.",
      tags:[["b","Excluded from primary"]] },
  ];

  return (
    <div className="flex flex-col gap-4">
      <InfoBar sources={[`${partnerLabel} dataset`, cohort ? `N=${cohort.total} validation cohort` : "N=… validation cohort"]}>
        <strong>Verification.</strong> Augura cross-references every element of the study design against the {partnerLabel} dataset ({cohort ? `N=${cohort.total} validation cohort` : "validation cohort"}) — population eligibility, outcome and intervention variables, and the missing-data strategy — before any outcome data are examined.
      </InfoBar>

      <SubTabs
        tabs={[
          { id: "population",   label: "Population",   icon: <Users size={14} /> },
          { id: "outcomes",     label: "Outcomes" },
          { id: "intervention", label: "Intervention" },
          { id: "missing",      label: "Missing data" },
        ]}
        active={sub}
        onChange={setSub}
      />

      {/* ════════════════════════ 5a — POPULATION ════════════════════════ */}
      {sub === "population" && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
            <strong className="text-foreground">Population verification.</strong>{" "}
            Confirm the population from the causal question is correctly identified in the dataset. Each eligibility criterion is applied in sequence — the cascade below shows how the enrolled cohort narrows to the final analysis population.
          </div>

          <div className="grid grid-cols-[1fr_320px] items-start gap-4">
            {/* Eligibility funnel */}
            <Card className="gap-0 rounded-xl border p-5">
              <div className="mb-3 flex items-center gap-1.5 text-[15px] font-semibold text-foreground">
                <Filter size={15} className="text-primary" /> Eligibility cascade
              </div>
              <div className="flex flex-col">
                {CASCADE.map((step, i) => {
                  const isLast = i === CASCADE.length - 1;
                  const widthPct = Math.round((step.n / enrolled) * 100);
                  const dropped = i === 0 ? 0 : CASCADE[i - 1].n - step.n;
                  return (
                    <div key={step.col}>
                      <div className="flex items-center gap-3">
                        <div className="flex-1">
                          <div
                            className={`flex items-center justify-between rounded-lg border px-3.5 py-2.5 transition-colors ${
                              isLast ? "border-[#97C459] bg-secondary" : "border-border bg-card"
                            }`}
                            style={{ width: `${Math.max(widthPct, 56)}%` }}
                          >
                            <div className="min-w-0">
                              <div className={`text-[12.5px] font-semibold ${isLast ? "text-[#27500A]" : "text-foreground"}`}>
                                {step.label}
                              </div>
                              <div className="font-mono text-[11px] text-muted-foreground">{step.col}</div>
                            </div>
                            <div className={`ml-3 flex-shrink-0 font-mono text-[15px] font-semibold ${isLast ? "text-[#27500A]" : "text-foreground"}`}>
                              {step.n.toLocaleString()}
                            </div>
                          </div>
                        </div>
                        <div className="w-[150px] flex-shrink-0 text-[11.5px] leading-snug text-muted-foreground">
                          {step.note}
                        </div>
                      </div>
                      {!isLast && (
                        <div className="flex items-center gap-1.5 py-1 pl-3 text-[11px] text-muted-foreground">
                          <ArrowRight size={11} className="rotate-90" />
                          {dropped > 0
                            ? <span>−{dropped.toLocaleString()} excluded</span>
                            : <span>no exclusions</span>}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-[#97C459] bg-secondary px-3.5 py-2.5 text-[12.5px] font-semibold text-[#27500A]">
                <Check size={15} strokeWidth={2.5} className="flex-shrink-0" />
                Eligible population: N = {finalN.toLocaleString()} — all criteria verified
              </div>
            </Card>

            {/* Right column — cohort stats + DAG alignment summary */}
            <div className="flex flex-col gap-4">
              <Card className="gap-0 rounded-xl border p-5">
                <div className="mb-3 flex items-center gap-1.5 text-[13px] font-semibold text-foreground">
                  <Users size={14} className="text-primary" /> Cohort snapshot
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  {[
                    [finalN.toLocaleString(), "Eligible users", "text-primary"],
                    [`${Math.round((finalN / enrolled) * 100)}%`, "Of full dataset", "text-foreground"],
                    ["52%", "Female", "text-foreground"],
                    ["47.3", "Mean age", "text-foreground"],
                  ].map(([v, l, c]) => (
                    <div key={l} className="rounded-lg bg-muted/50 p-3 text-center">
                      <div className={`font-mono text-[20px] font-semibold ${c}`}>{v}</div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">{l}</div>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="gap-0 rounded-xl border p-5">
                <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold text-foreground">
                  <Network size={14} className="text-primary" /> DAG ↔ dataset alignment
                </div>
                <div className="mb-3 rounded-lg border border-[#97C459] bg-secondary px-3 py-2.5 text-[12px] leading-[1.5] text-[#27500A]">
                  <strong>6 of 7 DAG nodes fully aligned.</strong> M2 (wearable) excluded from the primary adjustment set. Unmeasured confounders flagged for the sensitivity engine.
                </div>
                <div className="flex flex-col gap-1.5">
                  {DAG_ALIGNMENT.map((n) => (
                    <div key={n.col} className="flex items-center justify-between gap-2 text-[12px]">
                      <span className="min-w-0 flex-1 truncate text-muted-foreground">{n.name}</span>
                      <Tag color={VERIFY_TONE[n.tone].tag}>{n.tag}</Tag>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* ════════════════════════ 5b — OUTCOMES (existing availability) ════════════════════════ */}
      {sub === "outcomes" && (
        <div className="flex flex-col gap-4">
          {/* KPI summary */}
          <div className="grid grid-cols-4 gap-4">
            {[
              ["7 / 8",                             "DAG variables available",   "text-primary",
                "Number of variables identified by the causal DAG that are present in the uploaded dataset."],
              ["1",                                 "Critical variable missing",  "text-[#854F0B]",
                "A variable identified by the DAG as a confounder on the causal path between exposure and outcome, but absent from the dataset. Missing it threatens the validity of the causal estimate and must be addressed by a sensitivity analysis or alternative design."],
              [eligibleN ? `${eligibleN}` : cohort ? `${cohort.total}` : "…", "With primary outcome at T12", "text-primary",
                "Number of participants in the cohort with a measured value of the primary outcome at the 12-month follow-up."],
              ["2",                                 "Unmeasured confounders",     "text-[#854F0B]",
                "Variables known from clinical literature to potentially confound the exposure-outcome relationship, but not captured in any digital health dataset (e.g. motivation, health literacy). Reported as study limitations and probed via E-value sensitivity analysis."],
            ].map(([v,l,c,tip])=>(
              <Card key={l} title={tip} className={`gap-0 rounded-xl p-4 ${tip ? "cursor-help" : ""}`}>
                <div className={`font-mono text-[22px] font-semibold ${c}`}>{v}</div>
                <div className="mt-1 text-[12px] text-muted-foreground">{l}</div>
              </Card>
            ))}
          </div>

          {/* Definitions InfoBar — surfaces what "critical" vs "unmeasured" means */}
          <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
            <strong className="text-foreground">How variables are classified.</strong>{" "}
            <em>Critical</em> = identified by the DAG as confounding the exposure→outcome path
            <em> and</em> missing from the dataset (threatens identifiability — needs sensitivity analysis).
            {" "}<em>Unmeasured</em> = clinically plausible confounder structurally absent from
            digital-health data (e.g. health motivation, literacy, socioeconomic status); reported as
            a limitation and probed via E-value, not blocking. <em>Present</em> = the column exists
            in your uploaded dataset with sufficient coverage.
          </div>

          {/* Variable rows — 2-column layout */}
          <div className="grid grid-cols-2 gap-4">
            {/* Left column — Primary outcome, Exposure, Confounders */}
            <div className="flex flex-col gap-4">
              <div>
                <SectionLabel>Primary outcome</SectionLabel>
                <VarRow {...primaryRow} />
              </div>
              <div>
                <SectionLabel>Exposure (treatment variable)</SectionLabel>
                {hasEngagementCol
                  ? <VarRow {...DATA_VARS[1]} />
                  : <VarRow label="Exposure variable" status="amber" icon="⚠" pct={0}
                      sub="No engagement / adherence column detected in uploaded dataset — define exposure manually or upload a dataset with this variable." />}
              </div>
              <div>
                <SectionLabel>Confounders</SectionLabel>
                {dynamicConfounders.map(v=><VarRow key={v.label} {...v} />)}
              </div>
            </div>

            {/* Right column — Mediators, Secondary outcomes */}
            <div className="flex flex-col gap-4">
              <div>
                <SectionLabel>Mediators</SectionLabel>
                {hasEngagementCol
                  ? MEDIATORS.map(v=><VarRow key={v.label} {...v} />)
                  : <VarRow label="Mediators" status="amber" icon="⚠" pct={0}
                      sub="Mediator detection requires an engagement / adherence column in the uploaded dataset." />}
              </div>
              <div>
                <SectionLabel>Secondary outcomes</SectionLabel>
                {secondaryRows.map(v=><VarRow key={v.label} {...v} />)}
              </div>
            </div>
          </div>

          {/* Proceed banner */}
          <div className="rounded-xl border border-[#97C459] bg-secondary p-4">
            <div className="mb-1 flex items-center gap-1.5 text-[13px] font-semibold text-[#27500A]">
              <Check size={15} strokeWidth={2.5} className="flex-shrink-0" />
              Data sufficient to proceed with retrospective study
            </div>
            <div className="text-[12.5px] leading-[1.5] text-muted-foreground">
              7 of 8 required DAG variables are present. <strong>1 critical variable missing</strong> (medication changes during follow-up) — will be handled as a sensitivity analysis. Unmeasured confounders (motivation, literacy) reported as study limitations — standard practice in RWE. Eligible N=<strong>{cohort ? cohort.total : "…"}</strong>.
            </div>
          </div>
        </div>
      )}

      {/* ════════════════════════ 5c — INTERVENTION ════════════════════════ */}
      {sub === "intervention" && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
            <strong className="text-foreground">Intervention variable verification.</strong>{" "}
            The exposure is a composite <span className="font-mono">engagement_score</span> (0–100, tertile operationalisation). Each engagement-component variable is verified for presence, type, and role before the score is locked.
          </div>

          <div className="grid grid-cols-[1fr_300px] items-start gap-4">
            <Card className="gap-0 rounded-xl border p-5">
              <div className="mb-1 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[15px] font-semibold text-foreground">Lucis composite engagement score</div>
                  <div className="font-mono text-[12px] text-muted-foreground">engagement_score</div>
                </div>
                <Tag color="g">Confirmed</Tag>
              </div>
              <div className="mb-3 flex flex-wrap gap-1.5">
                <Tag color="b">Continuous 0–100 · tertile split</Tag>
                <Tag color="g">N = 4,023 · Missing 0%</Tag>
              </div>
              <div className="mb-3 text-[12px] leading-[1.5] text-muted-foreground">
                Composite of three component variables. High &gt; 70, Medium 30–70, Low &lt; 30. Each component is verified below.
              </div>

              <SectionLabel>Component variables</SectionLabel>
              <div className="flex flex-col gap-2">
                {INTERVENTION_VARS.map((v) => <VerifyRow key={v.col} {...v} />)}
              </div>
            </Card>

            <Card className="gap-0 rounded-xl border p-5">
              <div className="mb-3 text-[13px] font-semibold text-foreground">Tertile split — confirmed</div>
              <div className="flex flex-col gap-2">
                {[
                  ["High",   "N = 368 · 44.6%", "g"],
                  ["Medium", "N = 298 · 36.2%", "a"],
                  ["Low",    "N = 158 · 19.2%", "r"],
                ].map(([k, v, c]) => (
                  <div key={k} className="flex items-center justify-between gap-2">
                    <span className="text-[12.5px] font-medium text-foreground">{k} engagement</span>
                    <Tag color={c}>{v}</Tag>
                  </div>
                ))}
              </div>
              <div className="mt-3 rounded-lg border border-[#97C459] bg-secondary px-3 py-2.5 text-[12px] leading-[1.5] text-[#27500A]">
                <strong>0% missing</strong> on all components — tertile cell sizes adequate for stratified estimation.
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* ════════════════════════ 5d — MISSING DATA ════════════════════════ */}
      {sub === "missing" && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
            <strong className="text-foreground">Missing data analysis &amp; imputation strategy.</strong>{" "}
            Missingness is assessed across all analysis variables, the mechanism is declared, and the imputation strategy is locked <em>before</em> any outcome data are examined.
          </div>

          <div className="grid grid-cols-2 items-start gap-4">
            {/* Left — missingness + mechanism */}
            <Card className="gap-0 rounded-xl border p-5">
              <SectionLabel>Missingness by variable</SectionLabel>
              <div className="mb-4">
                {MISSINGNESS.map((m) => <MissRow key={m.name} {...m} />)}
              </div>
              <SectionLabel>Missing data mechanism</SectionLabel>
              <div className="flex items-start gap-2.5 rounded-lg border border-[#97C459] bg-secondary px-3 py-2.5">
                <Check size={14} strokeWidth={2.5} className="mt-px flex-shrink-0 text-[#27500A]" />
                <div>
                  <div className="text-[12.5px] font-semibold text-foreground">MAR — Missing at random</div>
                  <div className="text-[12px] leading-[1.45] text-muted-foreground">
                    Missingness correlates with follow-up duration and country. Little's MCAR test p=0.031 — MCAR rejected, MAR assumed. MNAR probed via pattern-mixture in the sensitivity engine.
                  </div>
                </div>
              </div>
            </Card>

            {/* Right — imputation strategy (locked) */}
            <Card className="gap-0 rounded-xl border p-5">
              <SectionLabel>Imputation strategy — locked</SectionLabel>
              <div className="flex flex-col gap-2.5">
                {IMPUTATION.map((s) => {
                  const t = VERIFY_TONE[s.tone] ?? VERIFY_TONE.plain;
                  return (
                    <div key={s.label} className={`rounded-lg border px-3.5 py-3 ${t.wrap}`}>
                      <div className="mb-1 text-[12.5px] font-semibold text-foreground">{s.label}</div>
                      <div className="mb-2 text-[12px] leading-[1.5] text-muted-foreground">{s.desc}</div>
                      <div className="flex flex-wrap gap-1.5">
                        {s.tags.map(([c, t2]) => <Tag key={t2} color={c}>{t2}</Tag>)}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-3 rounded-lg border border-[#97C459] bg-secondary px-3 py-2.5 text-[12px] leading-[1.55] text-[#27500A]">
                <strong>Strategy locked.</strong> Assumptions queued for the sensitivity engine: MAR (Little's test), MNAR pattern-mixture, and a complete-case comparison (N=748 vs N={finalN.toLocaleString()}).
              </div>
            </Card>
          </div>
        </div>
      )}

      <InlineChatbot {...chatProps} />

    </div>
  );
}
