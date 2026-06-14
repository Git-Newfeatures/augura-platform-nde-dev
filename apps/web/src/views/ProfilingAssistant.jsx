import { useState, useEffect, useRef } from "react";
import { isMockEnabled } from "@/mocks/mockMode";
import { Sparkles, AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoBar } from "../ui/components";

// ── Demo profile — bypasses the E1 agent for fast demos ──────────────────────
const DEMO_PROFILE = {
  pubmed_evidence_count: 701,
  risk_signal: "LOW",
  study_designs: ["retrospective_cohort", "pre_post", "external_matched"],
  risk_dimensions: [
    { name:"Safety Signals & Failure Modes",               score:2, rationale:"Low MAUDE adverse event rate for comparable SaMD/DTx products. No FDA recalls identified." },
    { name:"Generalizability, Equity & Robustness Risk",   score:4, rationale:"Evidence concentrated in high-SES employer cohorts; no independent external validation published." },
    { name:"Implementation & Adoption Risk",               score:4, rationale:"Digital therapeutics show 40–60% engagement drop-off at 12 weeks; alert fatigue is a known risk." },
    { name:"Limited Actionability & Intervention Linkage", score:3, rationale:"Recommendation specificity varies; protocolized arms outperform vague lifestyle advice in RCTs." },
    { name:"Limited Scalability & Market Breadth",         score:3, rationale:"Large target population but B2B contracting dependency; mainly urban/academic trial sites so far." },
    { name:"Limited Reproducibility & Consistency of Evidence", score:4, rationale:"Heterogeneous effect sizes across DTx studies; most evidence is single-team with no independent replication." },
  ],
  opportunity_dimensions: [
    { name:"Clinical Need & Indication Strength",        score:5, rationale:"Prediabetes and cardiometabolic risk represent a major disease burden. Digital platforms address a clear unmet gap in scalable preventive care." },
    { name:"Evidence Strength & Credibility",            score:3, rationale:"701-document corpus contains 286 prospective/RCT designs (41%); most digital preventive health evidence remains observational." },
    { name:"Effect Size & Outcome Impact Signal",        score:4, rationale:"HbA1c reductions of 0.3–0.5% in high-engagement cohorts are clinically meaningful and comparable to first-line pharmacological thresholds." },
    { name:"Actionability & Intervention Linkage",       score:3, rationale:"Recommendation modules linked to measurable behaviour change targets; protocolization could be strengthened." },
    { name:"Reproducibility & Consistency of Evidence",  score:3, rationale:"Directionally consistent results but high heterogeneity (I²>60%); limited independent external replication." },
    { name:"Regulatory & Reimbursement Pathway Clarity", score:4, rationale:"DiGA Germany fastest pathway (Lykon precedent); EU MDR Art. 22 wellness and HAS DSN also applicable." },
  ],
  // Documents the agent "retrieved" this run — populates the Corpus Intelligence panel.
  referenced_docs: [
    { source_id: "pubmed",         evidence_type: "rct",           title: "Digital lifestyle intervention and HbA1c in prediabetes: a randomized trial" },
    { source_id: "pubmed",         evidence_type: "meta_analysis", title: "Engagement with digital therapeutics and glycaemic outcomes: a systematic review" },
    { source_id: "clinicaltrials", evidence_type: "rct",           title: "Remote coaching for cardiometabolic risk reduction" },
    { source_id: "maude",          evidence_type: "adverse_event", title: "Adverse-event reports for wellness SaMD (cardiometabolic category)" },
    { source_id: "guidance",       evidence_type: "guidance",      title: "FDA — General Wellness: Policy for Low Risk Devices" },
  ],
};

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

