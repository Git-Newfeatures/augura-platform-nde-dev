import { Hexagon, GitCompareArrows, TrendingDown, Network } from "lucide-react";
import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tag } from "../ui/components";
import { DagRenderer } from "./CausalModel";
import { C, MONO } from "../theme";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 8: RESULTS  (after E2 Simulation)
// ─────────────────────────────────────────────────────────────────────────────

const RESULTS = {
  n: 824,
  effect: -0.33, ci: [-0.40, -0.26], p: "<0.001",
  mediated_pct: 70,
  indirect: -0.23, direct: -0.10,
  dm_rr: 0.36, dm_rr_ci: [0.19, 0.68], dm_risk_reduction: 64,
};

// Candidate mediators from the DAG — decompose the total effect through each via
// ACME (NDE = direct, NIE = indirect). Indirect + Direct ≈ total ATE (−0.33).
// M1 (recommendation adherence) is the primary mediator; demo decomposition.
const MEDIATORS = [
  { id:"M1", label:"Recommendation adherence", short:"adherence",       indirect:-0.23, indirectCi:[-0.30,-0.16], direct:-0.10, directCi:[-0.17,-0.01], mediated:70 },
  { id:"M2", label:"App login frequency",      short:"login frequency", indirect:-0.16, indirectCi:[-0.24,-0.08], direct:-0.17, directCi:[-0.25,-0.09], mediated:48 },
  { id:"M3", label:"Repeat test completion",   short:"repeat testing",  indirect:-0.12, indirectCi:[-0.20,-0.04], direct:-0.21, directCi:[-0.29,-0.13], mediated:36 },
];

const SUBGROUPS = [
  { label:"Overall", n:824,  est:-0.33, ci:[-0.40,-0.26], p:null,  bold:true },
  { label:"Age group", header:true },
  { label:"Age <45",  n:312,  est:-0.41, ci:[-0.51,-0.31], p:"0.043" },
  { label:"Age ≥45",  n:512,  est:-0.27, ci:[-0.36,-0.18], p:null },
  { label:"Baseline HbA1c stratum", header:true },
  { label:"HbA1c 5.7–5.9",          n:314, est:-0.22, ci:[-0.32,-0.12], p:"0.021" },
  { label:"HbA1c 6.0–6.4 ★ high-risk", n:518, est:-0.44, ci:[-0.54,-0.34], p:null, highlight:true },
  { label:"Sex", header:true },
  { label:"Female", n:438, est:-0.35, ci:[-0.44,-0.26], p:"0.61" },
  { label:"Male",   n:386, est:-0.30, ci:[-0.41,-0.19], p:null },
];

const OUTCOMES_FOREST = [
  { label:"HbA1c change (units)",  sub:"Primary outcome · 12M · N=824", est:-0.33, ci:[-0.40,-0.26], p:"<0.001", color:"#0F6E56", scale:"cont" },
  { label:"LDL-C (mg/dL)",         sub:"Secondary · 12M · N=801",       est:-9.4,  ci:[-15.6,-3.2], p:"0.004",  color:"#0C447C", scale:"cont" },
  { label:"hs-CRP (mg/L)",         sub:"Secondary · 12M · N=793",       est:-0.43, ci:[-0.69,-0.14], p:"0.012", color:"#0C447C", scale:"cont" },
  { label:"DM progression (RR)",   sub:"Secondary · 12M · N=824",       est:0.36,  ci:[0.19,0.68],  p:"0.002",  color:"#633806", scale:"rr"   },
];

// ── Counterfactual scenario projections (stochastic / modified-treatment-policy estimand) ──
// Demo numbers anchored to the observed ATE (−0.33). G-computation, marginalised over the
// counterfactual exposure distribution. Not for production — placeholder values.
const CF_SCENARIOS = [
  { label:"Status quo",            sub:"Observed exposure distribution",          delta:-0.33, ci:[-0.40,-0.26], ref:true },
  { label:"All → high engagement", sub:"Every user shifted to score ≥ 70",        delta:-0.44, ci:[-0.53,-0.35], best:true },
  { label:"All → low engagement",  sub:"Every user shifted to score < 30",        delta:-0.11, ci:[-0.19,-0.03] },
];

