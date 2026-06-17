import { useState } from "react";
import { FileText, FileCheck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/EmptyState";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 10: REPORT GENERATION
// Format picker (UI config) + report compilation.
// No live report-generation backend is wired yet — the compilation area
// renders an honest empty state instead of fabricated dossier content.
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

// ── Sub-components ────────────────────────────────────────────────────────────

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

// ── Main view ─────────────────────────────────────────────────────────────────

export default function ReportView({ partnerLabel = 'Partner', chatProps = {} }) {
  const [selectedFormat, setSelectedFormat] = useState("diga");

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
              onSelect={() => setSelectedFormat(fmt.id)} />
          ))}
        </div>
      </Card>

      {/* Report compilation — no live generation backend wired yet */}
      <Card className="mb-5 block gap-0 rounded-xl p-5">
        <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <FileCheck size={15} className="text-primary" />
          Generate report
        </div>
        <div className="mb-4 text-[12px] text-muted-foreground">
          Partner: <strong>{partnerLabel}</strong> ·
          Format: <strong>{FORMATS.find(f => f.id === selectedFormat)?.label}</strong>
        </div>
        <EmptyState
          icon={FileCheck}
          title="Not available yet — no live data source wired"
          subtitle="Report compilation will assemble your locked analysis into the selected format once a live generation source is connected."
        />
      </Card>

      {/* Chatbot */}
      <InlineChatbot {...chatProps} />

    </div>
  );
}