export default function ProfilingAssistant({ onDone, onRunStart, onStepsChange, product, setProduct, users, setUsers, outcome, setOutcome, uploadedData, agentStep, onAgentStep, displayName, tenantSlug, studyDesigns = {}, agentSources = [], clientDomains = [], clientTagline = "", clientEndpoints = [], pendingRunToken = 0 }) {
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

  async function getEmbedding(text) {
    const res = await fetch("/api/openai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: "text-embedding-3-small", input: text.slice(0, 8000) }),
    });
    const data = await res.json().catch(() => null);
    const emb = data?.data?.[0]?.embedding;
    if (!emb) throw new Error("Embedding unavailable");
    return emb;
  }

  async function semanticSearch(query, docType, limit = 10) {
    const embedding = await getEmbedding(query);
    const res = await fetch("/api/supabase", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query_embedding: "[" + embedding.join(",") + "]",
        match_count:     limit,
        doc_type_filter: docType,
        tenant_slug:     tenantSlug ?? null,
      }),
    });
    const rows = await res.json();
    if (!Array.isArray(rows)) return [];
    return rows;
  }

  const getDocType = (code) =>
    agentSources.find(s => s.code === code)?.doc_type
    ?? DOC_TYPE_FALLBACK[code]
    ?? code;

  // Prepend client clinical context to agent-generated queries for better
  // semantic search relevance — prevents cross-client document bleed.
  const ctxPrefix = [clientEndpoints[0], clientDomains[0]].filter(Boolean).join(" ");
  const withCtx   = (q) => ctxPrefix ? `${ctxPrefix} ${q}` : q;

  const TOOL_FNS = {
    search_pubmed:          (q, n) => semanticSearch(withCtx(q), getDocType("pubmed"),        n || 10),
    search_clinicaltrials:  (q, n) => semanticSearch(withCtx(q), getDocType("clinicaltrials"),n || 10),
    search_maude:           (q, n) => semanticSearch(withCtx(q), getDocType("maude"),          n || 10),
    search_fda_guidance:    (q, n) => semanticSearch(withCtx(q), getDocType("fda_guidance"),  n || 5),
  };

  // Minimum cosine similarity per source. Rows below threshold are dropped.
  // 0.40 calibrated against intern's Gemini-judged relevance benchmark
  // (3-layer prompt + floor 0.40 produced 2-3x more quality docs than 0.55).
  const SIMILARITY_THRESHOLD = {
    search_pubmed:         0.30,
    search_clinicaltrials: 0.30,
    search_maude:          0.30,
    search_fda_guidance:   0.30,
  };

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

  // Retry a retrieval call once after a short delay. Most failures are
  // transient (network blip, OpenAI embedding rate limit). On second failure,
  // re-throws so the existing catch block surfaces the error in the UI.
  async function retryRetrieval(label, fn) {
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        return await fn();
      } catch (err) {
        console.error(`[profiling] ${label} attempt ${attempt} failed:`, err?.message ?? err);
        if (attempt === 2) throw err;
        await new Promise(r => setTimeout(r, 1500));
      }
    }
  }

  async function callWithRetry(body, addLine, retries=4) {
    for (let i=0; i<retries; i++) {
      const res = await fetch("/api/anthropic", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(body),
      });
      if (res.status === 429 || res.status === 529) {
        const wait = (i+1) * 8000;
        addLine(`   API busy — retrying in ${wait/1000}s…`);
        await new Promise(r => setTimeout(r, wait));
        continue;
      }
      return await res.json();
    }
    throw new Error("API unavailable after retries — please try again in a moment");
  }

  // Streaming variant — used for the synthesis call so tokens appear as Claude writes.
  // Has a built-in 90s AbortController timeout to prevent indefinite hangs on
  // sparse corpora where synthesis takes much longer than tool-call rounds.
  async function callWithRetryStreaming(body, onTextDelta, retries=4) {
    for (let i=0; i<retries; i++) {
      const controller = new AbortController();
      const timeoutId  = setTimeout(() => controller.abort(), 90_000);

      let res;
      try {
        res = await fetch("/api/anthropic", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({ ...body, stream: true }),
          signal: controller.signal,
        });
      } catch(fetchErr) {
        clearTimeout(timeoutId);
        if (fetchErr.name === "AbortError")
          throw new Error("Synthesis timed out after 90s — please retry");
        throw fetchErr;
      }

      if (res.status === 429 || res.status === 529) {
        clearTimeout(timeoutId);
        await new Promise(r => setTimeout(r, (i+1) * 8000));
        continue;
      }

      try {
        const reader = res.body.getReader();
        const dec    = new TextDecoder();
        let buf = "", blocks = [], stopReason = null, accumText = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split("\n"); buf = lines.pop();
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw || raw === "[DONE]") continue;
            try {
              const ev = JSON.parse(raw);
              if (ev.type === "content_block_start") {
                const cb = ev.content_block;
                blocks[ev.index] = cb.type === "tool_use"
                  ? { type:"tool_use", id:cb.id, name:cb.name, _json:"" }
                  : { type:"text", text: cb.text || "" };
              } else if (ev.type === "content_block_delta") {
                const blk = blocks[ev.index];
                if (!blk) continue;
                if (ev.delta.type === "text_delta") {
                  blk.text  += ev.delta.text;
                  accumText += ev.delta.text;
                  onTextDelta?.(accumText);
                } else if (ev.delta.type === "input_json_delta") {
                  blk._json += ev.delta.partial_json;
                }
              } else if (ev.type === "message_delta") {
                stopReason = ev.delta?.stop_reason ?? stopReason;
              }
            } catch { /* ignore malformed SSE chunk */ }
          }
        }
        clearTimeout(timeoutId);
        const content = blocks.filter(Boolean).map(b => {
          if (b.type === "tool_use") {
            let input = {}; try { input = JSON.parse(b._json); } catch { /* malformed tool JSON */ }
            return { type:"tool_use", id:b.id, name:b.name, input };
          }
          return { type:"text", text: b.text || "" };
        });
        return { stop_reason: stopReason, content, error: null };
      } catch(streamErr) {
        clearTimeout(timeoutId);
        if (streamErr.name === "AbortError")
          throw new Error("Synthesis timed out after 90s — please retry");
        throw streamErr;
      }
    }
    throw new Error("API unavailable after retries — please try again in a moment");
  }

  // Demo profiling — a scripted, animated run over canned data. Never hits the
  // network, never fails. Used whenever the Demo-data toggle is on.
  async function runDemoAnimation() {
    setStep("running"); setSteps([]); setAgentError(null); setBannerDismissed(false);
    onRunStart?.({ product, users, projectId: tenantSlug, ranAt: new Date().toISOString() });
    const addLine = (t, replaceLast = false) => setSteps(p => {
      const repl = replaceLast && p.length && String(p[p.length - 1]).startsWith("__SYNTHSTREAM:");
      const next = repl ? [...p.slice(0, -1), t] : [...p, t];
      onStepsChange?.(next);
      return next;
    });
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const SOURCES = [
      { name: "search_pubmed",         q: "prediabetes digital therapeutic HbA1c engagement", n: 42 },
      { name: "search_clinicaltrials", q: "lifestyle intervention cardiometabolic remote",     n: 18 },
      { name: "search_maude",          q: "wellness SaMD / DTx adverse events",                 n: 3  },
      { name: "search_fda_guidance",   q: "general wellness software · SaMD intended use",      n: 7  },
    ];
    addLine("__INIT__");
    await sleep(500);
    for (const s of SOURCES) {
      addLine(`__QUERY:${s.name}:${s.q}__`);
      await sleep(700);
      addLine(`__RESULT:${s.name}:${s.n}__`);
      await sleep(300);
    }
    addLine("__SYNTH__");
    const synth = "Benchmarking Lucis against 47 comparable preventive-health products across 70 retrieved documents — scoring regulatory, evidence and safety dimensions.";
    const words = synth.split(" ");
    let acc = "";
    for (let i = 0; i < words.length; i++) {
      acc += (i ? " " : "") + words[i];
      addLine(`__SYNTHSTREAM:${acc}__`, i > 0);
      await sleep(40);
    }
    await sleep(500);
    addLine(`__SYNTHDATA:${JSON.stringify({ design: "Retrospective cohort", endpoint: "HbA1c change at 12 months" })}__`);
    addLine(`✓ Profile complete — ${DEMO_PROFILE.pubmed_evidence_count} comparable studies · MAUDE ${DEMO_PROFILE.risk_signal.toLowerCase()} risk · ${DEMO_PROFILE.study_designs.length} study designs ready`);
    setStep("done");
    onDone?.(DEMO_PROFILE);
  }

  async function run() {
    if (isMockEnabled()) return runDemoAnimation();
    setStep("running"); setSteps([]); setAgentError(null); setBannerDismissed(false);
    onRunStart?.({ product, users, projectId: tenantSlug, ranAt: new Date().toISOString() });
    // E1 profiling reasons about the literature/corpus only — not the user's
    // uploaded dataset. Dataset-aware reasoning happens later (Variable
    // Availability, Simulation, Results). Keeping the dataset out of the
    // profiling prompt prevents N values, column names, and ground-truth
    // values from leaking into corpus-level claims.
    const productDescription = `${product}\n\nUser characteristics:\n${users}\n\nOutcomes of interest:\n${outcome}`;
    const addLine = (t, replaceLast = false) => setSteps(p => {
      // replaceLast: update the last entry only if it is already a __SYNTHSTREAM token
      const shouldReplace = replaceLast && p.length > 0 &&
        String(p[p.length - 1]).startsWith("__SYNTHSTREAM:");
      const next = shouldReplace ? [...p.slice(0, -1), t] : [...p, t];
      onStepsChange?.(next);
      return next;
    });

    addLine("__INIT__");

    try {
      const messages = [{ role: "user", content: productDescription }];
      let profile = null;
      let iterations = 0;
      const MAX          = 6;   // max outer iterations (tool rounds + synthesis)
      const MAX_TOOL_CALLS = 16; // hard cap on individual tool calls (4 sources × 2 max × 2 buffer)
      const _refDocs = [];
      const _refSeen = new Set();
      const _refSourceCnt = {};

      const calledTools    = new Set(); // tracks which tools have been called (any call)
      const _toolCallCnt   = {};        // per-source call counter — max 2 per source
      const _toolResultCnt = {};        // unique doc count per source (for synthesis summary)
      const _sourceUrlSets = {};        // per-source Set of unique URLs — drives display counts
      let   totalToolCalls = 0;         // cumulative tool calls across all iterations
      let   synthSignaled     = false;   // ensures __SYNTH__ emitted at most once
      let   wasSynthesisRound = false;  // set true when synthesis call fires; used for max_tokens fallback

      while (iterations < MAX) {
        iterations++;

        // ── Synthesis trigger ─────────────────────────────────────────────────
        // Primary: all 4 sources have been called at least once (ideal path)
        // Fallback: tool call cap hit — force synthesis with accumulated results
        // Never fire based on iteration count alone — MAUDE/FDA must be called first
        const REQUIRED_SOURCES = [
          'search_pubmed', 'search_clinicaltrials', 'search_maude', 'search_fda_guidance'
        ];
        const allSourcesCalled = REQUIRED_SOURCES.every(s => calledTools.has(s));
        const isSynthesisRound = !synthSignaled && iterations > 1 && (
          allSourcesCalled ||
          totalToolCalls >= MAX_TOOL_CALLS
        );

        let data;
        if (isSynthesisRound) {
          // Empty-corpus guard: if every source returned zero documents, synthesising
          // would force the model to invent a profile (or hang on the 90s timeout).
          // Fail clearly instead — this is almost always an empty/misconfigured corpus
          // for this tenant, not a genuine "no evidence exists" result.
          if (_refDocs.length === 0) {
            addLine("⚠ No matching documents in the evidence corpus — profiling stopped");
            setAgentError("No matching documents were found in the evidence corpus for this product. This usually means the corpus is empty or not configured for this tenant. Check the corpus is populated, then retry.");
            setStep("input");
            break;
          }
          // Emit synthesising status IMMEDIATELY — before the Anthropic wait
          addLine("__SYNTH__");
          synthSignaled     = true;
          wasSynthesisRound = true;

          // Build compact evidence summary — collapses full tool history into
          // a single user message with source counts + top-2 titles per source.
          // Reduces synthesis input from ~10k tokens to ~500 tokens.
          const SOURCE_TO_TOOL = {
            pubmed:         "search_pubmed",
            clinicaltrials: "search_clinicaltrials",
            maude:          "search_maude",
            fda_guidance:   "search_fda_guidance",
          };
          const TOOL_DISPLAY_S = {
            search_pubmed:         "PubMed",
            search_clinicaltrials: "ClinicalTrials.gov",
            search_maude:          "MAUDE",
            search_fda_guidance:   "FDA Guidance",
          };
          const TOOL_ORDER_S = ["search_pubmed","search_clinicaltrials","search_maude","search_fda_guidance"];

          // Group _refDocs by tool (top 2 per source, highest similarity first)
          const docsByTool = {};
          for (const doc of _refDocs) {
            const tool = SOURCE_TO_TOOL[doc.source_id] || `search_${doc.source_id}`;
            if (!docsByTool[tool]) docsByTool[tool] = [];
            if (docsByTool[tool].length < 2) docsByTool[tool].push(doc);
          }

          const summaryLines = ["EVIDENCE CORPUS SEARCH RESULTS\n"];
          for (const tool of TOOL_ORDER_S) {
            const label = TOOL_DISPLAY_S[tool] || tool;
            const count = _toolResultCnt[tool] ?? 0;
            const docs  = docsByTool[tool] ?? [];
            summaryLines.push(
              `${label}: ${count} result${count !== 1 ? "s" : ""}${docs.length ? ". Top matches:" : "."}`
            );
            docs.forEach((d, i) => {
              const score = d.similarity_score != null ? ` (score: ${d.similarity_score.toFixed(2)})` : "";
              summaryLines.push(`  ${i + 1}. ${(d.title || "Untitled").slice(0, 120)}${score}`);
            });
          }
          summaryLines.push("\n\nReturn only the JSON object.");

          const synthesisMessages = [
            {
              role:    "user",
              content: `${messages[0].content}\n\n${summaryLines.join("\n")}`,
            },
          ];

          // Synthesis call — no tools (forces JSON response), 90s timeout built in.
          // Haiku + 400 max_tokens + trimmed schema → target <5s generation.
          let synthFirstToken = true;
          let synthThrottleTimer = null;
          data = await callWithRetryStreaming({
            model:       "claude-haiku-4-5-20251001",
            max_tokens:  4000,  // raised from 1200: long rationales on rich inputs were truncating mid-JSON, causing parse failures
            temperature: 0,
            system:      AGENT_SYSTEM,
            // no tools — forces text (JSON) output, not more tool calls
            messages:    synthesisMessages,
          }, (accumulatedText) => {
            // Throttle to ≤7 state updates/s — replace previous __SYNTHSTREAM: token
            if (!synthThrottleTimer) {
              synthThrottleTimer = setTimeout(() => {
                synthThrottleTimer = null;
                addLine(`__SYNTHSTREAM:${accumulatedText}__`, !synthFirstToken);
                synthFirstToken = false;
              }, 150);
            }
          });
        } else {
          data = await callWithRetry({
            model:       "claude-sonnet-4-6",
            max_tokens:  2000,  // raised for Bloomlife — richer corpus produces larger tool responses
            temperature: 0,
            system:      AGENT_SYSTEM,
            tools:       AGENT_TOOLS,
            messages,
          }, addLine);
        }
        if (data.error) { addLine(`⚠ Agent error: ${data.error.message}`); break; }

        const toolUseBlocks = [];
        const toolResultContents = [];

        for (const block of data.content) {
          if (block.type === "tool_use") {
            const { name, id, input } = block;
            calledTools.add(name); // track for synthesis detection
            const q = (input.query||"").length > 72 ? input.query.slice(0,72)+"…" : input.query;
            addLine(`__QUERY:${name}:${q}__`);
            toolUseBlocks.push({ name, id, input });
          }
        }

        for (const { name, id, input } of toolUseBlocks) {
          // Per-source call limit — max 2 calls per source to prevent infinite loops
          if ((_toolCallCnt[name] || 0) >= 2) {
            toolResultContents.push({ type:"tool_result", tool_use_id: id, content: "[]" });
            continue;
          }
          _toolCallCnt[name] = (_toolCallCnt[name] || 0) + 1;
          totalToolCalls++;
          try {
            const fn = TOOL_FNS[name];
            console.log(`[profiling] ${name} query="${input.query}"`);
            const rawResult = fn
              ? await retryRetrieval(name, () => fn(input.query, input.max_results))
              : [];
            // Threshold filter — drop rows below the per-source similarity floor.
            // Logs the kept/dropped counts and full score distribution to console
            // so you can calibrate thresholds against real retrievals.
            const threshold = SIMILARITY_THRESHOLD[name] ?? 0.5;
            const scoreDistribution = rawResult.map(r => Number(r.similarity ?? 0).toFixed(3));
            const result = rawResult.filter(r => (r.similarity ?? 0) >= threshold);
            console.log(
              `[profiling] ${name} threshold=${threshold}: kept ${result.length}/${rawResult.length}`,
              scoreDistribution,
            );
            // Validate URL shape — must be parseable http(s) URL with non-empty pathname.
            // Drops malformed values like "null", whitespace, "undefined", etc.
            const isValidUrl = (u) => {
              if (!u || typeof u !== "string") return false;
              try {
                const parsed = new URL(u);
                if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return false;
                if (!parsed.hostname) return false;
                return true;
              } catch { return false; }
            };
            // ── Build URL for a single result row (shared by Set tracking + _refDocs) ──
            // Returns null if no valid direct URL can be constructed. Search-page
            // fallbacks have been removed — we'd rather show fewer working links
            // than a mix of direct links and search pages.
            const buildRowUrl = (row) => {
              const explicit = row.canonical_url || row.source_url || null;
              if (isValidUrl(explicit)) return explicit;
              if (!row.doc_type || !row.filename) return null;
              const f = String(row.filename).trim();
              if (!f) return null;
              let u = null;
              if      (row.doc_type === "pubmed")         u = `https://pubmed.ncbi.nlm.nih.gov/${f}/`;
              else if (row.doc_type === "clinicaltrials") u = `https://clinicaltrials.gov/study/${f}`;
              else if (row.doc_type === "fda_guidance") {
                // Docket IDs like "FDA-2006-D-0464" live on regulations.gov.
                // Numeric IDs are FDA media IDs and use the /media/ download path.
                // Any other format → null (gets dropped by URL validator below).
                if      (/^FDA-\d{4}-[A-Z]-\d+$/i.test(f)) u = `https://www.regulations.gov/docket/${f}`;
                else if (/^\d+$/.test(f))                  u = `https://www.fda.gov/media/${f}/download`;
                else                                       u = null;
              }
              else if (row.doc_type === "maude")          u = `https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfmaude/detail.cfm?mdrfoi__id=${f}`;
              return isValidUrl(u) ? u : null;
            };

            // Track unique URLs per source across all calls — drives the display count.
            // Only valid direct URLs are counted; rows without a direct URL are
            // excluded from the count, which keeps headline numbers honest.
            if (!_sourceUrlSets[name]) _sourceUrlSets[name] = new Set();
            for (const row of result) {
              const u = buildRowUrl(row);
              if (u) _sourceUrlSets[name].add(u);
            }
            const uniqueCount = _sourceUrlSets[name].size;
            addLine(`__RESULT:${name}:${uniqueCount}__`);
            _toolResultCnt[name] = uniqueCount;

            // Capture top 10 docs per source for referenced_docs (40 total max)
            // match_chunks returns: content, doc_type, filename, source_url, similarity
            // content format: "Document type: pubmed | [actual text]"
            if (_refDocs.length < 40) {
              for (const row of result) {
                if ((_refSourceCnt[name] || 0) >= 10 || _refDocs.length >= 40) break;
                const rawContent = typeof row.content === "string" ? row.content : "";
                const stripped   = rawContent.replace(/^Document\s+type:\s*\S+\s*\|\s*/i, "").trim();
                const title = row.title
                  || (stripped.length > 0 ? stripped.slice(0, 120) : null)
                  || (row.doc_type && row.filename ? `${row.doc_type.toUpperCase()} ${row.filename}` : null)
                  || "Untitled";
                const sourceId = row.source_id || row.doc_type || name;
                const url = buildRowUrl(row);
                // Strict mode: drop rows without a valid direct URL. No more
                // search-page fallbacks — only show docs we can link to.
                if (!url) continue;
                const dedupeKey = url + "::" + (title || "");
                if (_refSeen.has(dedupeKey)) continue;
                _refSeen.add(dedupeKey);
                _refDocs.push({ title, url, source_id: sourceId, similarity_score: row.similarity ?? null, evidence_type: row.cesl_tags?.evidence_type ?? null });
                _refSourceCnt[name] = (_refSourceCnt[name] || 0) + 1;
              }
            }
            // ── IMPROVEMENT 3: compact tool results — top 3, 300-char content ──
            // Reduces synthesis context from ~50k tokens to ~5-8k tokens
            // CESL tags prepended so Claude knows evidence_type / domain / lifecycle
            const compact = result.slice(0, 3).map(r => {
              const tags  = r.cesl_tags;
              const label = tags
                ? `[${tags.evidence_type ?? '?'} | ${tags.clinical_domain ?? '?'} | ${tags.lifecycle_stage ?? '?'}]`
                : null;
              const raw       = typeof r.content === "string" ? r.content : "";
              const annotated = label ? `${label}\n${raw}` : raw;
              return {
                filename:   r.filename,
                similarity: r.similarity,
                content:    annotated.slice(0, 300),
                source_id:  r.source_id,
                doc_type:   r.doc_type,
              };
            });
            toolResultContents.push({ type:"tool_result", tool_use_id: id, content: JSON.stringify(compact) });
          } catch(err) {
            const reason = err?.message ?? String(err);
            console.error(`[profiling] ${name} failed after retry:`, reason, err);
            addLine(`__ERROR:${name}__`);
            toolResultContents.push({ type:"tool_result", tool_use_id: id, content: `Error: ${reason}`, is_error: true });
          }
        }

        if (toolUseBlocks.length > 0) {
          messages.push({ role: "assistant", content: data.content });
          messages.push({ role: "user", content: toolResultContents });
        }

        if (data.stop_reason === "max_tokens" && wasSynthesisRound) {
          console.warn('[synthesis] hit max_tokens — attempting partial parse');
        }
        const effectiveStopReason = (data.stop_reason === "max_tokens" && wasSynthesisRound)
          ? "end_turn"
          : data.stop_reason;
        if (effectiveStopReason === "end_turn") {
          const text = data.content.filter(b => b.type==="text").map(b => b.text).join("");
          try {
            const cleanJson = text
              .replace(/^```json\s*/i, '')
              .replace(/^```\s*/i, '')
              .replace(/```\s*$/i, '')
              .trim();
            const match = cleanJson.match(/\{[\s\S]*\}/);
            profile = JSON.parse(match ? match[0] : cleanJson);

            // ── Deterministic counts ─────────────────────────────────────────
            // Counts come from _sourceUrlSets (unique URLs retrieved from
            // Supabase), NOT from the LLM. Headline numbers, references panel,
            // and risk_signal are guaranteed coherent by construction.
            const llmClaimed = {
              pubmed:         profile.pubmed_evidence_count,
              clinicaltrials: profile.open_trials_count,
              maude:          profile.adverse_event_count,
              risk_signal:    profile.risk_signal,
            };
            const pubmedCount = _sourceUrlSets.search_pubmed?.size         ?? 0;
            const ctCount     = _sourceUrlSets.search_clinicaltrials?.size ?? 0;
            const maudeCount  = _sourceUrlSets.search_maude?.size          ?? 0;
            const fdaCount    = _sourceUrlSets.search_fda_guidance?.size   ?? 0;
            profile.pubmed_evidence_count = pubmedCount;
            profile.open_trials_count     = ctCount;
            profile.adverse_event_count   = maudeCount;
            profile.fda_guidance_count    = fdaCount;
            profile.risk_signal = maudeCount === 0 ? "LOW"
                                : maudeCount <= 5 ? "MEDIUM" : "HIGH";
            console.log("[profiling] computed counts:", { pubmed: pubmedCount, clinicaltrials: ctCount, maude: maudeCount, fda: fdaCount });
            console.log("[profiling] llm-claimed counts (overwritten):", llmClaimed);
            console.log("[profiling] risk_signal:", profile.risk_signal, "(from maude=" + maudeCount + ")");

            // Map study design codes → display labels using live Supabase data
            // with hardcoded fallback so app never breaks if fetch is in flight
            if (profile.study_designs) {
              profile.study_designs = profile.study_designs.map(sd => ({
                ...sd,
                name: studyDesigns[sd.code] ?? STUDY_DESIGN_FALLBACK[sd.code] ?? sd.code,
              }));
            }

            // Trim referenced_docs per source so the references panel never
            // shows MORE entries than the headline count for that source.
            const sourceCaps = {
              pubmed: pubmedCount, clinicaltrials: ctCount,
              maude:  maudeCount,  fda_guidance:   fdaCount,
            };
            const perSourceShown = {};
            profile.referenced_docs = _refDocs.filter(d => {
              const cap = sourceCaps[d.source_id] ?? 10;
              const seen = perSourceShown[d.source_id] || 0;
              if (seen >= cap) return false;
              perSourceShown[d.source_id] = seen + 1;
              return true;
            });
            const d = profile;
            // __SYNTH__ was emitted before the streaming call; only add if missed
            if (!synthSignaled) { addLine("__SYNTH__"); synthSignaled = true; }
            addLine(`__SYNTHDATA:${JSON.stringify({ design: d.design_type, endpoint: d.endpoint })}__`);
            addLine(`✓ Profile complete — ${d.pubmed_evidence_count} comparable studies · MAUDE ${(d.risk_signal||"").toLowerCase()} risk · ${d.study_designs?.length||3} study designs ready`);
            window.__e1Profile = profile;
            setStep("done");
            onDone?.(profile);
          } catch(e) {
            const synthesisText = data.content?.find(b => b.type === "text")?.text ?? "";
            console.error("Profile parse failed:", e, "\nRaw text:", synthesisText);
            addLine(`⚠ Profile parse failed: ${e.message}`);
            setStep("input");
            break; // exit agent loop — do not hang waiting for next iteration
          }
          break;
        }
        if (data.stop_reason === "max_tokens") {
          addLine("⚠ Agent output truncated — please retry");
          break;
        }
        if (data.stop_reason !== "tool_use") break;
      }
      if (!profile) setStep("input");
    } catch(err) {
      const msg = err?.message ?? String(err);
      console.error("[profiling] agent run failed:", msg, err);
      setAgentError(msg);
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