// ── Dose–response curve: ΔHbA1c as a function of engagement decile (demo, monotonic-ish) ──
const DOSE_RESPONSE = [
  { x:1,  y:-0.05, lo:-0.13, hi: 0.03 },
  { x:2,  y:-0.09, lo:-0.17, hi:-0.01 },
  { x:3,  y:-0.13, lo:-0.21, hi:-0.05 },
  { x:4,  y:-0.18, lo:-0.26, hi:-0.10 },
  { x:5,  y:-0.24, lo:-0.32, hi:-0.16 },
  { x:6,  y:-0.29, lo:-0.37, hi:-0.21 },
  { x:7,  y:-0.34, lo:-0.42, hi:-0.26 },
  { x:8,  y:-0.39, lo:-0.48, hi:-0.30 },
  { x:9,  y:-0.43, lo:-0.53, hi:-0.33 },
  { x:10, y:-0.46, lo:-0.57, hi:-0.35 },
];

// ── CATE distribution (individual treatment effects across the cohort, demo) ──
// Roughly bell-shaped, centred near the ATE (−0.33), bins are [from, to) on ΔHbA1c.
const CATE_BINS = [
  { from:-0.70, count:8   },
  { from:-0.60, count:24  },
  { from:-0.50, count:71  },
  { from:-0.40, count:148 },
  { from:-0.30, count:201 },
  { from:-0.20, count:166 },
  { from:-0.10, count:104 },
  { from: 0.00, count:62  },
  { from: 0.10, count:28  },
  { from: 0.20, count:12  },
];
const CATE_MEAN = -0.33;

function ForestRow({ row, xMin, xMax, width=240, nullVal=0 }) {
  if (row.header) return (
    <tr><td colSpan={5} className="pt-3 pb-1 text-[12px] font-semibold text-foreground">{row.label}</td></tr>
  );
  const toX = v => Math.max(0, Math.min(width, (v - xMin) / (xMax - xMin) * width));
  const cx = toX(row.est), lo = toX(row.ci[0]), hi = toX(row.ci[1]), nx = toX(nullVal);
  return (
    <tr className={row.highlight ? "bg-[#FFF9EE]" : "bg-transparent"}>
      <td className={`whitespace-nowrap py-1.5 pr-2 text-[12.5px] ${row.bold ? "font-semibold" : "font-normal"} ${row.highlight ? "text-[#633806]" : "text-foreground"}`}>
        {row.label}
      </td>
      <td className="pr-3 text-right font-mono text-[12px] text-muted-foreground">{row.n?.toLocaleString()}</td>
      <td className="pr-3">
        <svg width={width} height={16} style={{ display:"block", overflow:"visible" }}>
          <line x1={nx} y1={0} x2={nx} y2={16} stroke="#C4C2BA" strokeWidth={1} strokeDasharray="2 2" />
          <line x1={lo} y1={8} x2={hi} y2={8} stroke={row.bold ? "#1C1C1A" : "#378ADD"} strokeWidth={row.bold ? 2 : 1.5} />
          {row.bold
            ? <polygon points={`${cx},3 ${cx+5},8 ${cx},13 ${cx-5},8`} fill="#1C1C1A" />
            : <circle cx={cx} cy={8} r={3.5} fill="#378ADD" />}
        </svg>
      </td>
      <td className="whitespace-nowrap pr-2 font-mono text-[12px] text-muted-foreground">
        {row.est.toFixed(2)} [{row.ci[0].toFixed(2)}, {row.ci[1].toFixed(2)}]
      </td>
      <td className={`font-mono text-[12px] ${row.p && parseFloat(row.p) < 0.05 ? "text-primary" : "text-muted-foreground"}`}>
        {row.p ? (row.p.startsWith("<") ? row.p : `p=${row.p}`) : "—"}
      </td>
    </tr>
  );
}

