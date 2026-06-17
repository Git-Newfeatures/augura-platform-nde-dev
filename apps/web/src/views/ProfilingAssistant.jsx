import { useState, useEffect, useRef } from "react";
import { Sparkles, AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/api";
import { InfoBar } from "../ui/components";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 0: PROFILING ASSISTANT
// ─────────────────────────────────────────────────────────────────────────────
const STUDY_DESIGN_FALLBACK = {
  rct_parallel:             "Parallel-group RCT",
  rct_crossover:            "Crossover RCT",
  single_arm:               "Single-arm trial",
  prospective_cohort:       "Prospective cohort",
  retrospective_cohort:     "Retrospective cohort",
  registry:                 "Registry study",
  case_control:             "Case-control",
  pre_post:                 "Pre-post analysis",
  difference_in_diff:       "Difference-in-differences",
  propensity_matched:       "Propensity score matching",
  interrupted_ts:           "Interrupted time series",
  regression_discontinuity: "Regression discontinuity",
  parametric_bootstrap:     "Parametric bootstrap",
};

const DOC_TYPE_FALLBACK = {
  pubmed:        "pubmed",
  clinicaltrials:"clinicaltrials",
  maude:         "maude",
  fda_guidance:  "fda_guidance",
};

export default function ProfilingAssistant({ onDone, onRunStart, onStepsChange, product, setProduct, users, setUsers, outcome, setOutcome, uploadedData, agentStep, onAgentStep, displayName, tenantSlug, clientDomains = [], clientTagline = "", clientEndpoints = [], pendingRunToken = 0 }) {
  const [step, setStep_]        = useState(() => agentStep || "input");
  const [, setSteps]       = useState([]);
  function setStep(s) { setStep_(s); onAgentStep?.(s); }


  // Sync internal step when parent resets agentStep (e.g. after navigating back to Data Input)
  useEffect(() => {
    if (agentStep && agentStep !== step) setStep_(agentStep);
  }, [agentStep]); // eslint-disable-line react-hooks/exhaustive-deps
  const [agentError, setAgentError]       = useState(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const dismissedAtRef = useRef(null);

  // Reset the "Keep existing" dismissal whenever the user makes a new change after dismissing.
  // We track what the inputs looked like when the user dismissed, and re-show the banner
  // as soon as they diverge from that snapshot (not just from lastRunInputs).
  useEffect(() => {
    if (!bannerDismissed) { dismissedAtRef.current = null; return; }
    if (!dismissedAtRef.current) { dismissedAtRef.current = { product, users }; return; }
    if (product.trim() !== dismissedAtRef.current.product.trim() ||
        users.trim()   !== dismissedAtRef.current.users.trim()) {
      setBannerDismissed(false);
      dismissedAtRef.current = null;
    }
  }, [product, users, bannerDismissed]);

  const [localChecks, setLocalChecks] = useState([]);

  useEffect(() => {
    if (uploadedData && localChecks.length === 0) runLocalChecks(uploadedData);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function runLocalChecks(data) {
    if (!data) { setLocalChecks([]); return; }
    const { sheets } = data;
    const checks = [];

    const ID_COLS = ["member_id","user_id","patient_id","participant_id","id","subject_id"];
    sheets.forEach(sheet => {
      const ci = sheet.headers.findIndex(h => ID_COLS.includes(String(h).toLowerCase()));
      if (ci < 0) return;
      const ids = sheet.data.map(r => r[ci]).filter(v => v !== "" && v != null);
      const dupes = ids.length - new Set(ids).size;
      if (dupes > 0) {
        checks.push({ label:"Duplicate IDs", status:"error",
          message:`${dupes} duplicate ${sheet.headers[ci]} value${dupes>1?"s":""} in "${sheet.name}" — each member must appear once per timepoint.` });
      }
    });
    if (!checks.find(c => c.label === "Duplicate IDs")) {
      checks.push({ label:"Duplicate IDs", status:"ok", message:"No duplicate member IDs detected." });
    }

    const RANGES = [
      { patterns:/hba1c/i,           min:4,   max:15,  unit:"%" },
      { patterns:/^ldl/i,            min:30,  max:400, unit:"mg/dL" },
      { patterns:/hs_crp|hs-crp|crp/i, min:0, max:100, unit:"mg/L" },
      { patterns:/^bmi$/i,           min:10,  max:70,  unit:"kg/m²" },
      { patterns:/^age$/i,           min:18,  max:100, unit:"years" },
    ];
    const rangeIssues = [];
    sheets.forEach(sheet => {
      sheet.headers.forEach((h, ci) => {
        const rule = RANGES.find(r => r.patterns.test(String(h)));
        if (!rule) return;
        const vals = sheet.data.map(r => parseFloat(r[ci])).filter(v => !isNaN(v));
        if (!vals.length) return;
        const outOfRange = vals.filter(v => v < rule.min || v > rule.max);
        if (outOfRange.length > 0) {
          rangeIssues.push(`${h}: ${outOfRange.length} value${outOfRange.length>1?"s":""} outside ${rule.min}–${rule.max} ${rule.unit}`);
        }
      });
    });
    checks.push(rangeIssues.length > 0
      ? { label:"Value ranges", status:"warn",
          message:`Out-of-range values detected — ${rangeIssues.join(" · ")}. Check units or data entry errors.` }
      : { label:"Value ranges", status:"ok", message:"All numeric columns within expected clinical ranges." }
    );

    const tpColPatterns = /timepoint_months|visit|timepoint|follow_up/i;
    const idColPatterns = /member_id|user_id|patient_id|participant_id/i;
    let longitudinalCheck = null;
    sheets.forEach(sheet => {
      if (longitudinalCheck) return;
      const tpIdx = sheet.headers.findIndex(h => tpColPatterns.test(String(h)));
      const idIdx = sheet.headers.findIndex(h => idColPatterns.test(String(h)));
      if (tpIdx < 0 || idIdx < 0) return;
      const byMember = {};
      sheet.data.forEach(row => {
        const id = row[idIdx]; const tp = parseFloat(row[tpIdx]);
        if (!id || isNaN(tp)) return;
        if (!byMember[id]) byMember[id] = new Set();
        byMember[id].add(tp);
      });
      const members  = Object.keys(byMember);
      const hasT12   = members.filter(id => byMember[id].has(12)).length;
      const bothPct  = members.length > 0 ? Math.round(hasT12 / members.length * 100) : 0;
      if (bothPct < 70) {
        longitudinalCheck = { label:"Longitudinal completeness", status:"warn",
          message:`Only ${hasT12}/${members.length} members (${bothPct}%) have a T12 record — high dropout will reduce statistical power.` };
      } else {
        longitudinalCheck = { label:"Longitudinal completeness", status:"ok",
          message:`${hasT12}/${members.length} members (${bothPct}%) have T0 and T12 records.` };
      }
    });
    if (!longitudinalCheck) {
      longitudinalCheck = { label:"Longitudinal completeness", status:"warn",
        message:"No timepoint column detected — could not verify T0/T12 pairing." };
    }
    checks.push(longitudinalCheck);

    const allColNames = sheets.flatMap(s => s.headers.map(h => String(h).toLowerCase().trim()));
    const colMatch = pat => allColNames.some(h => pat.test(h));

    if (!colMatch(/engagement|adherence|login|completion|activity/i)) {
      checks.push({ label:"Missing: engagement / exposure", status:"warn", blocking:false,
        message:`No engagement or adherence column detected. Columns found: ${allColNames.filter(h=>h).slice(0,12).join(", ")}` });
    }
    if (!colMatch(/timepoint|visit|follow.?up|t0|t6|t12|month|week/i)) {
      checks.push({ label:"Missing: timepoint", status:"warn", blocking:false,
        message:`No timepoint column detected. Columns found: ${allColNames.filter(h=>h).slice(0,12).join(", ")}` });
    }

    const INJECTION_RE = /ignore\s+(previous|prior|all)\s+(instructions?|prompts?)|system\s*:|<\|im_start\||jailbreak|\[INST\]/i;
    let injectionFound = false;
    sheets.forEach(sheet => {
      sheet.data.forEach(row => {
        row.forEach(cell => {
          if (typeof cell === "string" && INJECTION_RE.test(cell)) injectionFound = true;
        });
      });
    });
    checks.push(injectionFound
      ? { label:"Prompt injection", status:"error", blocking:true,
          message:"Suspicious instruction-like text found in dataset cells — data rejected to protect the AI agent." }
      : { label:"Prompt injection", status:"ok", message:"No adversarial patterns detected in cell values." }
    );

    setLocalChecks(checks);
  }

  const TOOL_LABELS = {
    search_pubmed:         "PubMed",
    search_clinicaltrials: "ClinicalTrials.gov",
    search_maude:          "MAUDE",
    search_fda_guidance:   "FDA Guidance",
  };

  const SUPABASE_URL  = import.meta.env.VITE_SUPABASE_URL;
  const SUPABASE_ANON = import.meta.env.VITE_SUPABASE_ANON_KEY;

  const AGENT_TOOLS = [
    { name:"search_pubmed",         description:"Search peer-reviewed clinical literature in PubMed for study precedents, effect sizes, endpoints, and comparable interventions.", input_schema:{ type:"object", properties:{ query:{type:"string"}, max_results:{type:"integer",default:10} }, required:["query"] } },
    { name:"search_clinicaltrials", description:"Search ClinicalTrials.gov for comparable study designs, sample sizes, and active trials.", input_schema:{ type:"object", properties:{ query:{type:"string"}, max_results:{type:"integer",default:10} }, required:["query"] } },
    { name:"search_maude",          description:`Search MAUDE adverse event database for device safety signals and incident rates. Derive query terms directly from the CLIENT CONTEXT above — use the specific device category, physiological signals monitored, and failure modes relevant to that product (e.g. for fetal monitoring: 'fetal heart rate monitor malfunction', 'remote patient monitoring signal loss'; for glucose monitoring: 'continuous glucose monitor sensor failure'). Never use generic SaMD/DTx/digital health terms — MAUDE is indexed by concrete device names and event types. The client's PRIMARY ENDPOINTS and CLINICAL DOMAINS must anchor your search terms.`, input_schema:{ type:"object", properties:{ query:{type:"string"}, max_results:{type:"integer",default:10} }, required:["query"] } },
    { name:"search_fda_guidance",   description:"Search FDA regulatory guidance documents for applicable frameworks, SaMD requirements, and digital health policy.", input_schema:{ type:"object", properties:{ query:{type:"string"}, max_results:{type:"integer",default:5}  }, required:["query"] } },
  ];

  const clientCtxBlock = [
    `CLIENT: ${displayName ?? "Unknown"}`,
    clientTagline  ? `PRODUCT TYPE: ${clientTagline}` : null,
    clientEndpoints.length ? `PRIMARY ENDPOINTS: ${clientEndpoints.join(", ")}` : null,
    clientDomains.length   ? `CLINICAL DOMAINS: ${clientDomains.join(", ")}`   : null,
  ].filter(Boolean).join("\n");

  const AGENT_SYSTEM = `You are the Augura E1 Profiling Agent — a certified evidence generation intelligence system for healthcare AI and digital health companies.
CLIENT CONTEXT:
${clientCtxBlock}
YOUR TASK: Research the evidence landscape across four data sources and produce a structured risk/opportunity profile with study design recommendations. Focus on evidence relevant to the client's product type and clinical domains above.
SEARCH STRATEGY (3 LAYERS — execute in order, do NOT skip layers):
Level 1 — Wide source coverage:
- Search broadly across PubMed, ClinicalTrials, MAUDE, and FDA guidance where relevant.
- Map the evidence landscape before judging evidence quality.
Level 2 — Focused product/outcome search:
- Search narrower terms for product features, target users, collected data types, outcomes, and endpoints.
- Use source-specific language: PubMed uses conditions/outcomes/study designs; ClinicalTrials uses interventions/conditions/endpoints; FDA guidance uses device category/intended use/regulatory topic.
Level 3 — Risk, comparator, and regulatory gap-fill:
- Search comparable products/devices, safety signals, adverse events, failure modes, and regulatory constraints.
- For MAUDE, derive search terms from the CLIENT CONTEXT above — use the specific device category, monitored signals, and failure modes for this product. Never use generic SaMD/DTx/digital health terms. Never copy example terms from this prompt — generate terms that match the actual client product.
- Do not finalize after only broad retrieval if important evidence categories are missing.
Stop after 6–10 tool calls total.
OUTPUT FORMAT: Return a single valid JSON object (no markdown fences):
{"design_type":string(max 8 words),"endpoint":string(max 10 words),"feasibility_score":number,"risk_dimensions":[{"name":string,"score":number,"rationale":string}],"opportunity_dimensions":[{"name":string,"score":number,"rationale":string}],"study_designs":[{"code":string,"feasibility_score":number}],"agent_reasoning":string}
DO NOT POPULATE: open_trials_count, pubmed_evidence_count, adverse_event_count, fda_guidance_count, risk_signal. These are computed deterministically from the retrieved corpus and injected by the system. Do not invent specific document counts in agent_reasoning beyond what appears in the EVIDENCE CORPUS SEARCH RESULTS section provided to you.
SCORING RULES:
- All scores are integers 0–5 (not 0–100).
- risk_dimensions: EXACTLY 6 items in this order. score 0–5 where 5 = highest risk. 0–1 = low/controlled; 2–3 = monitor; 4–5 = critical. Items: (1) Safety Signals & Failure Modes [search MAUDE, PubMed adverse events], (2) Generalizability, Equity & Robustness Risk [diverse populations, external validation; search PubMed, ClinicalTrials], (3) Implementation & Adoption Risk [engagement drop-off, alert fatigue; search PubMed], (4) Limited Actionability & Intervention Linkage [protocolized vs vague; search PubMed, ClinicalTrials arms], (5) Limited Scalability & Market Breadth [population size, care settings; search PubMed, ClinicalTrials], (6) Limited Reproducibility & Consistency [result consistency, independent validations; search PubMed meta-analyses]. You MUST return all 6.
- opportunity_dimensions: EXACTLY 6 items in this order. score 0–5 where 5 = strongest opportunity. 0–1 = weak; 2–3 = moderate; 4–5 = strong. Items: (1) Clinical Need & Indication Strength [disease burden, unmet need; search PubMed], (2) Evidence Strength & Credibility [RCT > prospective > retrospective; search PubMed, ClinicalTrials], (3) Effect Size & Outcome Impact Signal [magnitude of benefit; search PubMed, ClinicalTrials], (4) Actionability & Intervention Linkage [protocol, alert, treatment change; search PubMed, ClinicalTrials], (5) Reproducibility & Consistency of Evidence [independent studies, consistency; search PubMed, ClinicalTrials], (6) Regulatory & Reimbursement Pathway Clarity [frameworks, reimbursement precedent; search FDA guidance, PubMed HTA]. You MUST return all 6.
- feasibility_score: integer 0–5.
- study_designs: EXACTLY 3 designs ranked by feasibility_score descending. study_designs[].feasibility_score is also 0–5.
- study_designs[].code must be exactly one of: rct_parallel, rct_crossover, single_arm, prospective_cohort, retrospective_cohort, registry, case_control, pre_post, difference_in_diff, propensity_matched, interrupted_ts, regression_discontinuity, parametric_bootstrap
- design_type: 8 words maximum.
- endpoint: 10 words maximum.
- agent_reasoning: maximum 60 words. End with a complete sentence. Describe the evidence landscape and overall profile only — do NOT name specific estimators (e.g. "propensity score matching", "TMLE", "IPW", "difference-in-differences"), do NOT prescribe adjustment sets, and do NOT recommend a specific study design. Estimator and design choices are made by the user in later stages of the platform. Reasoning should stay at the level of: feasibility of a study, evidence strength, key risks, and regulatory context.
RATIONALE RULES:
- Maximum 10 words per rationale. Use numbers and key terms only. No complete sentences. Always start with the evidence count or finding.
- risk rationale: score 0–1: explain why risk is low. score 2–3: state the key uncertainty. score 4–5: explain the main risk driver.
- opportunity rationale: score 4–5: explain the main strength. score 2–3: state the key opportunity factor. score 0–1: explain the main gap.
- Examples (use as STYLE templates only — do NOT copy specific numbers or device names; cite numbers from the actual evidence retrieved): score 1 risk: "No adverse events found in MAUDE for this device category". score 3 risk: "Self-selected users underrepresent low-income populations". score 4 risk: "No independent external validation study exists". score 4 opp: "Multiple PubMed studies confirm benefit in this domain". score 2 opp: "Limited by small single-site cohort, no validation". score 1 opp: "No head-to-head comparator trials found".
- Never repeat the dimension name in the rationale.
- Rationales must NOT prescribe a specific estimator (e.g. propensity score matching, TMLE, IPW, difference-in-differences) or adjustment set — those choices belong to later stages of the platform. Rationales describe the evidence and risk landscape only.
REGULATORY CONTEXT: Reference regulatory frameworks that are relevant to the client's clinical domains and markets described in CLIENT CONTEXT above. Prioritise frameworks applicable to the client's geography and indication. For EU digital health: DiGA (Germany), HAS (France), EU MDR Art. 22. For US: FDA SaMD, 510(k), De Novo. Only reference frameworks that are plausibly relevant to the client's product type.
COMPARABLE PRODUCTS: Reference digital health products that are comparable to the client's product type and clinical domains described in CLIENT CONTEXT above. Use evidence found in the corpus — do not default to a fixed list of brand names unless they appear in search results.
SCOPE: Your task is to characterise the literature and regulatory landscape for the client's product type. You do NOT have access to the user's uploaded dataset and you must NOT speculate about it. Do not cite specific N values, sample sizes, exposure-group sizes, biomarker distributions, or column names. Dataset-specific reasoning happens in later stages of the platform (Variable Availability, Simulation, Results) — not here. If you find yourself wanting to write "Dataset N=...", "the uploaded data shows...", or any similar phrase, replace it with a corpus-level claim (e.g. "the literature supports...", "comparable studies report...").
CRITICAL: risk_dimensions array MUST have exactly 6 elements. opportunity_dimensions array MUST have exactly 6 elements. study_designs array MUST have exactly 3 elements. Return ONLY valid JSON.
CRITICAL: Return raw JSON only. No markdown fences. No \`\`\`json. No \`\`\` wrapper. Start your response with { and end with }.`;

  async function run() {
    setStep("running"); setSteps([]); setAgentError(null); setBannerDismissed(false);
    onRunStart?.({ product, users, projectId: tenantSlug, ranAt: new Date().toISOString() });
    const productDescription = `${product}\n\nUser characteristics:\n${users}\n\nOutcomes of interest:\n${outcome}`;
    const addLine = (t) => setSteps(p => { const next = [...p, t]; onStepsChange?.(next); return next; });
    addLine("__INIT__");

    try {
      // Server-side profiling: the whole tool-use loop + corpus retrieval runs on the
      // backend (POST /agents/profiling/stream, NDJSON). We translate its events into
      // the token protocol that ProfilingRun renders.
      const res = await apiFetch("/agents/profiling/stream", {
        method: "POST",
        body: JSON.stringify({
          system: AGENT_SYSTEM,
          tools: AGENT_TOOLS,
          messages: [{ role: "user", content: productDescription }],
          product_description: productDescription,
        }),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`stream ${res.status} ${detail.slice(0, 200)}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let profile = null;
      let synthSignaled = false;
      const flush = (chunk) => {
        buf += chunk;
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          const s = line.trim();
          if (!s) continue;
          let ev; try { ev = JSON.parse(s); } catch { continue; }
          if (ev.type === "tool_use") {
            const q = String(ev.text || "").replace(/^→\s*\[[^\]]*\]\s*/, "");
            addLine(`__QUERY:${ev.tool}:${q}__`);
          } else if (ev.type === "tool_result") {
            addLine(`__RESULT:${ev.tool}:${ev.count ?? 0}__`);
          } else if (ev.type === "log") {
            if (/synthesis|synthesising|synthesizing/i.test(ev.text || "")) {
              if (!synthSignaled) { addLine("__SYNTH__"); synthSignaled = true; }
            } else {
              addLine(ev.text);
            }
          } else if (ev.type === "done") {
            profile = ev.profile || null;
          } else if (ev.type === "error") {
            addLine(`⚠ ${ev.text}`);
            setAgentError(ev.text);
          }
        }
      };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        flush(decoder.decode(value, { stream: true }));
      }
      flush(decoder.decode());

      if (profile) {
        const d = profile;
        if (!synthSignaled) addLine("__SYNTH__");
        addLine(`__SYNTHDATA:${JSON.stringify({ design: d.design_type, endpoint: d.endpoint })}__`);
        addLine(`✓ Profile complete — ${d.pubmed_evidence_count ?? "?"} comparable studies · MAUDE ${(d.risk_signal || "").toLowerCase()} risk · ${d.study_designs?.length || 3} study designs ready`);
        window.__e1Profile = profile;
        setStep("done");
        onDone?.(profile);
      } else {
        setStep("input");
        if (!agentError) setAgentError("Profiling did not return a profile.");
      }
    } catch (err) {
      const msg = err?.message ?? String(err);
      setAgentError(msg.includes("503") ? "Profiling unavailable: the LLM/embedding API keys aren't configured yet." : `Profiling failed: ${msg}`);
      addLine(`⚠ Agent failed: ${msg}`);
      setStep("input");
    }
  }

  // Auto-trigger run when parent increments pendingRunToken (used by Re-Run button
  // on Profiling Run tab — navigates here AND starts a fresh agent run in one step)
  useEffect(() => {
    // The profiling agent is corpus-only (it never reads the uploaded dataset), so
    // it can run without one — don't gate on hasDataset.
    if (pendingRunToken > 0) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingRunToken]);

  const textareaClass =
    "w-full resize-y rounded-lg border border-border bg-card px-3.5 py-3 text-[13px] leading-[1.6] text-foreground outline-none focus:ring-2 focus:ring-primary/15";

  return (
    <div className="flex flex-col gap-4">
      {displayName && (
        <div className="mb-1 text-[13px] font-semibold text-foreground">
          {displayName}
        </div>
      )}
      <InfoBar sources={["MAUDE","PubMed","ClinicalTrials.gov","FDA Guidance"]}>
        <strong>Profiling Assistant.</strong> Enter your product, user, and outcome details.
        The Augura agent will autonomously query the evidence corpus and produce a risk/opportunity profile with study design recommendations.
      </InfoBar>

      {agentError && step !== "running" && (
        <div className="flex items-start gap-2.5 rounded-xl border border-[#C0392B]/40 bg-[#FCEBEB] px-4 py-3 text-[12.5px] leading-relaxed text-[#C0392B]">
          <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
          <div>
            <strong>Agent error:</strong> {agentError}
            <button onClick={() => { setAgentError(null); run(); }}
              className="ml-3 cursor-pointer border-none bg-transparent text-[12px] font-semibold text-[#C0392B] underline">Retry</button>
            <button onClick={() => setAgentError(null)}
              className="ml-3 cursor-pointer border-none bg-transparent text-[12px] text-[#C0392B] underline">Dismiss</button>
          </div>
        </div>
      )}

      {step !== "running" && (
        <div className="grid grid-cols-2 items-start gap-4">

          {/* LEFT — Product characteristics (full height) */}
          <Card className="flex flex-col gap-0 rounded-xl p-5">
            <div className="mb-1.5 text-[13px] font-semibold text-foreground">
              Product characteristics
            </div>
            <div className="mb-3 text-[12px] leading-relaxed text-muted-foreground">
              Describe your digital health product: what it does, how it works, key differentiators,
              and the clinical problem it addresses.
            </div>
            <textarea value={product} onChange={e=>setProduct(e.target.value)}
              className={`${textareaClass} min-h-[280px] flex-1 resize-none`} />
          </Card>

          {/* RIGHT — User characteristics + outcomes (no dataset upload — that lives in 1b) */}
          <div className="flex flex-col gap-4">

            {/* User characteristics */}
            <Card className="block gap-0 rounded-xl p-5">
              <div className="mb-2 text-[13px] font-semibold text-foreground">
                User characteristics
              </div>
              <textarea value={users} onChange={e=>setUsers(e.target.value)}
                placeholder="e.g. Prediabetic adults, HbA1c 5.7–6.4%, age 35–65, France/UK/Ireland/Portugal…"
                className={`${textareaClass} min-h-[80px] resize-none`} />
            </Card>

            {/* Outcomes of interest */}
            <Card className="block gap-0 rounded-xl p-5">
              <div className="mb-2 text-[13px] font-semibold text-foreground">
                Outcomes of interest
              </div>
              <textarea value={outcome} onChange={e=>setOutcome(e.target.value)}
                placeholder="e.g. HbA1c change at 12 months, LDL-C, hs-CRP, T2D progression…"
                className={`${textareaClass} min-h-[80px] resize-none`} />
            </Card>
          </div>

        </div>
      )}



      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
