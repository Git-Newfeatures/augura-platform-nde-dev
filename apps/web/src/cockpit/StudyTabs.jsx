// Study-level surfaces that sit alongside the Workflow (per the navigation sketch's
// study tab bar: Workflow / History / Lineage / Settings). Demo content — these are
// cross-cutting views of a single study, not workflow steps.
import { useState } from "react";
import {
  History, GitBranch, Settings as SettingsIcon, FlaskConical, Brain, Network,
  FileText, Upload, RotateCcw, Eye, Check, Clock, Users, Shield, Archive,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

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
const HISTORY = [
  { type: "simulation", title: "Power simulation · LME / OLS / IPW", meta: "B=500 · all estimators above 80% power", when: "2 hours ago", by: "Dr. R. Pirracchio", status: "done" },
  { type: "dag",        title: "Causal DAG regenerated", meta: "8 nodes · 12 edges · 2 unmeasured confounders flagged", when: "2 hours ago", by: "Augura agent", status: "done" },
  { type: "simulation", title: "Bootstrap validation (2,000×)", meta: "VALIDATED · effect −0.33 [−0.40, −0.26]", when: "yesterday", by: "Dr. R. Pirracchio", status: "done" },
  { type: "export",     title: "DiGA evidence dossier · draft", meta: "PDF · 62% complete", when: "yesterday", by: "M-L. Dubois", status: "done" },
  { type: "profiling",  title: "E1 profiling run", meta: "47 comparators · risk LOW · 3 study designs proposed", when: "3 days ago", by: "Augura agent", status: "done" },
  { type: "upload",     title: "Cohort uploaded · lucis_study_cohort", meta: "824 rows · 31 columns · 2 soft flags", when: "3 days ago", by: "Dr. R. Pirracchio", status: "flag" },
];

export function StudyHistory() {
  return (
    <div className="flex flex-col gap-5">
      <PageHead icon={<><History size={13} /> Study · Activity</>} title="History"
        sub="Every run, agent call, edit, and export for this study — the full audit trail." />
      <Card className="gap-0 px-[18px] py-1">
        {HISTORY.map((h, i) => {
          const Icon = HISTORY_ICON[h.type] ?? Clock;
          return (
            <div key={i} className={`flex items-center gap-3.5 py-3.5 ${i === HISTORY.length - 1 ? "" : "border-b border-border"}`}>
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[10px] bg-secondary text-primary">
                <Icon size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-foreground">{h.title}</div>
                <div className="mt-0.5 text-[12px] text-muted-foreground">{h.meta}</div>
              </div>
              <div className="hidden w-40 flex-shrink-0 text-right text-[11.5px] text-muted-foreground sm:block">
                {h.by}<br /><span className="text-muted-foreground/70">{h.when}</span>
              </div>
              {h.status === "flag"
                ? <Badge variant="outline" className="text-[#B98900] border-[#B98900]/30">2 flags</Badge>
                : <Badge variant="secondary" className="text-primary"><Check size={11} className="mr-0.5" /> Done</Badge>}
              <Button variant="ghost" size="sm" className="h-7 gap-1 px-2.5 text-[12px]"><Eye size={13} /> View</Button>
            </div>
          );
        })}
      </Card>
    </div>
  );
}

// ── Lineage — variable trace from raw column to result ────────────────────────
const LINEAGE_STAGES = [
  { stage: "Dataset column", items: ["engagement_score", "hba1c_12m", "rec_adherence_pct", "age · sex · bmi"] },
  { stage: "Taxonomy concept", items: ["Composite engagement", "HbA1c change", "Adherence", "Demographics"] },
  { stage: "DAG role", items: ["Exposure (A)", "Outcome (Y)", "Mediator (M1)", "Confounders (X)"] },
  { stage: "Estimand & model", items: ["ATT · LME", "ΔHbA1c @ 12m", "NDE / NIE split", "Adjustment set"] },
  { stage: "Result", items: ["−0.33 [−0.40,−0.26]", "p < 0.001", "70% mediated", "E-value 3.1"] },
];
const STAGE_COLORS = ["#0F6E56", "#3172B0", "#3C3489", "#B98900", "#0F6E56"];

export function StudyLineage() {
  return (
    <div className="flex flex-col gap-5">
      <PageHead icon={<><GitBranch size={13} /> Study · Provenance</>} title="Lineage"
        sub="Trace every variable from raw dataset column through taxonomy, causal role, and model to the final result." />
      <Card className="gap-0 overflow-x-auto rounded-xl border p-5">
        <div className="grid min-w-[760px] gap-3" style={{ gridTemplateColumns: `repeat(${LINEAGE_STAGES.length}, 1fr)` }}>
          {LINEAGE_STAGES.map((col, ci) => (
            <div key={col.stage} className="flex flex-col gap-2">
              <div className="mb-1 flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
                <span className="h-2 w-2 rounded-full" style={{ background: STAGE_COLORS[ci] }} />
                {col.stage}
              </div>
              {col.items.map((it) => (
                <div key={it} className="rounded-lg border border-border bg-card px-2.5 py-2 font-mono text-[11.5px] text-foreground/80">
                  {it}
                </div>
              ))}
            </div>
          ))}
        </div>
        <p className="mt-4 text-[12px] text-muted-foreground">
          Each row flows left → right: every result is traceable back to a source column and the transforms applied. Unmeasured confounders (diet, income) enter at the DAG-role stage and are carried to the sensitivity analysis.
        </p>
      </Card>
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
        {[["Dr. Romain Pirracchio", "Owner"], ["Marie-Laure Dubois", "Editor"], ["François Mercier", "Viewer"]].map(([n, r]) => (
          <div key={n} className="flex items-center justify-between border-b border-border py-2.5 last:border-b-0">
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-secondary text-[11px] font-semibold text-primary">{n.split(" ").map((x) => x[0]).slice(-2).join("")}</span>
              <span className="text-[13px] text-foreground">{n}</span>
            </div>
            <Badge variant="outline" className="text-muted-foreground">{r}</Badge>
          </div>
        ))}
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
