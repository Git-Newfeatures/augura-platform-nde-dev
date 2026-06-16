import { useState } from "react";
import { ChevronRight, Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { SubTabs } from "@/cockpit/SubTabs";
import { InfoBar, Radar, IntelRow, IntelBlock } from "../ui/components";
import InlineChatbot from "../components/InlineChatbot";
import { C, MONO } from "../theme";

// ── Engagement-profile demo data (offline / demo only) ────────────────────────
// Variables the agent mapped to engagement concepts — all confirmed by the user.
const ENGAGEMENT_VARS = [
  { name: "Composite engagement score", col: "engagement_score",   concept: "Composite engagement", primary: true  },
  { name: "App login frequency (monthly)", col: "logins_per_month", concept: "Frequency" },
  { name: "Recommendation adherence rate", col: "rec_adherence_pct", concept: "Adherence" },
  { name: "Repeat test completion (≥2 tests)", col: "repeat_test_flag", concept: "Retention" },
];

// Mean composite engagement score by cohort follow-up month (0–100), gentle uptrend.
const ENGAGEMENT_TREND = [
  { m: "M0",  v: 48 }, { m: "M1",  v: 51 }, { m: "M2",  v: 53 }, { m: "M3",  v: 52 },
  { m: "M4",  v: 55 }, { m: "M5",  v: 57 }, { m: "M6",  v: 58 }, { m: "M7",  v: 60 },
  { m: "M8",  v: 59 }, { m: "M9",  v: 62 }, { m: "M10", v: 63 }, { m: "M11", v: 64 },
];

// Baseline engagement distribution — tertile buckets at study entry (N=824).
const ENGAGEMENT_DIST = [
  { label: "Low\n(<30)",    count: 158, color: C.amber },
  { label: "Medium\n(30–70)", count: 298, color: C.blue },
  { label: "High\n(>70)",   count: 368, color: C.green },
];

// ── Inline line chart (engagement over time) — matches MonitoringView/MiniChart ─
function EngagementTrendChart({ data, color = C.green, height = 150 }) {
  const W = 320, H = height;
  const PAD = { top: 10, right: 10, bottom: 22, left: 30 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  const vals = data.map((d) => d.v);
  const rawLo = Math.min(...vals);
  const rawHi = Math.max(...vals);
  const pad = (rawHi - rawLo) * 0.25 || 5;
  const lo = Math.max(0, rawLo - pad);
  const hi = rawHi + pad;
  const range = hi - lo || 1;

  const px = (i) => PAD.left + (i / Math.max(data.length - 1, 1)) * cw;
  const py = (v) => PAD.top + ch - ((v - lo) / range) * ch;

  const pts = data.map((d, i) => `${px(i)},${py(d.v)}`).join(" ");
  const fillPts = `${PAD.left},${PAD.top + ch} ${pts} ${PAD.left + cw},${PAD.top + ch}`;
  const yTicks = [lo + range * 0.1, lo + range * 0.5, lo + range * 0.9];
  const xLabels = [0, Math.floor((data.length - 1) / 2), data.length - 1];

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", height: H, overflow: "visible" }}>
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PAD.left} y1={py(v)} x2={W - PAD.right} y2={py(v)}
            stroke={C.border} strokeWidth={0.5} strokeDasharray="3 3" />
          <text x={PAD.left - 4} y={py(v) + 3} textAnchor="end"
            fontSize={7.5} fill={C.faint} fontFamily={MONO}>
            {Math.round(v)}
          </text>
        </g>
      ))}
      <polygon points={fillPts} fill={`${color}1A`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2}
        strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => (
        <circle key={i} cx={px(i)} cy={py(d.v)} r={2.5} fill={color} />
      ))}
      {xLabels.map((i) => (
        <text key={i} x={px(i)} y={H - 4} textAnchor="middle"
          fontSize={7.5} fill={C.faint} fontFamily={MONO}>
          {data[i].m}
        </text>
      ))}
    </svg>
  );
}

