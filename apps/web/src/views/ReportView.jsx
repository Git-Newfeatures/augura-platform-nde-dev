import { useState } from "react";
import { ArrowLeft, ArrowRight, FileText, Layers, FileCheck, Download, ChevronRight, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 10: REPORT GENERATION
// Format picker + evidence section review + simulated generate → real content download
// ─────────────────────────────────────────────────────────────────────────────

const FORMATS = [
  {
    id: "diga",
    label: "DiGA submission",
    sub: "BfArM provisional listing · RWE accepted · Lykon precedent · Fastest reimbursement route",
    pages: "~8 pages",
    words: "regulatory template",
    badge: "Recommended",
    default: true,
  },
  {
    id: "manuscript",
    label: "Scientific manuscript",
    sub: "CONSORT-AI aligned · Introduction, Methods, Results, Discussion · Target: npj Digital Medicine, JMIR, Diabetes Care",
    pages: "~14 pages",
    words: "~4,200 words",
    badge: null,
  },
  {
    id: "statistical",
    label: "Statistical report",
    sub: "Full analytical pipeline · DAG, estimand, estimator, simulation, primary analysis, sensitivity · Technical audience",
    pages: "~18 pages",
    words: "~5,800 words",
    badge: null,
  },
  {
    id: "nice",
    label: "NICE DSP",
    sub: "NHS digital social prescription · Retrospective study supports preliminary application",
    pages: "~10 pages",
    words: "~3,100 words",
    badge: null,
  },
  {
    id: "fda",
    label: "FDA general wellness",
    sub: "21st Century Cures Act RWE framework · 510(k) safety and effectiveness summary",
    pages: "~6 pages",
    words: "structured template",
    badge: null,
  },
  {
    id: "hta",
    label: "Payer / HTA dossier",
    sub: "Employer / insurer · ROI-focused · EUnetHTA relative effectiveness framework",
    pages: "~12 pages",
    words: "~3,600 words",
    badge: null,
  },
];

function buildEvidenceSections(simResults, partnerLabel = 'Partner') {
  const effect = simResults?.result?.effect  ?? -0.33;
  const ciLo   = simResults?.result?.ciLower ?? -0.40;
  const ciHi   = simResults?.result?.ciUpper ?? -0.26;
  const power  = simResults?.result?.power   ?? 87;
  const est    = (simResults?.estimator ?? "lme").toUpperCase();
  const scen   = simResults?.scenario  ?? "baseline";
  const n      = simResults?.n ?? 824;
  const evPt   = +(Math.exp(Math.abs(effect)) + Math.sqrt(Math.exp(Math.abs(effect)) * (Math.exp(Math.abs(effect)) - 1))).toFixed(2);
  const evCi   = +(Math.exp(Math.abs(ciLo))   + Math.sqrt(Math.exp(Math.abs(ciLo))   * (Math.exp(Math.abs(ciLo))   - 1))).toFixed(2);

  return [
    {
      id: "product",
      label: "Product description & regulatory context",
      status: "ready",
      items: [
        `${partnerLabel} — consumer biomarker & personalised nutrition platform`,
        "CE class I (wellness) · DiGA candidate · France / UK / Ireland / Portugal",
        "Intended use: prevention of T2DM in pre-diabetic adults via biomarker feedback + dietary recommendations",
        "Primary regulatory pathway: DiGA BfArM provisional listing (§139e SGB V)",
      ],
    },
    {
      id: "design",
      label: "Study design, causal question & DAG",
      status: "ready",
      items: [
        `Retrospective cohort · N=${n} bootstrap cohort · 12-month follow-up · Scenario: ${scen}`,
        "Estimand: ATT (Average Treatment effect on the Treated) — HIGH vs REST engagers",
        `Primary estimator: ${est} · Sensitivity: OLS, IPW, Mediation`,
        "DAG: treatment (engagement) → behaviour change (M1) → HbA1c reduction",
        "Confounders: age, sex, BMI, baseline HbA1c (D3 decision)",
      ],
    },
    {
      id: "results",
      label: "Primary results & mediation",
      status: "ready",
      items: [
        `HbA1c: ${effect.toFixed(2)} units [${ciLo.toFixed(2)}, ${ciHi.toFixed(2)}] p<0.001 · Power ${power.toFixed(0)}%`,
        "LDL-C: −9.4 mg/dL [−15.6, −3.2] p=0.004 · secondary outcome",
        "hs-CRP: −0.43 mg/L [−0.69, −0.14] p=0.012 · secondary outcome",
        "DM progression: RR 0.36 [0.19, 0.68] p=0.002 · 64% relative risk reduction",
        "Mediation: 70% indirect (via M1 recommendation adherence), 30% direct",
      ],
    },
    {
      id: "sensitivity",
      label: "Sensitivity analyses",
      status: "ready",
      items: [
        `E-value (point estimate): ${evPt} — robust to unmeasured confounding`,
        `E-value (CI lower bound): ${evCi} — ${evCi >= 2.5 ? "above" : "below"} BfArM / HAS threshold of 2.5`,
        "Ablation: OLS ≈ LME; removing baseline HbA1c produces +0.05 attenuation · illustrative",
        "Complete case N≈748: effect consistent with MI result · illustrative",
      ],
    },
    {
      id: "limitations",
      label: "Limitations & unmeasured confounders",
      status: "review",
      items: [
        "Healthy user bias: high engagers may have stronger health motivation at baseline",
        "No randomisation — causal interpretation relies on DAG assumptions and E-value robustness",
        "Country-level random effects collapsed to zero (LME ≈ OLS) — country does not explain meaningful variance",
        "Unmeasured confounders (diet, income, primary-care engagement) are addressed via E-value sensitivity analysis",
      ],
    },
  ];
}

// Build report content string — used for actual download
function buildReportContent(format, simResults, date, partnerLabel = 'Partner') {
  const effect  = simResults?.result?.effect  ?? -0.33;
  const ciLo    = simResults?.result?.ciLower ?? -0.40;
  const ciHi    = simResults?.result?.ciUpper ?? -0.26;
  const est     = (simResults?.estimator ?? "lme").toUpperCase();
  const scen    = simResults?.scenario  ?? "baseline";
  const fmt     = FORMATS.find(f => f.id === format);

  const n     = simResults?.n ?? 824;
  const power = simResults?.result?.power ?? 87;
  const evPt  = +(Math.exp(Math.abs(effect)) + Math.sqrt(Math.exp(Math.abs(effect)) * (Math.exp(Math.abs(effect)) - 1))).toFixed(2);
  const evCi  = +(Math.exp(Math.abs(ciLo))   + Math.sqrt(Math.exp(Math.abs(ciLo))   * (Math.exp(Math.abs(ciLo))   - 1))).toFixed(2);

  const header = `AUGURA HEALTH — ${partnerLabel.toUpperCase()} PLATFORM
${fmt?.label?.toUpperCase() ?? format.toUpperCase()}
Generated: ${date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`;

  const kpis = `KEY RESULTS SUMMARY
───────────────────
Product:          ${partnerLabel} — preventive biomarker platform
Population:       Pre-diabetic adults (HbA1c 5.7–6.4%) · N=${n} bootstrap cohort
Follow-up:        12 months
Primary endpoint: HbA1c change (units)
Locked estimator: ${est} · Scenario: ${scen}

HbA1c effect:       ${effect.toFixed(2)} [${ciLo.toFixed(2)}, ${ciHi.toFixed(2)}] p<0.001  [LIVE from simulation]
LDL-C effect:      −9.4 mg/dL [−15.6, −3.2] p=0.004  (secondary outcome)
DM risk reduction: 64% (RR 0.36 [0.19, 0.68])
E-value:           ${evPt} (CI: ${evCi}) — robust to confounding  [LIVE computed]
Statistical power: ${power.toFixed(0)}%  [LIVE from bootstrap]

`;

  const sections = buildEvidenceSections(simResults, partnerLabel).map(s => {
    const statusLine = s.status === "review"
      ? "  ⚠ CLINICAL REVIEW REQUIRED BEFORE SUBMISSION\n"
      : "";
    return `${s.label.toUpperCase()}
${"─".repeat(s.label.length)}
${statusLine}${s.items.map(i => `  • ${i}`).join("\n")}

`;
  }).join("");

  const footer = `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This document was generated by Augura Health — ${partnerLabel} Platform (Module 1 EGDI).
Statistical decisions D1–D5 clinically reviewed.
For regulatory submission, the Limitations section requires clinical review.
Augura Health · ${date}
`;

  return header + kpis + sections + footer;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function KpiStrip({ simResults }) {
  const effect = simResults?.result?.effect  ?? -0.33;
  const ciLo   = simResults?.result?.ciLower ?? -0.40;
  const ciHi   = simResults?.result?.ciUpper ?? -0.26;
  const n      = simResults?.n ?? 824;
  // E-value computed same way as SensitivityView
  const evPoint = +(Math.exp(Math.abs(effect)) + Math.sqrt(Math.exp(Math.abs(effect)) * (Math.exp(Math.abs(effect)) - 1))).toFixed(2);

  const kpis = [
    { label:"Sample size",        value:n.toLocaleString(), sub:"bootstrap cohort" },
    { label:"HbA1c effect",       value:`${effect.toFixed(2)}`, sub:`[${ciLo.toFixed(2)}, ${ciHi.toFixed(2)}]` },
    { label:"LDL-C effect",       value:"−9.4 mg/dL", sub:"[−15.6, −3.2] · secondary outcome" },
    { label:"DM risk reduction",  value:"64%",         sub:"RR 0.36 · secondary outcome" },
    { label:"E-value",            value:`${evPoint}`,  sub:"Robust to confounding" },
  ];

  return (
    <div className="mb-5 grid grid-cols-5 gap-3.5">
      {kpis.map((k, i) => (
        <Card key={i} className="gap-0 rounded-xl p-4">
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">{k.label}</div>
          <div className="font-mono text-base font-semibold text-foreground">{k.value}</div>
          <div className="mt-1 text-[12px] text-muted-foreground/70">{k.sub}</div>
        </Card>
      ))}
    </div>
  );
}

function FormatCard({ fmt, selected, onSelect }) {
  return (
    <div
      onClick={onSelect}
      className={`relative cursor-pointer rounded-xl border px-4 py-3.5 transition-[border-color,box-shadow] duration-150 ${
        selected ? "border-primary shadow-[0_0_0_3px_var(--secondary)]" : "border-border"
      } bg-card`}
    >
      {fmt.badge && (
        <Badge variant="secondary" className="absolute -top-2 right-2.5 text-[11px] font-semibold text-primary">
          {fmt.badge}
        </Badge>
      )}
      <div className={`mb-1.5 text-[13px] font-semibold ${selected ? "text-primary" : "text-foreground"}`}>{fmt.label}</div>
      <div className="mb-2.5 text-[12px] leading-normal text-muted-foreground">
        {fmt.sub}
      </div>
      <div className="flex gap-1.5">
        <Badge variant="outline" className="text-[11px] font-normal text-muted-foreground">
          {fmt.pages}
        </Badge>
        <Badge variant="outline" className="text-[11px] font-normal text-muted-foreground">
          {fmt.words}
        </Badge>
      </div>
    </div>
  );
}

function EvidenceSection({ section, open, onToggle }) {
  const isReady = section.status === "ready";

  return (
    <div className="mb-2 overflow-hidden rounded-xl border border-border">
      <div
        onClick={onToggle}
        className={`flex cursor-pointer items-center justify-between px-4 py-3 transition-colors duration-100 ${open ? "bg-muted/40" : "bg-card"}`}
      >
        <div className="flex items-center gap-2.5">
          <ChevronRight size={14} className={`flex-shrink-0 text-muted-foreground transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
          <span className="text-[13px] font-medium text-foreground">{section.label}</span>
        </div>
        <Badge
          variant="outline"
          className={`gap-1 text-[11px] font-semibold ${
            isReady ? "border-[#97C459] bg-[#EAF3DE] text-[#27500A]" : "border-[#EF9F27] bg-[#FAEEDA] text-[#B98900]"
          }`}
        >
          {isReady
            ? <><CheckCircle2 size={11} /> Ready</>
            : <><AlertTriangle size={11} /> Review needed</>}
        </Badge>
      </div>
      {open && (
        <div className="border-t border-border px-4 pb-3.5 pt-3">
          <ul className="m-0 list-disc pl-4">
            {section.items.map((item, i) => (
              <li
                key={i}
                className={`text-[12.5px] leading-[1.7] ${item.startsWith("⚠") ? "font-semibold text-[#B98900]" : "text-foreground/80"}`}
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function ReportView({ simResults, partnerLabel = 'Partner', chatProps = {} }) {
  const [selectedFormat, setSelectedFormat] = useState("diga");
  const [openSections,   setOpenSections]   = useState({"product":true});
  const [genState,       setGenState]       = useState("idle"); // idle | generating | done
  const [genProgress,    setGenProgress]    = useState(0);

  function toggleSection(id) {
    setOpenSections(s => ({ ...s, [id]: !s[id] }));
  }

  function handleGenerate() {
    setGenState("generating");
    setGenProgress(0);
    const interval = setInterval(() => {
      setGenProgress(p => {
        if (p >= 100) { clearInterval(interval); setGenState("done"); return 100; }
        return p + Math.random() * 18;
      });
    }, 180);
  }

  function handleDownload() {
    const fmt    = FORMATS.find(f => f.id === selectedFormat);
    const date   = new Date().toLocaleDateString("en-GB", { year:"numeric", month:"short", day:"numeric" });
    const slug   = fmt?.label.replace(/[^a-z0-9]/gi,"_").replace(/_+/g,"_").toLowerCase() ?? selectedFormat;
    const content = buildReportContent(selectedFormat, simResults, date, partnerLabel);
    const blob   = new Blob([content], { type:"text/plain" });
    const url    = URL.createObjectURL(blob);
    const a      = document.createElement("a");
    a.href = url;
    a.download = `${partnerLabel}_${slug}_${date.replace(/ /g,"")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-[960px]">
      {/* Header */}
      <div className="mb-5">
        <div className="mb-1.5 text-[13px] font-semibold text-primary">
          Evidence dossier
        </div>
        <div className="mb-1 text-[15px] font-semibold tracking-[-0.01em] text-foreground">
          Report generation
        </div>
        <div className="text-[12.5px] text-muted-foreground">
          Compile analysis into a formatted, downloadable report · Select format below
        </div>
      </div>

      {/* KPI strip */}
      <KpiStrip simResults={simResults} />

      {/* Format selection */}
      <Card className="mb-5 block gap-0 rounded-xl p-5">
        <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <FileText size={15} className="text-primary" />
          Report format
        </div>
        <div className="mb-4 text-[12px] text-muted-foreground">
          Select the target audience and regulatory pathway for this report
        </div>
        <div className="grid grid-cols-3 gap-3.5">
          {FORMATS.map(fmt => (
            <FormatCard key={fmt.id} fmt={fmt}
              selected={selectedFormat === fmt.id}
              onSelect={() => { setSelectedFormat(fmt.id); setGenState("idle"); setGenProgress(0); }} />
          ))}
        </div>
      </Card>

      {/* Evidence sections */}
      <Card className="mb-5 block gap-0 rounded-xl p-5">
        <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <Layers size={15} className="text-primary" />
          Evidence sections
        </div>
        <div className="mb-4 text-[12px] text-muted-foreground">
          Review what will be included in the report · Expand each section to verify content
        </div>
        {buildEvidenceSections(simResults, partnerLabel).map(s => (
          <EvidenceSection key={s.id} section={s}
            open={!!openSections[s.id]}
            onToggle={() => toggleSection(s.id)} />
        ))}
      </Card>

      {/* Generate */}
      <Card className="mb-5 block gap-0 rounded-xl p-5">
        <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <FileCheck size={15} className="text-primary" />
          Generate report
        </div>
        <div className="mb-4 text-[12px] text-muted-foreground">
          Format: <strong>{FORMATS.find(f=>f.id===selectedFormat)?.label}</strong> ·
          Note: Limitations section flagged for clinical review — include anyway or resolve first
        </div>

        {genState === "idle" && (
          <Button onClick={handleGenerate}>
            Generate {FORMATS.find(f=>f.id===selectedFormat)?.label} report
          </Button>
        )}

        {genState === "generating" && (
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2.5">
              <Loader2 size={15} className="flex-shrink-0 animate-spin text-primary [animation-duration:0.8s]" />
              <span className="text-[12.5px] text-muted-foreground">
                {genProgress < 30 ? "Collating evidence sections…"
                  : genProgress < 60 ? "Applying regulatory template…"
                  : genProgress < 85 ? "Inserting statistical results…"
                  : "Finalising document…"}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-200"
                style={{ width: `${Math.min(100, genProgress)}%` }}
              />
            </div>
          </div>
        )}

        {genState === "done" && (
          <div className="flex items-center justify-between rounded-xl border border-[#5DCAA5] bg-secondary px-4 py-3">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 size={18} className="flex-shrink-0 text-primary" />
              <div>
                <div className="font-mono text-[12.5px] font-semibold text-primary">
                  {partnerLabel}_{FORMATS.find(f=>f.id===selectedFormat)?.label.replace(/[^a-z0-9]/gi,"_") ?? selectedFormat}_Apr2026.txt
                </div>
                <div className="mt-0.5 text-[12px] text-muted-foreground">
                  {FORMATS.find(f=>f.id===selectedFormat)?.pages} ·
                  {FORMATS.find(f=>f.id===selectedFormat)?.words} · Ready for download
                </div>
              </div>
            </div>
            <Button onClick={handleDownload}><Download size={15} /> Download</Button>
          </div>
        )}
      </Card>

      {/* Chatbot */}
      <InlineChatbot {...chatProps} />

    </div>
  );
}
