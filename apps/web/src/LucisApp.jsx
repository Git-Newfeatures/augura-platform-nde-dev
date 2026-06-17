import { useState, useEffect, useMemo, Component } from "react";

class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e) { return { error: e }; }
  render() {
    if (this.state.error) return (
      <div className="m-4 rounded-lg border border-[#F5A9A9] bg-[#FFF5F5] p-6 font-mono text-[12px] text-[#C0392B]">
        <strong>Runtime error in this view:</strong><br />
        {this.state.error.message}<br /><br />
        <pre className="whitespace-pre-wrap text-[11px] text-muted-foreground">
          {this.state.error.stack?.slice(0, 600)}
        </pre>
      </div>
    );
    return this.props.children;
  }
}
import { useParams, useNavigate } from "react-router-dom";
import { FALLBACK_PROJECT_ID, BLANK_DEFAULTS } from "./data/projectDefaults";
import SimulationEngine from "./SimulationEngine";
import { apiJson } from "./api";

import ProfilingAssistant     from "./views/ProfilingAssistant";
import DatasetVerification    from "./views/DatasetVerification";
import ProfilingRun           from "./views/ProfilingRun";
import ProductProfile         from "./views/ProductProfile";
import StudyType              from "./views/StudyType";
import OutcomeSelection       from "./views/OutcomeSelection";
import DataAvailability       from "./views/DataAvailability";
import StudyDesign            from "./views/StudyDesign";
import CausalModel            from "./views/CausalModel";
import SimulationLoadingScreen from "./views/SimulationLoadingScreen";
import ResultsView            from "./views/ResultsView";
import SensitivityView        from "./views/SensitivityView";
import ReportView             from "./views/ReportView";
import MonitoringView         from "./views/MonitoringView";
import { StudyShell }         from "./cockpit/StudyShell";
import { Rail }               from "./cockpit/Rail";
import { StudyHistory, StudyLineage, StudySettings } from "./cockpit/StudyTabs";
import { buildCockpitStudy } from "./cockpit/cockpitData";
import { VIEW_ORDER } from "./lib/nav";

