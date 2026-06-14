import { useMemo, useRef, useState, useEffect } from "react";
import { CheckCircle2, RotateCw } from "lucide-react";
import { Card } from "../ui/components";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CorpusPanelEmbed } from "../CorpusPanelEmbed";
import InlineChatbot from "../components/InlineChatbot";

// ── Helpers ───────────────────────────────────────────────────────────────────
function ageLabel(dateStr) {
  if (!dateStr) return "";
  const secs = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (secs < 60)        return "just now";
  if (secs < 3600)      return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400)     return `${Math.floor(secs / 3600)}h ago`;
  if (secs < 86400 * 7) return `${Math.floor(secs / 86400)}d ago`;
  return new Date(dateStr).toLocaleDateString("en-US", { month:"short", day:"numeric" });
}

// ── Source display config ─────────────────────────────────────────────────────
const SOURCE_CONFIG = [
  { key: "search_pubmed",         label: "PubMed",        resultFn: (n) => n > 0 ? `Found ${n} stud${n === 1 ? "y" : "ies"}` : "No results" },
  { key: "search_clinicaltrials", label: "ClinicalTrials", resultFn: (n) => n > 0 ? `Found ${n} trial${n === 1 ? "" : "s"}` : "No results" },
  { key: "search_maude",          label: "MAUDE",         resultFn: (n) => n > 0 ? `Found ${n} event${n === 1 ? "" : "s"}` : "No adverse events" },
  { key: "search_fda_guidance",   label: "FDA Guidance",  resultFn: (n) => n > 0 ? `Found ${n} doc${n === 1 ? "" : "s"}` : "No documents" },
];

// ── Parse structured tokens from the steps array ──────────────────────────────
function parseSteps(steps) {
  const sources = Object.fromEntries(
    SOURCE_CONFIG.map(({ key }) => [key, { queried: false, hasResult: false, count: 0, calls: 0, error: false, queries: [] }])
  );
  let initDone = false;
  let synthStarted = false;
  let synthData = null;
  let synthStream = null;
  let completionLine = null;

  for (const line of steps) {
    if (line === "__INIT__")  { initDone = true; continue; }
    if (line === "__SYNTH__") { synthStarted = true; continue; }

    if (line.startsWith("__SYNTHSTREAM:")) {
      synthStream = line.slice(14, -2); // remove prefix + trailing __
      continue;
    }
    if (line.startsWith("__SYNTHDATA:")) {
      try {
        synthData = JSON.parse(line.slice(12, -2));
      } catch { /* ignore malformed */ }
      continue;
    }
    if (line.startsWith("__QUERY:")) {
      const inner = line.slice(8, -2); // "name:query" or just "name"
      const ci = inner.indexOf(":");
      const src = ci === -1 ? inner : inner.slice(0, ci);
      const q   = ci === -1 ? null  : inner.slice(ci + 1);
      if (sources[src]) { sources[src].queried = true; if (q) sources[src].queries.push(q); }
      continue;
    }
    if (line.startsWith("__RESULT:")) {
      const rest = line.slice(9, -2);
      const ci   = rest.lastIndexOf(":");
      const src  = rest.slice(0, ci);
      const n    = parseInt(rest.slice(ci + 1), 10) || 0;
      if (sources[src]) { sources[src].queried = true; sources[src].hasResult = true; sources[src].count = n; sources[src].calls += 1; }
      continue;
    }
    if (line.startsWith("__ERROR:")) {
      const src = line.slice(8, -2);
      if (sources[src]) sources[src].error = true;
      continue;
    }
    if (line.startsWith("✓ Profile complete")) {
      completionLine = line;
    }
  }

  const totalDocs = Object.values(sources).reduce((sum, s) => sum + s.count, 0);

  return { initDone, sources, synthStarted, synthData, synthStream, completionLine, totalDocs };
}

const DEV_MOCK_PROFILE = {
  agent_reasoning: "Sample profile — benchmarked against the Augura corpus. Run the live agent for a client-specific profile.",
  risk_dimensions: [
    { name:"Safety Signals & Failure Modes",               score:40,  rationale:"Low adverse event rate across comparable SaMD products." },
    { name:"Generalizability, Equity & Robustness Risk",   score:80,  rationale:"Studies concentrated on high-SES employer cohorts." },
    { name:"Implementation & Adoption Risk",               score:80,  rationale:"Median 40–60% engagement drop-off at 12 weeks in comparable DTx." },
    { name:"Limited Actionability & Intervention Linkage", score:60,  rationale:"Recommendation specificity varies across modules." },
    { name:"Limited Scalability & Market Breadth",         score:60,  rationale:"B2B contracting dependency limits access." },
    { name:"Limited Reproducibility & Consistency",        score:80,  rationale:"Effect sizes heterogeneous across studies." },
  ],
  opportunity_dimensions: [
    { name:"Clinical Need & Indication Strength",        score:100, rationale:"374M adults globally with IFG/IGT (IDF 2021)." },
    { name:"Evidence Strength & Credibility",            score:60,  rationale:"41% prospective/RCT designs in corpus." },
    { name:"Effect Size & Outcome Impact Signal",        score:80,  rationale:"HbA1c reductions of 0.3–0.5% in high-engagement cohorts." },
    { name:"Actionability & Intervention Linkage",       score:60,  rationale:"Protocolized interventions outperform vague lifestyle advice 2×." },
    { name:"Reproducibility & Consistency of Evidence",  score:60,  rationale:"I² >60% in comparable meta-analyses." },
    { name:"Regulatory & Reimbursement Pathway Clarity", score:80,  rationale:"DiGA provisional listing achievable within 12 months." },
  ],
  feasibility_score: 72,
};