// ── Inline bar histogram (baseline engagement distribution) ───────────────────
function EngagementDistChart({ data, height = 150 }) {
  const W = 320, H = height;
  const PAD = { top: 12, right: 10, bottom: 30, left: 30 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  const maxV = Math.max(...data.map((d) => d.count)) || 1;
  const py = (v) => PAD.top + ch - (v / maxV) * ch;
  const slot = cw / data.length;
  const barW = slot * 0.52;
  const yTicks = [0, maxV * 0.5, maxV];

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", height: H, overflow: "visible" }}>
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PAD.left} y1={py(v)} x2={W - PAD.right} y2={py(v)}
            stroke={C.border} strokeWidth={0.5} strokeDasharray="3 3" />
          <text x={PAD.left - 4} y={py(v) + 3} textAnchor="end"
            fontSize={7.5} fill={C.faint} fontFamily={MONO}>
            {Math.round(v)}
          </text>
        </g>
      ))}
      {data.map((d, i) => {
        const cx = PAD.left + slot * i + slot / 2;
        const y = py(d.count);
        return (
          <g key={i}>
            <rect x={cx - barW / 2} y={y} width={barW} height={PAD.top + ch - y}
              rx={3} fill={d.color} opacity={0.9} />
            <text x={cx} y={y - 4} textAnchor="middle"
              fontSize={8} fontWeight={600} fill={C.sub} fontFamily={MONO}>
              {d.count}
            </text>
            {d.label.split("\n").map((line, li) => (
              <text key={li} x={cx} y={H - 16 + li * 9} textAnchor="middle"
                fontSize={7.5} fill={C.faint} fontFamily={MONO}>
                {line}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 1: PRODUCT PROFILE
// ─────────────────────────────────────────────────────────────────────────────
export default function ProductProfile({ e1Profile, partnerLabel = 'Partner', benchmarkMeta = null, chatProps = {} }) {
  const [sub, setSub] = useState("product");
  // Scores are 0–5 natively from the agent; legacy/dev fixtures may still be 0–100,
  // so auto-detect: anything >5 is treated as a 0–100 value and scaled down.
  const to5 = (s) => {
    const v = typeof s === "number" ? (s > 5 ? s / 20 : s) : 0;
    return Math.min(5, Math.max(0, Math.round(v * 10) / 10));
  };

  const highRisks    = e1Profile ? e1Profile.risk_dimensions?.filter(d=>d.score>=4).length ?? 3 : 3;
  const medRisks     = e1Profile ? e1Profile.risk_dimensions?.filter(d=>d.score>=2&&d.score<4).length ?? 3 : 3;
  const opps         = e1Profile ? e1Profile.opportunity_dimensions?.filter(d=>d.score>=4).length ?? 5 : 5;

  const riskScores = e1Profile?.risk_dimensions?.slice(0,6).map(d=>to5(d.score)) || [2,4,4,3,3,4];
  const oppScores  = e1Profile?.opportunity_dimensions?.slice(0,6).map(d=>to5(d.score)) || [5,3,4,3,3,4];

  const agentSummary = e1Profile?.agent_reasoning || null;

  // Top-N dimension names for the executive summaries — driven by agent output
  const topRisks = (e1Profile?.risk_dimensions || [])
    .slice().sort((a,b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0,2).map(d => d.name).filter(Boolean);
  const topOpps  = (e1Profile?.opportunity_dimensions || [])
    .slice().sort((a,b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0,2).map(d => d.name).filter(Boolean);
  return (
    <div className="flex flex-col gap-4">
      <SubTabs
        tabs={[
          { id: "product", label: "Product profile" },
          { id: "engagement", label: "Engagement profile" },
        ]}
        active={sub}
        onChange={setSub}
      />

      {sub === "product" && (
      <>
      <InfoBar sources={["MAUDE","PubMed","ClinicalTrials.gov","FDA Guidance"]}>
        <strong>Product-level profile.</strong> Benchmarked against comparable preventive health products in the Augura corpus. Scores reflect existing evidence, regulatory standing, and safety signals — independent of any planned study.
      </InfoBar>

      {/* Agent reasoning — surfaced from e1Profile.agent_reasoning */}
      {agentSummary && (
        <Card className="gap-0 rounded-xl p-5">
          <div className="mb-2.5 text-[13px] font-semibold text-foreground">
            Agent reasoning
          </div>
          <div className="text-[12.5px] leading-relaxed text-foreground/80">
            {agentSummary}
          </div>
        </Card>
      )}

      {/* How the benchmark is defined — proximity & exclusion criteria */}
      <Card className="gap-0 rounded-xl p-5">
        <div className="mb-2.5 text-[13px] font-semibold text-foreground">
          About the benchmark
        </div>
        <div className="mb-4 text-[12.5px] leading-relaxed text-foreground/80">
          The comparator set is built from products in the Augura corpus that match {partnerLabel} on
          three proximity dimensions: <strong>indication</strong> ({benchmarkMeta?.indication ?? 'same clinical domain'}),
          <strong> modality</strong> (digital therapeutic, SaMD, or consumer wellness software), and
          <strong> regulatory class</strong> (CE Class I / FDA general wellness or equivalent).
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="mb-1.5 text-[12px] font-semibold text-primary">
              Included
            </div>
            <div className="text-[12px] leading-relaxed text-muted-foreground">
              {benchmarkMeta?.included ?? 'Products matching the clinical indication, modality, and regulatory class of this product.'}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[12px] font-semibold text-[#B98900]">
              Excluded
            </div>
            <div className="text-[12px] leading-relaxed text-muted-foreground">
              {benchmarkMeta?.excluded ?? 'Products outside the clinical domain, modality, or regulatory class.'}
            </div>
          </div>
        </div>
      </Card>

      {/* Benchmarking title + 3 radars */}
      <div>
        <div className="mb-3.5 text-[13px] font-semibold text-foreground">
          Benchmarking
        </div>
        <div className="grid grid-cols-2 items-stretch gap-4">
          <Card className="gap-0 rounded-xl p-5">
            <div className="mb-1 text-[15px] font-semibold text-foreground">Risk profile</div>
            <div className="mb-3 text-[12px] text-muted-foreground">{`Risks inherent to ${partnerLabel}.`} Higher = higher risk. /5.</div>
            <div className="flex justify-center">
              <Radar size={220}
                labels={["Safety\nsignals","Generalizability\n& equity","Implementation\nrisk","Actionability\nlinkage","Scalability\n& market","Reproducibility\n& evidence"]}
                maxVal={5}
                datasets={[
                  { data:riskScores, stroke:"#E24B4A" },
                ]}
              />
            </div>
            <div className="mb-3 rounded-lg border border-border bg-[#FBF4F4] px-3 py-2.5 text-[12px] leading-relaxed text-foreground/80">
              <strong className="text-[#A03A39]">Summary —</strong> {highRisks} high-risk and {medRisks} medium-risk
              dimensions identified by the agent.
              {topRisks.length > 0 && <> Largest exposures: <em>{topRisks.join(", ")}</em>.</>}
            </div>
            <div className="mb-2 flex items-center gap-1 text-[11px] text-muted-foreground">
              <ChevronRight size={12} /> Click any row for engine intelligence
            </div>
            <table className="w-full border-collapse">
              <thead><tr>
                {["Dimension","Score"].map(h=>(
                  <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-semibold text-muted-foreground">{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {(e1Profile?.risk_dimensions?.length > 0
                  ? e1Profile.risk_dimensions.slice(0,6)
                  : [
                      {name:"Safety Signals & Failure Modes",               score:2,  rationale:"MAUDE search across SaMD/DTx category terms: low adverse event rate — 3 incidents across 9 comparable preventive digital health products, all lab sample handling. No FDA recalls identified for analogous consumer wellness software."},
                      {name:"Generalizability, Equity & Robustness Risk",  score:4,  rationale:"External validation on diverse populations is limited. Existing studies concentrate on high-SES employer cohorts; ethnic and geographic diversity underrepresented. No independent external validation published for comparable EU preventive platforms."},
                      {name:"Implementation & Adoption Risk",               score:4,  rationale:"PubMed literature on digital therapeutics shows median 12-week engagement drop-off of 40–60%. Alert fatigue documented in comparable recommendation-based platforms. Real-world adherence likely lower than study conditions."},
                      {name:"Limited Actionability & Intervention Linkage", score:3,  rationale:`Recommendation specificity varies across ${partnerLabel} modules. PubMed review of ClinicalTrials intervention arms shows protocolized arms outperform vague lifestyle advice. Clear downstream clinical action pathway needed for payer acceptance.`},
                      {name:"Limited Scalability & Market Breadth",         score:3,  rationale:"Target population (prediabetes + preventive health, employer channel) is large but access depends on B2B contracting. ClinicalTrials site diversity for comparable products is primarily urban/academic. FDA indications for wellness SaMD remain broad."},
                      {name:"Limited Reproducibility & Consistency of Evidence", score:4, rationale:`Effect sizes for digital health engagement interventions are heterogeneous across studies. PubMed meta-analyses show wide CI bands. Independent team replications rare — most evidence is single-team. ${partnerLabel} has no independent external validation yet.`},
                    ]
                ).map((d,i) => {
                  const score = to5(typeof d.score === "number" ? d.score : 60);
                  return (
                    <IntelRow key={i} label={d.name} score={score} scoreColor="#E24B4A" max={5}>
                      <IntelBlock label="Agent finding">{d.rationale}</IntelBlock>
                    </IntelRow>
                  );
                })}
              </tbody>
            </table>
          </Card>

          <Card className="gap-0 rounded-xl p-5">
            <div className="mb-1 text-[15px] font-semibold text-foreground">Opportunity profile</div>
            <div className="mb-3 text-[12px] text-muted-foreground">Independently scored opportunities. Higher = stronger. /5.</div>
            <div className="flex justify-center">
              <Radar size={220}
                labels={["Clinical\nneed","Evidence\nstrength","Effect\nsize","Actionability\nlinkage","Reproducibility","Regulatory\npathway"]}
                maxVal={5}
                datasets={[
                  { data:oppScores, stroke:"#1D9E75" },
                ]}
              />
            </div>
            <div className="mb-3 rounded-lg border border-border bg-[#F2F8F4] px-3 py-2.5 text-[12px] leading-relaxed text-foreground/80">
              <strong className="text-[#1D6E55]">Summary —</strong> {opps} dimensions score in the upper range.
              {topOpps.length > 0 && <> Strongest pillars: <em>{topOpps.join(", ")}</em>.</>}
            </div>
            <div className="mb-2 flex items-center gap-1 text-[11px] text-muted-foreground">
              <ChevronRight size={12} /> Click any row for engine intelligence
            </div>
            <table className="w-full border-collapse">
              <thead><tr>
                {["Dimension","Score"].map(h=>(
                  <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-semibold text-muted-foreground">{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {(e1Profile?.opportunity_dimensions?.length > 0
                  ? e1Profile.opportunity_dimensions.slice(0,6)
                  : [
                      {name:"Clinical Need & Indication Strength",       score:5, rationale:"Prediabetes and cardiometabolic risk represent a major disease burden — 374M adults globally with IFG/IGT (IDF 2021). HbA1c monitoring and lifestyle intervention are first-line standard of care but largely underprovided; digital platforms address a clear unmet gap in scalable preventive care."},
                      {name:"Evidence Strength & Credibility",           score:3,  rationale:`The 701-document corpus contains 286 prospective or RCT designs (41%); however most digital preventive health evidence is observational or pre-post. True RCT evidence for ${partnerLabel}-type platforms remains sparse relative to pharmacological comparators.`},
                      {name:"Effect Size & Outcome Impact Signal",       score:4,  rationale:"HbA1c reductions of 0.3–0.5% in high-engagement digital cohorts are clinically meaningful (comparable to first-line metformin threshold for HAS reimbursement). LDL and hs-CRP secondary signals add cardiovascular credibility."},
                      {name:"Actionability & Intervention Linkage",      score:3,  rationale:"Recommendation modules are linked to measurable behaviour change targets. However PubMed review shows protocolized interventions (structured recommendation algorithms) outperform vague lifestyle advice by 2× in comparable platforms. Protocol specificity can be strengthened."},
                      {name:"Reproducibility & Consistency of Evidence", score:3,  rationale:"Results are directionally consistent across the corpus but effect size heterogeneity is substantial (I² >60% in comparable meta-analyses). Independent replication by external teams remains limited; most evidence is generated by product-affiliated research groups."},
                      {name:"Regulatory & Reimbursement Pathway Clarity",score:4,  rationale:"DiGA (Germany) offers the fastest pathway — Lykon DE precedent with provisional listing achievable within 12 months. EU MDR Art. 22 wellness and HAS DSN apply; HAS requires at least one prospective study for reimbursement. Multiple viable pathways confirmed."},
                    ]
                ).map((d,i) => {
                  const score = to5(typeof d.score === "number" ? d.score : 60);
                  return (
                    <IntelRow key={i} label={d.name} score={score} scoreColor="#1D9E75" max={5}>
                      <IntelBlock label="Agent finding">{d.rationale}</IntelBlock>
                    </IntelRow>
                  );
                })}
              </tbody>
            </table>
          </Card>

        </div>
      </div>
      </>
      )}

      {sub === "engagement" && (
      <>
      <InfoBar sources={["Lucis dataset","Benchmark corpus"]}>
        <strong>Engagement profile.</strong> Augura identified engagement variables in the Lucis dataset through conversational prompting. Column names were mapped to engagement concepts and confirmed by the user. Temporal trend and baseline distribution are shown below.
      </InfoBar>

      {/* Engagement variable mapping — agent-confirmed */}
      <Card className="gap-0 rounded-xl p-5">
        <div className="mb-1 text-[15px] font-semibold text-foreground">Engagement variables</div>
        <div className="mb-3.5 text-[12px] text-muted-foreground">
          Agent-proposed mappings from dataset column names to engagement concepts. The user confirmed each.
        </div>
        <table className="w-full border-collapse">
          <thead><tr>
            {["Variable","Column","Concept","Status"].map(h=>(
              <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-semibold text-muted-foreground">{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {ENGAGEMENT_VARS.map((v) => (
              <tr key={v.col} className="border-b border-border/60 last:border-0">
                <td className="px-2 py-2.5 text-[12.5px] font-medium text-foreground">{v.name}</td>
                <td className="px-2 py-2.5">
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{v.col}</code>
                </td>
                <td className="px-2 py-2.5 text-[12px] text-foreground/80">
                  {v.concept}
                  {v.primary && <span className="ml-1.5 text-[11px] font-medium text-primary">· primary</span>}
                </td>
                <td className="px-2 py-2.5">
                  <span className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-secondary/50 px-2 py-0.5 text-[11px] font-medium text-primary">
                    <Check size={12} /> confirmed
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Temporal trend + baseline distribution */}
      <div className="grid grid-cols-2 items-stretch gap-4">
        <Card className="gap-0 rounded-xl p-5">
          <div className="mb-1 text-[15px] font-semibold text-foreground">Engagement over time</div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            Mean composite engagement score by cohort follow-up month · 12-month window.
          </div>
          <EngagementTrendChart data={ENGAGEMENT_TREND} />
        </Card>

        <Card className="gap-0 rounded-xl p-5">
          <div className="mb-1 text-[15px] font-semibold text-foreground">Baseline engagement distribution</div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            Users by engagement tertile at study entry · N = 824.
          </div>
          <EngagementDistChart data={ENGAGEMENT_DIST} />
        </Card>
      </div>
      </>
      )}

      {/* Inline chatbot */}
      <InlineChatbot {...chatProps} />
    </div>
  );
}