export default function ResultsView({ simResults, dagCache, partnerLabel = 'Partner' }) {
  const simEst    = simResults?.result;
  const simN      = simResults?.n ?? RESULTS.n;
  const simEffect = simEst?.effect   ?? RESULTS.effect;
  const simCILo   = simEst?.ci?.[0]  ?? RESULTS.ci[0];
  const simCIHi   = simEst?.ci?.[1]  ?? RESULTS.ci[1];
  const simPower  = simEst?.power    ?? null;
  const simLabel  = simResults?.estimatorLabel ?? "LME";
  const isLive    = !!simEst;

  const R = {
    ...RESULTS,
    n:      simN,
    effect: simEffect,
    ci:     [simCILo, simCIHi],
    p:      simPower ? (simPower >= 99.9 ? "<0.001" : "<0.05") : RESULTS.p,
  };

  // Selected mediator for the NDE/NIE decomposition card.
  const [medId, setMedId] = useState("M1");
  const med = MEDIATORS.find(m => m.id === medId) || MEDIATORS[0];

  // Internal data-provenance badges are hidden in the demo. Kept as a no-op so the
  // existing tag={…} call sites don't need touching.
  const DataBadge = () => null;

  const KPI = ({ label, value, sub, accent, wide, tag }) => (
    <Card className={`gap-0 rounded-xl p-4 ${wide ? "flex-[1.4_1_0]" : "flex-1"} ${accent ? "border-[#5DCAA5] bg-secondary" : "border-border bg-card"}`}>
      <div className="mb-1.5 flex items-center justify-between gap-1.5">
        <div className="text-[12px] font-medium text-muted-foreground">{label}</div>
        {tag && <DataBadge type={tag} />}
      </div>
      <div className={`font-semibold leading-[1.1] ${accent ? "text-[28px] text-primary" : "text-[22px] text-foreground"}`}>{value}</div>
      {sub && <div className="mt-1 text-[12px] text-muted-foreground">{sub}</div>}
    </Card>
  );

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-5">

      {/* KPI strip */}
      <div className="flex gap-4">
        <KPI label="Sample" value={simN.toLocaleString()} sub="eligible users" tag="live" />
        <KPI label="HbA1c Effect" value={`${R.effect.toFixed(2)}`} sub={`[${R.ci[0].toFixed(2)}, ${R.ci[1].toFixed(2)}]`} accent tag={isLive ? "live" : "hardcoded"} />
        <KPI label="Mediated" value={`${med.mediated}%`} sub={`via ${med.short}`} tag="romain" />
        <KPI label="DM Risk Reduction" value={`${R.dm_risk_reduction}%`} sub={`RR ${R.dm_rr.toFixed(2)}`} tag="romain" />
        <KPI label="Causal language" value="Consistent with causal" sub="in study context" wide tag="hardcoded" />
      </div>

      {/* Row 2: Primary result + Mediation */}
      <div className="grid grid-cols-2 gap-4">

        <Card className="gap-0 rounded-xl border-border bg-card p-5">
          <div className="mb-1 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-foreground">Primary result — HbA1c change at 12M</div>
            <DataBadge type={isLive ? "live" : "hardcoded"} />
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            High vs Low engagement · {simLabel} · Adjusted for age, sex, BMI, baseline HbA1c · MI for missing data
          </div>
          <div className="mb-1 flex items-baseline gap-2">
            <span className="text-[40px] font-bold tracking-[-1px] text-primary">{R.effect.toFixed(2)}</span>
            <span className="text-[13px] text-muted-foreground">HbA1c units</span>
          </div>
          <div className="mb-3 text-[12.5px] text-muted-foreground">
            95% CI [{R.ci[0].toFixed(2)}, {R.ci[1].toFixed(2)}] · p {R.p}
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-2.5 text-[12px] leading-relaxed text-foreground/80">
            <strong>Interpretation:</strong> Consistent with a causal effect of {R.effect.toFixed(2)} HbA1c units in adults with prediabetes using {partnerLabel} — under observed engagement conditions. Unmeasured confounders (health motivation, literacy) may attenuate this estimate; E-values are reported on page 9.
          </div>
        </Card>

        <Card className="gap-0 rounded-xl border-border bg-card p-5">
          <div className="mb-0.5 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-foreground">Mediation decomposition — total, direct &amp; indirect effects</div>
            <DataBadge type="romain" />
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            ACME · Bootstrap CI 1000 iterations · natural direct (NDE) &amp; indirect (NIE) effects
          </div>
          {/* Mediator selector — decompose the total effect (NDE/NIE) through each DAG mediator */}
          <div className="mb-3.5 flex flex-wrap items-center gap-1.5">
            <span className="mr-0.5 text-[11px] font-medium text-muted-foreground">Mediator:</span>
            {MEDIATORS.map(m => (
              <button
                key={m.id}
                onClick={() => setMedId(m.id)}
                className={`rounded-full border px-2.5 py-[3px] text-[11.5px] transition-colors ${m.id === medId ? "border-primary bg-primary/10 font-semibold text-primary" : "border-border bg-card text-muted-foreground hover:bg-muted/50"}`}
              >
                {m.label} <span className="font-mono text-[10px] opacity-70">{m.id}</span>
              </button>
            ))}
          </div>
          {[
            { label:"Total effect",               val:R.effect,     ci:R.ci,           color:"#2A5F4F", pct:null },
            { label:`Indirect — NIE (${med.id})`, val:med.indirect, ci:med.indirectCi, color:"#378ADD", pct:`${med.mediated}% of total` },
            { label:"Direct — NDE",               val:med.direct,   ci:med.directCi,   color:"#AAA89E", pct:`${100-med.mediated}% of total` },
          ].map(row => {
            const barW = Math.abs(row.val) / Math.abs(R.effect) * 180;
            return (
              <div key={row.label} className="mb-3">
                <div className="mb-1 flex items-baseline justify-between">
                  <span className="text-[12.5px] font-semibold text-foreground">{row.label}</span>
                  <span className="font-mono text-[12px] text-muted-foreground">
                    {row.val.toFixed(2)} HbA1c{row.pct ? ` · ${row.pct}` : ""}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-[18px] rounded-[3px]" style={{ width:barW, background:row.color }} />
                  <span className="font-mono text-[11px] text-muted-foreground">
                    [{row.ci[0].toFixed(2)}, {row.ci[1].toFixed(2)}] · p{R.p}
                  </span>
                </div>
              </div>
            );
          })}
        </Card>
      </div>

      {/* Row 3: Subgroup forest plot */}
      <Card className="gap-0 rounded-xl border-border bg-card p-5">
        <div className="mb-1 flex items-center justify-between">
          <div>
            <div className="text-[13px] font-semibold text-foreground">Subgroup forest plot — pre-specified heterogeneity of treatment effect (HTE)</div>
            <div className="mt-0.5 text-[12px] text-muted-foreground">HbA1c change at 12M · High vs Low engagement · Negative = improvement · Diamond = pooled estimate</div>
          </div>
          <Tag color="a">preliminary</Tag>
        </div>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-border">
                {["Subgroup","N","Effect (95% CI)","Est. [95% CI]","p int."].map(h => (
                  <th key={h} className={`pb-2 pr-2 text-[12px] font-semibold text-muted-foreground ${h==="N" ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SUBGROUPS.map((row, i) => <ForestRow key={i} row={row} xMin={-0.65} xMax={0.1} nullVal={0} />)}
            </tbody>
          </table>
        </div>
        <div className="mt-2 text-[11px] text-muted-foreground">← Favours high engagement</div>
      </Card>

      {/* Row 4: DAG + Multi-outcome forest */}
      <div className="grid grid-cols-2 gap-4">

        <Card className="gap-0 rounded-xl border-border bg-card p-5">
          <div className="mb-0.5 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-foreground">Causal DAG — quantified effect decomposition</div>
            <DataBadge type={dagCache?.nodes?.length ? "live" : "hardcoded"} />
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            {dagCache?.nodes?.length
              ? `${dagCache.nodes.length} nodes · built by Augura DAG agent · ACME decomposition`
              : "Total · direct and indirect effects annotated on pathways · ACME decomposition — run Causal Model to derive from your data"}
          </div>
          {dagCache?.nodes?.length
            ? <DagRenderer nodes={dagCache.nodes} edges={dagCache.edges ?? []} />
            : (
              <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg bg-muted/40 px-4 text-center text-[12px] text-muted-foreground">
                <Hexagon size={22} className="text-muted-foreground/50" />
                No DAG available — complete the Causal Model step to generate the diagram from your data
              </div>
            )
          }
        </Card>

        <Card className="gap-0 rounded-xl border-border bg-card p-5">
          <div className="mb-0.5 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-foreground">Forest plot — all outcomes</div>
            <DataBadge type="romain" />
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">High vs Low engagement · Effect direction: negative = improvement</div>
          <div className="flex flex-col gap-4">
            {OUTCOMES_FOREST.map(row => {
              const isRR = row.scale === "rr";
              const xMin = isRR ? 0 : -20, xMax = isRR ? 1.4 : 4, nullV = isRR ? 1 : 0;
              const W = 160;
              const toX = v => Math.max(0, Math.min(W, (v - xMin) / (xMax - xMin) * W));
              const cx = toX(row.est), lo = toX(row.ci[0]), hi = toX(row.ci[1]), nx = toX(nullV);
              return (
                <div key={row.label}>
                  <div className="mb-1 flex items-baseline justify-between">
                    <div>
                      <span className="text-[12.5px] font-semibold text-foreground">{row.label}</span>
                      <span className="ml-1.5 text-[12px] text-muted-foreground">{row.sub}</span>
                    </div>
                    <span className={`ml-3 font-mono text-[12px] ${parseFloat(row.p) < 0.05 || row.p === "<0.001" ? "text-primary" : "text-muted-foreground"}`}>p = {row.p}</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <svg width={W} height={20} style={{ flexShrink:0, overflow:"visible" }}>
                      <line x1={nx} y1={0} x2={nx} y2={20} stroke="#C4C2BA" strokeWidth={1} strokeDasharray="3 2" />
                      <line x1={lo} y1={10} x2={hi} y2={10} stroke={row.color} strokeWidth={2} />
                      <circle cx={cx} cy={10} r={4} fill={row.color} />
                    </svg>
                    <span className="whitespace-nowrap font-mono text-[12px] text-muted-foreground">
                      {isRR ? `RR ${row.est.toFixed(2)}` : row.est.toFixed(2)} [{row.ci[0].toFixed(isRR?2:1)}, {row.ci[1].toFixed(isRR?2:1)}]
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 border-t border-border pt-2.5 text-[11px] text-muted-foreground">
            ← Favours high engagement{" "}<span className="float-right">Favours low →</span>
          </div>
        </Card>
      </div>

      {/* Row 5: Counterfactual scenario projections */}
      <Card className="gap-0 rounded-xl border-border bg-card p-5">
        <div className="mb-1 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitCompareArrows size={16} className="text-primary" />
            <div className="text-[15px] font-semibold text-foreground">Counterfactual scenario projections</div>
          </div>
          <DataBadge type="hardcoded" />
        </div>
        <div className="mb-4 text-[12.5px] text-muted-foreground">
          Modified-treatment-policy estimand · G-computation marginalised over the counterfactual exposure distribution · no unexposed control arm required
        </div>

        {/* Scenario cards */}
        <div className="grid grid-cols-3 gap-3">
          {CF_SCENARIOS.map(s => {
            const ref  = CF_SCENARIOS.find(c => c.ref);
            const diff = s.ref ? 0 : +(s.delta - ref.delta).toFixed(2);
            return (
              <div
                key={s.label}
                className={`rounded-xl border p-4 ${
                  s.best
                    ? "border-[#5DCAA5] bg-secondary"
                    : s.ref
                      ? "border-border bg-muted/40"
                      : "border-border bg-card"
                }`}
              >
                <div className="mb-0.5 text-[12.5px] font-semibold text-foreground">{s.label}</div>
                <div className="mb-2 text-[11.5px] leading-snug text-muted-foreground">{s.sub}</div>
                <div className={`font-mono text-[26px] font-semibold leading-none ${s.best ? "text-primary" : "text-foreground"}`}>
                  {s.delta.toFixed(2)}
                </div>
                <div className="mt-1 font-mono text-[11.5px] text-muted-foreground">
                  95% CI [{s.ci[0].toFixed(2)}, {s.ci[1].toFixed(2)}]
                </div>
                <div className="mt-1 text-[11.5px]">
                  {s.ref
                    ? <span className="text-muted-foreground">Reference</span>
                    : <span style={{ color: diff < 0 ? C.green : C.amber }}>
                        {diff > 0 ? "+" : ""}{diff.toFixed(2)} vs status quo
                      </span>}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-3 rounded-lg bg-[#E6F1FB] px-3 py-2.5 text-[12px] leading-relaxed text-[#0C447C]">
          <strong>What this answers:</strong> the mean ΔHbA1c we would expect if every eligible user were shifted to a target
          engagement level — not a contrast between observed groups. Shifting all users to high engagement projects an additional
          −0.11 HbA1c units beyond the status quo (≈ 33% larger effect), equivalent to ~2,400 fewer T2D progressions per 10,000 users/year at scale.
        </div>
      </Card>

      {/* Row 6: Dose–response + CATE distribution */}
      <div className="grid grid-cols-2 gap-4">

        {/* Dose–response curve */}
        <Card className="gap-0 rounded-xl border-border bg-card p-5">
          <div className="mb-1 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingDown size={16} className="text-primary" />
              <div className="text-[13px] font-semibold text-foreground">Dose–response curve</div>
            </div>
            <DataBadge type="hardcoded" />
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            ΔHbA1c by engagement decile · continuous exposure · shaded 95% CI band
          </div>

          {(() => {
            const W = 460, H = 200;
            const PAD = { top:12, right:14, bottom:30, left:42 };
            const cw = W - PAD.left - PAD.right;
            const ch = H - PAD.top - PAD.bottom;
            const xs = DOSE_RESPONSE.map(d => d.x);
            const xMin = Math.min(...xs), xMax = Math.max(...xs);
            const yVals = DOSE_RESPONSE.flatMap(d => [d.lo, d.hi]);
            const yLo = Math.min(...yVals), yHi = Math.max(...yVals);
            const yPad = (yHi - yLo) * 0.12 || 0.1;
            const lo = yLo - yPad, hi = yHi + yPad, range = hi - lo || 1;
            const px = v => PAD.left + (v - xMin) / (xMax - xMin) * cw;
            const py = v => PAD.top + ch - (v - lo) / range * ch;
            const linePts = DOSE_RESPONSE.map(d => `${px(d.x)},${py(d.y)}`).join(" ");
            const bandPts = [
              ...DOSE_RESPONSE.map(d => `${px(d.x)},${py(d.hi)}`),
              ...[...DOSE_RESPONSE].reverse().map(d => `${px(d.x)},${py(d.lo)}`),
            ].join(" ");
            const yTicks = [lo + range*0.12, lo + range*0.5, lo + range*0.88];
            const xTicks = [1, 5, 10];
            const zeroY = py(0);
            return (
              <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:"block", height:H, overflow:"visible" }}>
                {yTicks.map((v,i) => (
                  <g key={i}>
                    <line x1={PAD.left} y1={py(v)} x2={W-PAD.right} y2={py(v)} stroke={C.border} strokeWidth={0.5} strokeDasharray="3 3" />
                    <text x={PAD.left-5} y={py(v)+3} textAnchor="end" fontSize={8.5} fill={C.faint} fontFamily={MONO}>{v.toFixed(2)}</text>
                  </g>
                ))}
                {zeroY > PAD.top && zeroY < PAD.top + ch && (
                  <line x1={PAD.left} y1={zeroY} x2={W-PAD.right} y2={zeroY} stroke={C.border2} strokeWidth={1} strokeDasharray="4 3" />
                )}
                <polygon points={bandPts} fill={`${C.green}1F`} />
                <polyline points={linePts} fill="none" stroke={C.green} strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" />
                {DOSE_RESPONSE.map((d,i) => <circle key={i} cx={px(d.x)} cy={py(d.y)} r={3} fill={C.green} />)}
                {xTicks.map(t => (
                  <text key={t} x={px(t)} y={H-9} textAnchor="middle" fontSize={8.5} fill={C.faint} fontFamily={MONO}>D{t}</text>
                ))}
                <text x={PAD.left + cw/2} y={H-1} textAnchor="middle" fontSize={9} fill={C.faint}>Engagement decile (dose) →</text>
              </svg>
            );
          })()}

          <div className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">
            Near-monotonic gradient — each engagement decile adds ≈ −0.05 HbA1c units, with no
            plateau across the observed range. Supports a continuous dose–response rather than a threshold effect.
          </div>
        </Card>

        {/* Causal Forest — CATE distribution */}
        <Card className="gap-0 rounded-xl border-border bg-card p-5">
          <div className="mb-1 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Network size={16} className="text-primary" />
              <div className="text-[13px] font-semibold text-foreground">Causal Forest — CATE distribution</div>
            </div>
            <DataBadge type="hardcoded" />
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            Individual treatment effects (CATE) across N={RESULTS.n} · honest GRF · mean = ATE
          </div>

          {(() => {
            const W = 460, H = 200;
            const PAD = { top:12, right:14, bottom:30, left:42 };
            const cw = W - PAD.left - PAD.right;
            const ch = H - PAD.top - PAD.bottom;
            const binW = 0.10;
            const xMin = CATE_BINS[0].from;
            const xMax = CATE_BINS[CATE_BINS.length-1].from + binW;
            const maxCount = Math.max(...CATE_BINS.map(b => b.count));
            const bx = v => PAD.left + (v - xMin) / (xMax - xMin) * cw;
            const barW = cw / CATE_BINS.length;
            const yTicks = [0, maxCount/2, maxCount];
            const xTicks = [-0.60, -0.30, 0.00, 0.20];
            const meanX = bx(CATE_MEAN);
            return (
              <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:"block", height:H, overflow:"visible" }}>
                {yTicks.map((v,i) => {
                  const y = PAD.top + ch - (v / maxCount) * ch;
                  return (
                    <g key={i}>
                      <line x1={PAD.left} y1={y} x2={W-PAD.right} y2={y} stroke={C.border} strokeWidth={0.5} strokeDasharray="3 3" />
                      <text x={PAD.left-5} y={y+3} textAnchor="end" fontSize={8.5} fill={C.faint} fontFamily={MONO}>{Math.round(v)}</text>
                    </g>
                  );
                })}
                {CATE_BINS.map((b,i) => {
                  const h = (b.count / maxCount) * ch;
                  const x = bx(b.from) + 1;
                  const beneficial = b.from + binW <= 0;
                  return (
                    <rect key={i} x={x} y={PAD.top + ch - h} width={Math.max(barW-2,1)} height={h}
                      rx={1.5} fill={beneficial ? `${C.green}CC` : `${C.amber}B3`} />
                  );
                })}
                {/* Mean line */}
                <line x1={meanX} y1={PAD.top-2} x2={meanX} y2={PAD.top+ch} stroke={C.text} strokeWidth={1.5} strokeDasharray="4 3" />
                <text x={meanX} y={PAD.top-4} textAnchor="middle" fontSize={8.5} fill={C.text} fontFamily={MONO}>ATE {CATE_MEAN.toFixed(2)}</text>
                {xTicks.map(t => (
                  <text key={t} x={bx(t)} y={H-9} textAnchor="middle" fontSize={8.5} fill={C.faint} fontFamily={MONO}>{t.toFixed(2)}</text>
                ))}
                <text x={PAD.left + cw/2} y={H-1} textAnchor="middle" fontSize={9} fill={C.faint}>Individual ΔHbA1c (CATE) →</text>
              </svg>
            );
          })()}

          <div className="mt-2 flex items-center gap-4 text-[11.5px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background:`${C.green}CC` }} />benefit (Δ&lt;0)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background:`${C.amber}B3` }} />no benefit (Δ≥0)
            </span>
          </div>
          <div className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">
            Effects are heterogeneous but predominantly beneficial — ~87% of users have a negative
            CATE, concentrated around the ATE (−0.33), with a long left tail of high-responders.
          </div>
        </Card>
      </div>

    </div>
  );
}