export default function ProfilingRun({ steps = [], agentStep, e1Profile, chatProps = {}, clientDomains, clientEvidenceTypes, lastRunInputs = null, onReRun = null, agentSources = [] }) {
  const isDone    = agentStep === "done";
  const isRunning = agentStep === "running";

  const { initDone, sources, synthStarted, synthData, synthStream, completionLine, totalDocs } = useMemo(
    () => parseSteps(steps),
    [steps]
  );

  // ── Synthesis elapsed timer ─────────────────────────────────────────────────
  // Counts seconds since __SYNTH__ was emitted so the user can see progress
  // rather than a frozen screen during the 15–60s synthesis call.
  const synthStartRef = useRef(null);
  const [synthElapsed, setSynthElapsed] = useState(0);

  useEffect(() => {
    if (synthStarted && !synthStartRef.current) {
      synthStartRef.current = Date.now();
    }
    if (!synthStarted) {
      synthStartRef.current = null;
      setSynthElapsed(0);
    }
  }, [synthStarted]);

  useEffect(() => {
    if (!synthStarted || completionLine) return;
    const id = setInterval(() => {
      if (synthStartRef.current) {
        setSynthElapsed(Math.floor((Date.now() - synthStartRef.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(id);
  }, [synthStarted, completionLine]);

  const hasAnyStep = steps.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <style>{`
        @keyframes lp{0%,100%{opacity:.35}50%{opacity:1}}
        @keyframes sweep{0%{background-position:200% 0}100%{background-position:-200% 0}}
      `}</style>

      {/* Agent log card */}
      <Card>
        {/* Header */}
        <div className="mb-3 border-b border-border pb-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className={`flex items-center gap-1.5 text-[13px] font-semibold ${isDone ? "text-primary" : "text-foreground"}`}>
              {isDone && <CheckCircle2 size={15} className="flex-shrink-0" />}
              {isDone ? "Profile complete — ready to view" : isRunning ? "Querying evidence corpus" : "Profiling log"}
            </span>
            {/* Cached-run timestamp + Re-run button */}
            {isDone && lastRunInputs && (
              <div className="flex flex-shrink-0 items-center gap-2.5">
                <span className="text-[12px] text-muted-foreground">
                  {ageLabel(lastRunInputs.ranAt)} · {(lastRunInputs.product ?? "").slice(0, 40).trim()}{(lastRunInputs.product ?? "").length > 40 ? "…" : ""}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onReRun?.()}
                  className="h-7 gap-1.5 rounded-md px-2.5 text-[12px] text-muted-foreground"
                >
                  <RotateCw size={13} />
                  Re-run
                </Button>
              </div>
            )}
          </div>
          {/* Progress bar */}
          {(isRunning || isDone) && (
            <div className={`h-[3px] overflow-hidden rounded-sm ${isDone ? "bg-primary" : "bg-secondary"}`}>
              {isRunning && (
                <div
                  className="h-full rounded-sm"
                  style={{
                    background:"linear-gradient(90deg, transparent 0%, #047857 40%, #5DCAA5 60%, transparent 100%)",
                    backgroundSize:"200% 100%",
                    animation:"sweep 2s linear infinite",
                  }}
                />
              )}
            </div>
          )}
        </div>

        {/* Log body */}
        {!hasAnyStep ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center text-[12px] text-muted-foreground">
            <span>
              {isDone
                ? "Log not available — run completed before this session."
                : "The Augura agent searches PubMed, ClinicalTrials.gov, MAUDE and FDA guidance to build the evidence profile."}
            </span>
            {onReRun && (
              <Button
                onClick={() => onReRun()}
                className="h-auto rounded-lg px-4 py-2 text-[12.5px] font-semibold"
              >
                {isDone ? "Re-run profiling agent →" : "Run profiling agent →"}
              </Button>
            )}
          </div>
        ) : (
          <div className="font-mono text-[12px] leading-[1.95]">

            {/* Phase 1 — Init */}
            {initDone && (
              <div className="mb-2.5 font-semibold text-primary">
                ✓ Augura Profiling Agent (v1.0)
              </div>
            )}

            {/* Phase 2 — Per-source status rows */}
            {initDone && (
              <div className="mb-2.5 flex flex-col gap-px">
                {SOURCE_CONFIG.map(({ key, label: fallbackLabel, resultFn }) => {
                  const code      = key.replace(/^search_/, "");
                  const agentSrc  = agentSources.find(s => s.code === code);
                  const label     = agentSrc?.label ?? fallbackLabel;
                  const src       = sources[key];
                  let status;
                  if (src.error) {
                    status = <span className="text-[#B98900]">Error — skipped</span>;
                  } else if (!src.queried) {
                    status = <span className="text-muted-foreground/60">Waiting…</span>;
                  } else if (!src.hasResult) {
                    status = <span className="text-muted-foreground/60" style={{ animation:"lp 1.2s ease-in-out infinite" }}>Searching…</span>;
                  } else {
                    const count = src.count;
                    const dim   = count === 0;
                    let text;
                    if (agentSrc?.result_unit) {
                      const unit = agentSrc.result_unit;
                      if (code === "maude") {
                        text = count > 0 ? `Found ${count} ${unit}` : "No adverse events";
                      } else {
                        text = count > 0 ? `Found ${count} ${unit}` : "No documents";
                      }
                    } else {
                      text = resultFn(count);
                    }
                    // Show round count when the agent searched this source more than once
                    // (3-layer strategy does multiple rounds — total reflects all rounds).
                    const roundsSuffix = src.calls > 1 ? ` · ${src.calls} rounds` : "";
                    status = (
                      <span className={dim ? "font-normal text-muted-foreground" : "font-semibold text-primary"}>
                        {!dim && "✓ "}{text}{roundsSuffix}
                      </span>
                    );
                  }
                  return (
                    <div key={key} className="mb-0.5 flex flex-col gap-px">
                      <div className="flex items-baseline">
                        <span className="min-w-[148px] text-muted-foreground/70">[{label}]</span>
                        {status}
                      </div>
                      {src.queries.length > 0 && (
                        <div className="pl-[148px]">
                          {src.queries.map((q, i) => (
                            <div key={i} className="max-w-[460px] truncate font-mono text-[11.5px] text-muted-foreground/70">
                              ↳ "{q}"
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Phase 3 — Synthesis + completion */}
            {(synthStarted || completionLine) && (
              <div className="mt-0.5 border-t border-border pt-2.5">
                {/* Synthesis header — pulsing while running, shows elapsed seconds */}
                <div
                  className="font-semibold text-primary"
                  style={!completionLine ? { animation:"lp 1.2s ease-in-out infinite" } : undefined}
                >
                  {completionLine
                    ? "→ [Augura Engine] Synthesising findings across all sources"
                    : synthElapsed > 0
                      ? `→ [Augura Engine] Synthesising… ${synthElapsed}s`
                      : "→ [Augura Engine] Synthesising findings across all sources"}
                </div>

                {/* Live streaming synthesis text — last 120 chars of accumulated output */}
                {synthStream && !completionLine && (
                  <div className="mt-1 break-all pl-3 text-[12px] italic text-muted-foreground" style={{ fontFamily:"'Geist Variable', 'Geist', system-ui, sans-serif" }}>
                    {"..." + synthStream.slice(-120)}
                  </div>
                )}

                {/* Synthesis detail block — visible once synthData arrives */}
                {synthData && !completionLine && (
                  <div className="mt-1 flex flex-col gap-0.5 pl-3">
                    {synthData.design && (
                      <span className="text-[12.5px] text-muted-foreground">Recommended design: {synthData.design}</span>
                    )}
                    {synthData.endpoint && (
                      <span className="text-[12.5px] text-muted-foreground">Primary endpoint: {synthData.endpoint}</span>
                    )}
                  </div>
                )}

                {/* Completion line — shows unique doc count */}
                {completionLine && (
                  <>
                    <div className="mt-1 font-semibold text-primary">
                      ✓ Profile complete — {totalDocs} unique documents · MAUDE {(e1Profile?.risk_signal ?? "low").toLowerCase()} risk · {e1Profile?.study_designs?.length ?? 3} study designs ready
                    </div>
                    <div className="mt-1 pl-3 text-[12px] leading-[1.5] text-muted-foreground">
                      The Corpus Intelligence panel below shows the full indexed evidence corpus.
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </Card>

      {isDone && (
        <>
          {/* Corpus Intelligence panel */}
          <CorpusPanelEmbed
            referencedDocs={e1Profile?.referenced_docs ?? []}
            clientDomains={clientDomains ?? ["cardiometabolic", "preventive_health", "patient_monitoring"]}
            clientEvidenceTypes={clientEvidenceTypes ?? []}
            rawRetrievalCount={totalDocs}
            agentSources={agentSources}
          />

          {/* Inline chatbot */}
          <InlineChatbot {...chatProps}
          />
        </>
      )}
    </div>
  );
}
