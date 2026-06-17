// Study-level surfaces that sit alongside the Workflow (per the navigation sketch's
// study tab bar: Workflow / History / Lineage / Settings). Demo content — these are
// cross-cutting views of a single study, not workflow steps.
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  History, GitBranch, Settings as SettingsIcon, FlaskConical, Brain, Network,
  FileText, Upload, RotateCcw, Users, Shield, Archive,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/EmptyState";
import { apiJson } from "@/api";

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

// ── History — the workspace audit trail, from the analytics activity feed ──────
const EVENT_LABEL = {
  "study.created": "Study created",
  "study.updated": "Study updated",
  "simulation.requested": "Simulation requested",
  "simulation.bootstrap.succeeded": "Simulation completed",
  "document.requested": "Dossier requested",
  "document.generated": "Dossier generated",
  "cohort.imported": "Cohort imported",
};

function relTime(iso) {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function StudyHistory() {
  const [events, setEvents] = useState(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try { const e = await apiJson("/analytics/activity?limit=50"); if (alive) setEvents(e); }
      catch { if (alive) setEvents([]); }
    })();
    return () => { alive = false; };
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <PageHead icon={<><History size={13} /> Study · Activity</>} title="History"
        sub="Runs, agent calls, edits, and exports across your workspace — the audit trail." />
      {events == null ? (
        <div className="py-10 text-center text-[12px] text-muted-foreground">Loading activity…</div>
      ) : events.length === 0 ? (
        <EmptyState
          icon={History}
          title="No activity yet"
          subtitle="The audit trail will populate as runs, agent calls, edits, and exports happen."
        />
      ) : (
        <Card className="gap-0 overflow-hidden p-0">
          {events.map((e, i) => (
            <div
              key={e.id}
              className={`flex items-center gap-3 px-4 py-3 ${i === events.length - 1 ? "" : "border-b border-border/60"}`}
            >
              <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary" />
              <span className="flex-1 text-[13px] text-foreground">
                {EVENT_LABEL[e.event_type] || e.event_type}
                {e.metadata?.name && <span className="text-muted-foreground"> · {e.metadata.name}</span>}
                {e.metadata?.type && <span className="text-muted-foreground"> · {e.metadata.type}</span>}
                {e.metadata?.cohort_name && <span className="text-muted-foreground"> · {e.metadata.cohort_name}</span>}
              </span>
              <span className="flex-shrink-0 font-mono text-[11px] text-muted-foreground/70">{relTime(e.created_at)}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

// ── Lineage — versioned, content-hashed artifacts (reproducibility chain) ──────
const ARTIFACT_LABEL = {
  simulation_run: "Simulation run",
  document: "Dossier",
  dataset: "Dataset",
};

export function StudyLineage() {
  const [artifacts, setArtifacts] = useState(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try { const a = await apiJson("/analytics/artifacts?limit=50"); if (alive) setArtifacts(a); }
      catch { if (alive) setArtifacts([]); }
    })();
    return () => { alive = false; };
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <PageHead icon={<><GitBranch size={13} /> Study · Provenance</>} title="Lineage"
        sub="Versioned, content-hashed artifacts — the reproducibility chain from data to result." />
      {artifacts == null ? (
        <div className="py-10 text-center text-[12px] text-muted-foreground">Loading provenance…</div>
      ) : artifacts.length === 0 ? (
        <EmptyState
          icon={GitBranch}
          title="No artifacts yet"
          subtitle="Each simulation run and generated dossier records a versioned, hashed artifact here."
        />
      ) : (
        <Card className="gap-0 overflow-hidden p-0">
          {artifacts.map((a, i) => (
            <div
              key={a.id}
              className={`flex items-center gap-3 px-4 py-3 ${i === artifacts.length - 1 ? "" : "border-b border-border/60"}`}
            >
              <Badge variant="secondary" className="text-primary">{ARTIFACT_LABEL[a.kind] || a.kind}</Badge>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] text-foreground">
                  v{a.version}
                  {a.provenance?.type && <span className="text-muted-foreground"> · {a.provenance.type}</span>}
                  {a.locked && <span className="ml-2 text-[11px] text-[#B98900]">locked</span>}
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-muted-foreground/70">
                  sha256 {String(a.sha256).slice(0, 16)}…
                </div>
              </div>
              <span className="flex-shrink-0 font-mono text-[11px] text-muted-foreground/70">{relTime(a.created_at)}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

// ── Settings — study configuration ────────────────────────────────────────────
const fieldCls = "w-full rounded-lg border border-border bg-white px-3 py-2 text-[13px] text-foreground outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15";

// UUID v4-ish check: only real backend studies (created via POST /studies) have a
// UUID id; legacy slug routes can't be persisted (GET/PATCH expect a UUID).
const isUuid = (s) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s || "");

export function StudySettings({ study, projectId }) {
  const navigate = useNavigate();
  const persistable = isUuid(projectId);
  const [name, setName] = useState(study?.name ?? "Study");
  const [framework, setFramework] = useState((study?.framework ?? "DiGA").split(" · ")[0]);
  const [category, setCategory] = useState(study?.category && study.category !== "—" ? study.category : "");
  const [lead, setLead] = useState(study?.lead && study.lead !== "—" ? study.lead : "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  // Hydrate from the real study record when we have a UUID route.
  useEffect(() => {
    if (!persistable) return;
    let alive = true;
    apiJson(`/studies/${projectId}`)
      .then((s) => {
        if (!alive) return;
        setName(s.name ?? "");
        if (s.framework) setFramework(s.framework);
        setCategory(s.category ?? "");
        setLead(s.lead ?? "");
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [projectId, persistable]);

  async function save() {
    if (!persistable) return;
    setBusy(true); setMsg(null);
    try {
      await apiJson(`/studies/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify({ name, framework, category: category || null, lead: lead || null }),
      });
      setMsg("Saved.");
    } catch {
      setMsg("Could not save changes.");
    } finally { setBusy(false); }
  }

  async function archive() {
    if (!persistable) return;
    setBusy(true); setMsg(null);
    try {
      await apiJson(`/studies/${projectId}`, { method: "PATCH", body: JSON.stringify({ status: "archived" }) });
      navigate("/studies");
    } catch {
      setBusy(false);
      setMsg("Could not archive the study.");
    }
  }

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
            <input className={fieldCls} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="—" /></label>
          <label className="block"><div className="mb-1.5 text-[12.5px] font-medium text-foreground">Study lead</div>
            <input className={fieldCls} value={lead} onChange={(e) => setLead(e.target.value)} placeholder="—" /></label>
        </div>
        <div className="mt-4 flex items-center gap-3 border-t border-border pt-4">
          <Button onClick={save} disabled={busy || !persistable}>
            {busy ? "Saving…" : "Save changes"}
          </Button>
          {msg && <span className="text-[12.5px] text-muted-foreground">{msg}</span>}
          {!persistable && <span className="text-[12px] text-muted-foreground">Create the study first to edit its settings.</span>}
        </div>
      </Card>

      <Card className="gap-0 rounded-xl border p-5">
        <div className="mb-1 flex items-center gap-2 text-[15px] font-semibold text-foreground"><Users size={15} className="text-primary" /> Collaborators</div>
        <p className="mb-3 text-[12px] text-muted-foreground">People with access to this study.</p>
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-[12.5px] text-muted-foreground">
          Collaborator management isn't enabled yet — access follows your organisation membership.
        </div>
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
        <Button onClick={archive} variant="outline" size="sm" disabled={busy || !persistable}
          className="w-fit border-[#C0392B]/30 text-[#C0392B] text-xs hover:bg-[#C0392B]/[0.06]">Archive this study</Button>
      </Card>
    </div>
  );
}
