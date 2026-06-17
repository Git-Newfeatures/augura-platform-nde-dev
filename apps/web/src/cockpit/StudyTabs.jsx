// Study-level surfaces that sit alongside the Workflow (per the navigation sketch's
// study tab bar: Workflow / History / Lineage / Settings). Demo content — these are
// cross-cutting views of a single study, not workflow steps.
import { useState } from "react";
import {
  History, GitBranch, Settings as SettingsIcon, FlaskConical, Brain, Network,
  FileText, Upload, RotateCcw, Users, Shield, Archive,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/EmptyState";

function PageHead({ icon, title, sub }) {
  return (
    <div className="mb-1">
      <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-primary">
        {icon}
      </div>
      <h1 className="mt-1 text-[22px] font-semibold tracking-[-0.02em] text-foreground">{title}</h1>
      <p className="mt-1 text-[13.5px] text-muted-foreground">{sub}</p>
    </div>
  );
}

// ── History — the per-study run log (sketch's "primary daily-use surface") ─────
const HISTORY_ICON = {
  simulation: FlaskConical, profiling: Brain, dag: Network, export: FileText, upload: Upload, edit: RotateCcw,
};

export function StudyHistory() {
  return (
    <div className="flex flex-col gap-5">
      <PageHead icon={<><History size={13} /> Study · Activity</>} title="History"
        sub="Every run, agent call, edit, and export for this study — the full audit trail." />
      <EmptyState
        icon={History}
        title="No activity yet"
        subtitle="The audit trail will populate as runs, agent calls, edits, and exports happen for this study."
      />
    </div>
  );
}

// ── Lineage — variable trace from raw column to result ────────────────────────
const STAGE_COLORS = ["#0F6E56", "#3172B0", "#3C3489", "#B98900", "#0F6E56"];

export function StudyLineage() {
  return (
    <div className="flex flex-col gap-5">
      <PageHead icon={<><GitBranch size={13} /> Study · Provenance</>} title="Lineage"
        sub="Trace every variable from raw dataset column through taxonomy, causal role, and model to the final result." />
      <EmptyState
        icon={GitBranch}
        title="Not available yet — no live data source wired"
        subtitle="Variable lineage will trace each result back to its source column once runs produce traceable provenance."
      />
    </div>
  );
}

// ── Settings — study configuration ────────────────────────────────────────────
const fieldCls = "w-full rounded-lg border border-border bg-white px-3 py-2 text-[13px] text-foreground outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15";

export function StudySettings({ study }) {
  const [name, setName] = useState(study?.name ?? "Study");
  const [framework, setFramework] = useState((study?.framework ?? "DiGA").split(" · ")[0]);
  return (
    <div className="flex flex-col gap-5">
      <PageHead icon={<><SettingsIcon size={13} /> Study · Configuration</>} title="Settings"
        sub="Study metadata, collaborators, and data-handling preferences." />

      <Card className="gap-0 rounded-xl border p-5">
        <div className="mb-3.5 text-[15px] font-semibold text-foreground">Study details</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block"><div className="mb-1.5 text-[12.5px] font-medium text-foreground">Study name</div>
            <input className={fieldCls} value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="block"><div className="mb-1.5 text-[12.5px] font-medium text-foreground">Target framework</div>
            <select className={fieldCls} value={framework} onChange={(e) => setFramework(e.target.value)}>
              {["DiGA", "CONSORT-AI", "EU MDR", "NICE DSP", "EUnetHTA", "FDA SaMD"].map((f) => <option key={f}>{f}</option>)}
            </select></label>
          <label className="block"><div className="mb-1.5 text-[12.5px] font-medium text-foreground">Category</div>
            <input className={fieldCls} defaultValue={study?.category ?? "—"} /></label>
          <label className="block"><div className="mb-1.5 text-[12.5px] font-medium text-foreground">Study lead</div>
            <input className={fieldCls} defaultValue={study?.lead ?? "—"} /></label>
        </div>
      </Card>

      <Card className="gap-0 rounded-xl border p-5">
        <div className="mb-1 flex items-center gap-2 text-[15px] font-semibold text-foreground"><Users size={15} className="text-primary" /> Collaborators</div>
        <p className="mb-3 text-[12px] text-muted-foreground">People with access to this study.</p>
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-[12.5px] text-muted-foreground">
          No collaborators yet — invite teammates to share access to this study.
        </div>
        <Button variant="outline" size="sm" className="mt-3 w-fit text-xs">+ Invite collaborator</Button>
      </Card>

      <Card className="gap-0 rounded-xl border p-5">
        <div className="mb-1 flex items-center gap-2 text-[15px] font-semibold text-foreground"><Shield size={15} className="text-primary" /> Data & retention</div>
        <div className="mt-2 flex flex-col gap-2.5 text-[12.5px] text-foreground/80">
          <div className="flex items-center justify-between"><span>Dataset retention</span><Badge variant="secondary" className="text-primary">12 months</Badge></div>
          <div className="flex items-center justify-between"><span>De-identification</span><Badge variant="secondary" className="text-primary">Pseudonymised ✓</Badge></div>
          <div className="flex items-center justify-between"><span>Default export format</span><Badge variant="outline" className="text-muted-foreground">DiGA dossier (PDF)</Badge></div>
        </div>
      </Card>

      <Card className="gap-0 rounded-xl p-5" style={{ borderColor: "rgba(192,57,43,0.3)" }}>
        <div className="mb-1 flex items-center gap-2 text-[15px] font-semibold text-[#C0392B]"><Archive size={15} /> Archive study</div>
        <p className="mb-3 text-[12px] text-muted-foreground">Archiving hides the study from the dashboard. It can be restored later.</p>
        <Button variant="outline" size="sm" className="w-fit border-[#C0392B]/30 text-[#C0392B] text-xs hover:bg-[#C0392B]/[0.06]">Archive this study</Button>
      </Card>
    </div>
  );
}