// ── Session persistence helpers ───────────────────────────────────────────────
const SS_KEY_DEFAULT = "lucis_session_v2";
function ssLoad(key, fallback, ssKey = SS_KEY_DEFAULT) {
  try { const s = sessionStorage.getItem(ssKey); return s ? (JSON.parse(s)[key] ?? fallback) : fallback; }
  catch { return fallback; }
}
function ssStore(key, value, ssKey = SS_KEY_DEFAULT) {
  try {
    const s = sessionStorage.getItem(ssKey);
    const obj = s ? JSON.parse(s) : {};
    obj[key] = value;
    sessionStorage.setItem(ssKey, JSON.stringify(obj));
  } catch { /* silent */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN APP
// ─────────────────────────────────────────────────────────────────────────────
export default function LucisApp() {
  const params = useParams();
  const projectId = params.id ?? FALLBACK_PROJECT_ID;
  const splat = params["*"] || "";
  const navigate = useNavigate();
  // Studies render with neutral defaults; real per-study metadata should be
  // sourced from the backend study record once that endpoint is wired.
  const defaults = BLANK_DEFAULTS;
  const SS_KEY = `augura_session_v3_${projectId}`;
  const load = (key, fallback) => ssLoad(key, fallback, SS_KEY);

  // `view` is derived from the URL splat — the router is the source of truth.
  //   ""                → cockpit (Overview)
  //   "workflow/<view>" → that step view
  //   runs/lineage/settings are handled inside the cockpit tabs (P1)
  const view = (() => {
    if (!splat) return "cockpit";
    const m = splat.match(/^workflow\/(.+)$/);
    if (m && VIEW_ORDER.includes(m[1])) return m[1];
    if (["history", "lineage", "settings"].includes(splat)) return splat;
    return "cockpit";
  })();

  const [profileReady, setReady]    = useState(() => load("profileReady", false));
  const [e1Profile, setE1Profile]   = useState(() => load("e1Profile", null));
  const [studyType, setStudyType]       = useState(() => load("studyType", "retro"));
  const [studyDesign, setStudyDesign]   = useState("retro_cohort");
  const [studyEstimand, setStudyEstimand] = useState("ATE");
  const [selectedEstimators, setSelectedEstimators] = useState(() => load("selectedEstimators", ["lme","ols","ipw"]));
  const [lockedEstimator, setLockedEstimator] = useState(() => load("lockedEstimator", null));
  const [simResults,      setSimResults]      = useState(() => load("simResults", null));
  const [simLoading, setSimLoading] = useState(false);
  const [selectedOutcome, setSelectedOutcome] = useState(() => load("selectedOutcome", defaults.endpoints?.[0] ?? ""));
  const [selectedCohort,   setSelectedCohort]   = useState(() => load("selectedCohort", defaults.defaultCohort));
  const [uploadedRowCount, setUploadedRowCount] = useState(() => load("uploadedRowCount", null));
  const [uploadedData,     setUploadedData]     = useState(() => load("uploadedData", null));
  const [dagCache, setDagCache] = useState(() => load("dagCache", null));
  const [cqExposure, setCqExposure] = useState(() => load("cqExposure", defaults.cqExposure ?? ""));
  const [cqPopulation, setCqPopulation] = useState(() => load("cqPopulation", defaults.cqPopulation ?? []));
  // Never restore "running" state — if user refreshed mid-run, reset to input
  const [agentStep, setAgentStep] = useState(() => { const s = load("agentStep", "input"); return s === "running" ? "input" : s; });
  const [agentSteps,    setAgentSteps]    = useState(() => load("agentSteps", []));
  const [lastRunInputs, setLastRunInputs] = useState(() => load("lastRunInputs", null));
  // Tracks the furthest Profiling sub-tab the user has explicitly completed (clicked Next from)
  // null = none yet (agent just finished), then advances through profiling tab ids in order
  const [completedTab, setCompletedTab] = useState(() => load("completedTab", null));
  // Live study record (GET /studies/:id) backing the cockpit shell. null until loaded
  // or when projectId isn't a real UUID (legacy/slug routes) → scaffold fallback.
  const [studyRow, setStudyRow] = useState(null);
  // (admin entry now lives in the shell TopBar; sidebar replaced by the StepNav rail)

  // Variable mappings produced by the 1b verification view — keyed by `sheet::column`.
  // Each value: { user_decision, final_role, final_canonical_id }
  const [variableMappings, setVariableMappings] = useState(() => load("variableMappings", {}));

  // Full variable-check agent result — persisted so 1b rehydrates without re-running.
  // Shape: { clinical_domain, outcomes_catalog_size, total_columns, batches, matches, dataset_questions }
  const [variableCheckResult, setVariableCheckResult] = useState(() => load("variableCheckResult", null));

  // ── Tenant CESL profile — served by the backend (/reference/tenant, JWT-scoped).
  // No projectId param: the server resolves the tenant from the auth token.
  const [tenantProfile, setTenantProfile] = useState(null);
  useEffect(() => {
    apiJson('/reference/tenant')
      .then(data => { if (data) setTenantProfile(data); })
      .catch(() => {});
  }, []);

  const [studyDesigns, setStudyDesigns] = useState({}); // { code: label }
  useEffect(() => {
    apiJson('/reference/study-designs')
      .then(data => {
        const map = {};
        (Array.isArray(data) ? data : []).forEach(d => { map[d.code] = d.label; });
        setStudyDesigns(map);
      })
      .catch(() => {});
  }, []);

  const [agentSources, setAgentSources] = useState([]); // [{ code, label, doc_type, ... }]
  useEffect(() => {
    apiJson('/reference/cesl-sources')
      .then(data => setAgentSources(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  // Clinical domains come from the fetched tenant CESL profile; empty until it loads
  // (or if the tenant has no profile) — no hardcoded partner defaults.
  const clientDomains =
    tenantProfile?.cesl_profile?.clinical_domain ?? [];

  const clientEvidenceTypes =
    tenantProfile?.cesl_profile?.evidence_type ?? [];

  // ── Shared chat state (session-only, not persisted) ──────────────────────────
  const [chatHistory, setChatHistory] = useState([]);

  // Increment to ask ProfilingAssistant to auto-trigger a fresh run on next mount
  const [pendingRunToken, setPendingRunToken] = useState(0);

  // Clear DAG cache when outcome, causal question, or confirmed dataset variables change
  // so the DAG agent always re-runs with fresh measured/unmeasured flags from 1b.
  const mappingsFingerprint = Object.entries(variableMappings || {})
    .filter(([, d]) => d.user_decision && d.user_decision !== "pending")
    .map(([k, d]) => `${k}:${d.final_role}`)
    .sort().join("|");
  useEffect(() => { setDagCache(null); }, [selectedOutcome, cqExposure, cqPopulation.join(","), mappingsFingerprint]); // eslint-disable-line react-hooks/exhaustive-deps

  const [product, setProduct] = useState(() => load("product", defaults.productCharacteristics));
  const [users, setUsers]     = useState(() => load("users",   defaults.userCharacteristics));
  const [outcome, setOutcome] = useState(() => load("outcome", defaults.outcomesOfInterest));

  // Persist all state to sessionStorage
  useEffect(() => {
    try {
      // Filter __SYNTHDATA tokens — profile is already in e1Profile, no need to double-store
      const stepsToSave = agentSteps.filter(s => !String(s).startsWith("__SYNTHDATA:"));
      sessionStorage.setItem(SS_KEY, JSON.stringify({  // SS_KEY is project-scoped
        profileReady, e1Profile, studyType, selectedEstimators,
        lockedEstimator, selectedOutcome, product, users, outcome,
        simResults, uploadedRowCount, uploadedData, agentStep, completedTab,
        agentSteps: stepsToSave, lastRunInputs, cqExposure, cqPopulation,
        variableMappings, variableCheckResult,
      }));
    } catch { /* sessionStorage full or unavailable — silent */ }
  }, [profileReady, e1Profile, studyType, selectedEstimators, lockedEstimator, selectedOutcome, dagCache, product, users, outcome, simResults, uploadedRowCount, uploadedData, agentStep, agentSteps, lastRunInputs, cqExposure, cqPopulation, variableMappings, variableCheckResult]);

  // A dataset must be uploaded before the agent can run and before any downstream phase is accessible
  const hasDataset = !!uploadedData;

  // Load the real study record for the cockpit shell (UUID routes only).
  const isUuidId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(projectId);
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!isUuidId) { setStudyRow(null); return; }
      try { const r = await apiJson(`/studies/${projectId}`); if (alive) setStudyRow(r); }
      catch { /* legacy/slug route or unreachable → scaffold fallback */ }
    })();
    return () => { alive = false; };
  }, [projectId, isUuidId]);

  // Cockpit study shape = live backend row + real workflow progress (replaces the
  // former static scaffold). Rail / StepNav / Overview / Settings all consume this.
  const cockpitStudy = useMemo(
    () => buildCockpitStudy(projectId, studyRow, {
      hasDataset, profileReady, completedTab, lockedEstimator, simResults, currentView: view,
      question: {
        population: Array.isArray(cqPopulation) ? cqPopulation.join(", ") : cqPopulation,
        exposure: cqExposure,
        outcome: selectedOutcome,
      },
    }),
    [projectId, studyRow, hasDataset, profileReady, completedTab, lockedEstimator,
     simResults, view, cqPopulation, cqExposure, selectedOutcome],
  );

  // Flat lowercased column names across all uploaded sheets — used to gate
  // hardcoded variable displays (engagement, mediators) on what is actually present.
  const uploadedColumns = uploadedData?.sheets
    ? uploadedData.sheets.flatMap(s => (s.headers || []).map(h => String(h).toLowerCase().trim()))
    : [];
  const hasEngagementCol = uploadedColumns.some(h => /engagement|adherence|login|completion|sessions_per_week|recommendations_followed/.test(h));

  // Derive dataset-confirmed variable lists from 1b decisions — fed into the DAG agent
  // so it knows which variables are actually measured vs. inferred from literature only.
  const datasetVariables = (() => {
    const mappings = variableMappings || {};
    const confirmed = Object.entries(mappings)
      .filter(([, d]) => d.user_decision && d.user_decision !== "pending" && d.final_role !== "unused")
      .map(([key, d]) => ({ column: key.split("::")[1], role: d.final_role, canonical_id: d.final_canonical_id || null }));

    return {
      measuredConfounders:   confirmed.filter(v => v.role === "measured_confounder").map(v => v.column),
      unmeasuredConfounders: confirmed.filter(v => v.role === "unmeasured_confounder").map(v => v.column),
      mediators:             confirmed.filter(v => v.role === "mediator").map(v => v.column),
      effectModifiers:       confirmed.filter(v => v.role === "effect_modifier").map(v => v.column),
      exposureComponents:    confirmed.filter(v => v.role === "exposure_component").map(v => v.column),
      exposures:             confirmed.filter(v => v.role === "exposure").map(v => v.column),
      outcomes:              confirmed.filter(v => v.role === "outcome").map(v => ({ column: v.column, canonical_id: v.canonical_id })),
      primaryExposure:       confirmed.find(v => v.role === "exposure")?.column || null,
      // Dataset structure questions agreed/corrected by user in 1b
      datasetQuestions: (variableCheckResult?.dataset_questions || []).map(q => ({
        question_code: q.question_code,
        answer: q.answer,
      })),
    };
  })();

  // Sequential tab order — must match Sidebar profiling children (profiling_run is not gated, excluded here)
  const TAB_ORDER = ["profile","outcomes","causal","datacheck","studytype","design"];

  // Advance completedTab to at least `tabId` when user clicks Next
  function completeTab(tabId) {
    const idx = TAB_ORDER.indexOf(tabId);
    const cur = TAB_ORDER.indexOf(completedTab);
    if (idx > cur) setCompletedTab(tabId);
  }

  // Guard: results-stage views need a completed simulation to render. Deep-linking
  // to them without simResults bounces to the Overview. Upstream steps render their
  // own initial/empty state, so they stay freely navigable.
  useEffect(() => {
    if (view === "cockpit") return;
    const needsSim = ["results", "sensitivity", "report", "monitoring"].includes(view);
    if (needsSim && !simResults) {
      navigate(`/studies/${projectId}`, { replace: true });
    }
  }, [view, simResults]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Dynamic system prompt ────────────────────────────────────────────────────
  function buildSystemPrompt() {
    let p = `You are the Augura evidence intelligence assistant.
Answer questions about this client's evidence profile, study design, and regulatory strategy.
Base all numbers and claims strictly on the data provided in this prompt — do not hallucinate or invent statistics. If a number is not in the prompt, say you don't have that information rather than guessing. Keep responses under 250 words unless the user explicitly asks for more detail. Use plain English — avoid jargon and explain technical terms when you use them. Use markdown formatting: **bold** for key terms, bullet points for lists, ## for section headings.
When referencing specific evidence or statistics, cite the source in brackets e.g. [PubMed], [ClinicalTrials], [MAUDE], [FDA Guidance], [Augura corpus]. Only cite sources that are in the data provided to you.

CURRENT VIEW: ${view}

CLIENT PROFILE:
Active client: ${tenantProfile?.name ?? defaults.displayName}
Clinical domains: ${clientDomains.join(', ')}
${clientEvidenceTypes.length ? `Evidence focus: ${clientEvidenceTypes.join(', ')}\n` : ''}Product: ${product || "Not specified"}
Users: ${users || "Not specified"}
Outcomes: ${outcome || "Not specified"}`;

    if (e1Profile) {
      p += `

AGENT PROFILING RESULTS:
- Study design: ${e1Profile.design_type ?? "N/A"}
- Primary endpoint: ${e1Profile.endpoint ?? "N/A"}
- Feasibility score: ${e1Profile.feasibility_score ?? "N/A"}%
- Risk signal (MAUDE): ${e1Profile.risk_signal ?? "Unknown"}
- Population: ${e1Profile.population ?? "N/A"}
- Agent reasoning: ${e1Profile.agent_reasoning ?? "N/A"}`;

      if (e1Profile.pubmed_evidence_count != null || e1Profile.open_trials_count != null) {
        p += `

SOURCE COUNTS:
- PubMed studies: ${e1Profile.pubmed_evidence_count ?? "N/A"}
- ClinicalTrials records: ${e1Profile.open_trials_count ?? "N/A"}
- MAUDE adverse events: ${e1Profile.adverse_event_count ?? "N/A"}`;
      }

      if (e1Profile.risk_dimensions?.length) {
        p += "\n\nRISK DIMENSIONS (0–100, higher = more risk):";
        e1Profile.risk_dimensions.forEach(d => {
          p += `\n- ${d.name}: ${d.score}/100 — ${d.rationale}`;
        });
      }

      if (e1Profile.opportunity_dimensions?.length) {
        p += "\n\nOPPORTUNITY DIMENSIONS (0–100, higher = stronger opportunity):";
        e1Profile.opportunity_dimensions.forEach(d => {
          p += `\n- ${d.name}: ${d.score}/100 — ${d.rationale}`;
        });
      }

      if (e1Profile.relevant_guidance?.length) {
        p += "\n\nRELEVANT REGULATORY GUIDANCE:";
        e1Profile.relevant_guidance.slice(0, 3).forEach(g => {
          p += `\n- ${g.title} (${g.date}) — ${g.framework}`;
        });
      }

      if (e1Profile.referenced_docs?.length) {
        p += `\n\nDOCUMENTS RETRIEVED THIS RUN: ${e1Profile.referenced_docs.length}`;
        const top5 = e1Profile.referenced_docs.slice(0, 5);
        p += "\nTop documents:\n" + top5.map((d, i) => `${i + 1}. ${d.title ?? d.canonical_url ?? "Untitled"}`).join("\n");
      }
    }

    return p;
  }

  // ── Dynamic suggestion chips ──────────────────────────────────────────────────
  function buildSuggestions() {
    const done = agentStep === "done";
    switch (view) {
      case "profiling_run":
        return done && e1Profile ? [
          "Why this study design?",
          "What did MAUDE show?",
          "Top evidence gaps?",
          "Strongest signal found?",
        ] : [
          "What data do you need?",
          "How long does this take?",
          "Which sources are searched?",
        ];
      case "profile":
        return [
          "Why this risk score?",
          "Best regulatory pathway?",
          "Strongest opportunity here?",
          "How does this benchmark?",
        ];
      case "studytype":
        return [
          "Main recruitment risk?",
          "How to control confounding?",
          "Realistic timeline?",
          "Budget estimate?",
        ];
      case "outcomes":
        return [
          "Why this primary endpoint?",
          "Alternative endpoints?",
          "Payer requirements here?",
        ];
      case "datacheck":
        return [
          "What data is missing?",
          "Can we use existing data?",
          "Data quality concerns?",
        ];
      case "causal":
        return [
          "What is a confounder?",
          "How to handle selection bias?",
          "Adjust for medication use?",
        ];
      case "design":
        return [
          "Why mixed-effects model?",
          "Sample size rationale?",
          "Regulatory alignment?",
        ];
      case "simulation":
        return [
          "What does power mean?",
          "Why this estimator?",
          "Conservative vs optimistic?",
        ];
      case "sensitivity":
        return [
          "Is the result robust?",
          "What drives sensitivity bands?",
          "E-value threshold for DiGA?",
        ];
      case "report":
        return [
          "Key findings to highlight?",
          "What claims can we make?",
          "Limitations to disclose?",
        ];
      case "monitoring":
        return [
          "Is the effect stable?",
          "Any concerning drift?",
          "When to re-analyse?",
        ];
      default:
        return [
          "What does this show?",
          "What are the key risks?",
          "Recommended next step?",
        ];
    }
  }

  const chatProps = {
    history:     chatHistory,
    onHistory:   setChatHistory,
    system:      buildSystemPrompt(),
    suggestions: buildSuggestions(),
  };

  function go(id) {
    // Reset agent to input state when navigating back to Data Input
    if (id === "assistant" && agentStep === "running") setAgentStep("input");
    if (id === "cockpit") navigate(`/studies/${projectId}`);
    else if (["history", "lineage", "settings"].includes(id)) navigate(`/studies/${projectId}/${id}`);
    else navigate(`/studies/${projectId}/workflow/${id}`);
    window.scrollTo(0, 0);
  }
  function onDone(profile) { setE1Profile(profile || null); setReady(true); setAgentStep("done"); setCompletedTab(null); go("profiling_run"); }
  function onRunStart(snapshot) { if (snapshot) setLastRunInputs(snapshot); go("profiling_run"); }

  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* Chrome (TopBar) provided by the unified shell. The study is ONE persistent
          surface: breadcrumb + header + left rail (StudyShell), with the main panel
          swapping between the Overview dashboard and a workflow step. */}
      <StudyShell
        study={cockpitStudy}
        go={go}
        onExit={() => navigate('/studies')}
        ctx={{ hasDataset, profileReady, completedTab, lockedEstimator, currentView: view }}
      >
        {/* Overview dashboard — the study home (needs-attention · causal question · readiness) */}
        <div className={`max-w-[640px] ${view === "cockpit" ? "block" : "hidden"}`}>
          <Rail study={cockpitStudy} go={go} />
        </div>

        {/* Step content — ProfilingAssistant stays mounted so its agent loop survives navigation */}
        <div className={view === "cockpit" ? "hidden" : "block"}>
        {simLoading && <SimulationLoadingScreen estimators={selectedEstimators} studyType={studyType} />}

        {/* ProfilingAssistant — always mounted so agent loop survives tab navigation */}
        <div className={!simLoading && view === "assistant" ? "" : "hidden"}>
          <ProfilingAssistant
            onDone={onDone}
            onRunStart={onRunStart}
            onStepsChange={setAgentSteps}
            lastRunInputs={lastRunInputs}
            e1Profile={e1Profile}
            product={product} setProduct={setProduct}
            users={users} setUsers={setUsers}
            outcome={outcome} setOutcome={setOutcome}
            onCohortSelect={(name, rowCount) => { setSelectedCohort(name); ssStore("selectedCohort", name, SS_KEY); if (rowCount != null) setUploadedRowCount(rowCount); }}
            selectedCohort={selectedCohort}
            uploadedData={uploadedData} onUploadData={(data) => { setUploadedData(data); if (!data) { setReady(false); setE1Profile(null); setCompletedTab(null); } }}
            agentStep={agentStep} onAgentStep={setAgentStep}
            hasDataset={hasDataset}
            displayName={defaults.displayName}
            tenantSlug={projectId ?? FALLBACK_PROJECT_ID}
            studyDesigns={studyDesigns}
            agentSources={agentSources}
            clientDomains={clientDomains}
            clientTagline={defaults.tagline}
            clientEndpoints={defaults.endpoints ?? []}
            pendingRunToken={pendingRunToken}
          />
        </div>

        {!simLoading && <>
          {view==="dataset_verify" && <DatasetVerification
            uploadedData={uploadedData}
            onUploadData={(data) => { setUploadedData(data); if (!data) { setReady(false); setE1Profile(null); setCompletedTab(null); setVariableMappings({}); setVariableCheckResult(null); } }}
            product={product} users={users} outcome={outcome}
            tenantSlug={projectId ?? FALLBACK_PROJECT_ID}
            selectedCohort={selectedCohort}
            onCohortSelect={(name, rowCount) => { setSelectedCohort(name); ssStore("selectedCohort", name, SS_KEY); if (rowCount != null) setUploadedRowCount(rowCount); }}
            variableMappings={variableMappings}
            setVariableMappings={setVariableMappings}
            variableCheckResult={variableCheckResult}
            setVariableCheckResult={setVariableCheckResult}
            onBack={() => go("assistant")}
            onRunProfiling={() => { setAgentStep("input"); setPendingRunToken(t => t + 1); go("profiling_run"); }}
          />}
          {view==="profiling_run" && <ProfilingRun steps={agentSteps} agentStep={agentStep} e1Profile={e1Profile} product={product} users={users} outcome={outcome} onViewProfile={()=>go("profile")} profileReady={profileReady} chatProps={chatProps} clientDomains={clientDomains} clientEvidenceTypes={clientEvidenceTypes} lastRunInputs={lastRunInputs} onReRun={() => { setAgentStep("input"); setPendingRunToken(t => t + 1); go("profiling_run"); }} agentSources={agentSources} />}
          {view==="profile"     && <ProductProfile     onNext={()=>{ completeTab("profile");    go("outcomes");    }} e1Profile={e1Profile} product={product} users={users} outcome={outcome} partnerLabel={defaults.partnerLabel} benchmarkMeta={defaults.benchmarkMeta} chatProps={chatProps} />}
          {view==="outcomes"    && <OutcomeSelection   onNext={()=>{ completeTab("outcomes");   go("causal");      }} onBack={()=>go("profile")} product={product} users={users} outcome={outcome} selectedOutcome={selectedOutcome} setSelectedOutcome={setSelectedOutcome} selectedCohort={selectedCohort} cqExposure={cqExposure} setCqExposure={setCqExposure} cqPopulation={cqPopulation} setCqPopulation={setCqPopulation} partnerLabel={defaults.partnerLabel} hasEngagementCol={hasEngagementCol} projectEndpoints={defaults.endpoints ?? []} chatProps={chatProps} />}
          {view==="causal"      && <CausalModel        onBack={()=>go("outcomes")}    onNext={()=>{ completeTab("causal");     go("datacheck");   }} studyType={studyType} e1Profile={e1Profile} product={product} outcome={outcome} dagCache={dagCache} setDagCache={setDagCache} selectedOutcome={selectedOutcome} selectedCohort={selectedCohort} cqExposure={cqExposure} cqPopulation={cqPopulation} partnerLabel={defaults.partnerLabel} candidateOutcomes={defaults.endpoints ?? []} datasetVariables={datasetVariables} />}
          {view==="datacheck"   && <DataAvailability   onNext={()=>{ completeTab("datacheck");  go("studytype");   }} onBack={()=>go("causal")} product={product} users={users} outcome={outcome} selectedOutcome={selectedOutcome} selectedCohort={selectedCohort} partnerLabel={defaults.partnerLabel} hasEngagementCol={hasEngagementCol} chatProps={chatProps} datasetVariables={datasetVariables} />}
          {view==="studytype"   && <StudyType          onNext={({ approach, design, estimand })=>{ setStudyType(approach); setStudyDesign(design); setStudyEstimand(estimand); completeTab("studytype"); go("design"); }} onBack={()=>go("datacheck")} product={product} users={users} outcome={outcome} partnerLabel={defaults.partnerLabel} chatProps={chatProps} />}
          {view==="design"      && <StudyDesign        onBack={()=>go("studytype")}   onNext={(est)=>{
            completeTab("design");
            setSelectedEstimators(est);
            setSimLoading(true);
            setTimeout(() => { setSimLoading(false); go("simulation"); }, 4500);
          }} studyType={studyType} studyDesign={studyDesign} studyEstimand={studyEstimand} partnerLabel={defaults.partnerLabel} />}
          {view==="simulation"  && <SimulationEngine   onBack={()=>go("design")}      onNext={(data)=>{ setLockedEstimator(data.estimator); setSimResults(data); go("results"); }} e1Profile={e1Profile} outcome={outcome} studyType={studyType} selectedEstimators={selectedEstimators} selectedCohort={selectedCohort} selectedOutcome={selectedOutcome} uploadedRowCount={uploadedRowCount} partnerLabel={defaults.partnerLabel} />}
          {view==="results"     && <ResultsView      onBack={()=>go("simulation")} onNext={()=>go("sensitivity")} simResults={simResults} dagCache={dagCache} partnerLabel={defaults.partnerLabel} />}
          {view==="sensitivity" && <ErrorBoundary><SensitivityView  simResults={simResults} onBack={()=>go("results")}      onNext={()=>go("report")} chatProps={chatProps} partnerLabel={defaults.partnerLabel} /></ErrorBoundary>}
          {view==="report"      && <ReportView       simResults={simResults} onBack={()=>go("sensitivity")}  onNext={()=>go("monitoring")} partnerLabel={defaults.partnerLabel} chatProps={chatProps} studyId={projectId} />}
          {view==="monitoring"  && <MonitoringView   simResults={simResults} onBack={()=>go("report")} partnerLabel={defaults.partnerLabel} chatProps={chatProps} />}
          {view==="history"     && <StudyHistory  study={cockpitStudy} />}
          {view==="lineage"     && <StudyLineage  study={cockpitStudy} />}
          {view==="settings"    && <StudySettings study={cockpitStudy} projectId={projectId} />}
        </>}
        </div>
      </StudyShell>

    </div>
  );
}
