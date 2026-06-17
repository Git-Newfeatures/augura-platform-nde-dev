import { useState, useEffect } from "react";
import { ArrowLeft, ArrowRight, RotateCcw, Undo2, RefreshCw, ChevronUp, ChevronDown, AlertTriangle, Ban, Info, Check, X, Circle, Network, MessageSquare } from "lucide-react";
import { apiJson } from "../api";
import { fetchCohort, isHighEngager } from "../workspace/cohortData";
import { C, FONT, MONO } from "../theme";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoBar } from "../ui/components";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 7: CAUSAL MODEL
// Implements Causal Roadmap steps D1–D3:
//   D1 — Causal question + population (HIGH vs REST engagement)
//   D2 — Estimand (ATT — Average Treatment effect on the Treated)
//   D3 — Minimal sufficient adjustment set (confounders)
// ─────────────────────────────────────────────────────────────────────────────

// ── Role visual config ────────────────────────────────────────────────────────
// Legend chips and DAG nodes use the same palette so they read as one system.
// `solid: true` means dark fill + white text (used for treatment/mediator/outcome).
const ROLE_STYLE = {
  intervention:          { fill: "#1F2937", stroke: "#1F2937", text: "#FFFFFF", solid: true,  label: "Exposure"      },
  mediator:              { fill: "#2A9D8F", stroke: "#2A9D8F", text: "#FFFFFF", solid: true,  label: "Mediator"      },
  outcome:               { fill: "#0C447C", stroke: "#0C447C", text: "#FFFFFF", solid: true,  label: "Outcome"       },
  confounder:            { fill: "#FFF8E6", stroke: "#EF9F27", text: "#633806", solid: false, label: "Confounder"    },
  unmeasured_confounder: { fill: "#FFF8E6", stroke: "#EF9F27", text: "#633806", solid: false, label: "Unmeasured"    },
  effect_modifier:       { fill: "#FDECEA", stroke: "#E24B4A", text: "#7A2020", solid: false, label: "Effect mod."   },
  collider:              { fill: "#FDECEA", stroke: "#E24B4A", text: "#7A2020", solid: false, label: "Collider ⛔"   },
};

// Suggestion pills + system prompt for the embedded DAG assistant.
const DAG_CHAT_SUGGESTIONS = [
  "Why isn't motivation adjustable?",
  "Can I add BMI as a mediator?",
  "What is a collider?",
  "Why are mediators excluded from the adjustment set?",
];
const DAG_CHAT_SYSTEM =
  "You are the Augura causal-model assistant. You help the user reason about the DAG " +
  "for this study: the exposure → outcome question, confounders in the adjustment set, " +
  "mediators (never adjusted for a total-effect estimand), effect modifiers, colliders " +
  "(must not be adjusted), and unmeasured confounders retained for E-value sensitivity. " +
  "Answer concisely (under 120 words) and stay focused on causal-inference reasoning.";

// ── DAG sanitiser ─────────────────────────────────────────────────────────────
// Defensive cleanup of agent output: drop any node whose label matches an
// alternative candidate outcome (e.g. HbA1c when LDL is selected), and ensure
// the direct intervention→outcome edge is present (represents the total causal
// effect being estimated — must always be drawn even if mediated).
function sanitizeDag(dag, selectedOutcome, candidateOutcomes = []) {
  if (!dag?.nodes) return dag;
  const others = (candidateOutcomes || []).filter(c => c !== selectedOutcome).map(s => s.toLowerCase());
  const matchesOtherOutcome = (label = "") => {
    const l = label.toLowerCase();
    return others.some(o => l.includes(o));
  };

  const interventionId = dag.nodes.find(n => n.role === "intervention")?.id;
  const outcomeId      = dag.nodes.find(n => n.role === "outcome")?.id;

  // Drop covariate nodes that match another candidate outcome
  const dropIds = new Set(
    dag.nodes
      .filter(n => n.role !== "intervention" && n.role !== "outcome" && matchesOtherOutcome(n.label))
      .map(n => n.id)
  );

  let nodes = dag.nodes.filter(n => !dropIds.has(n.id));
  let edges = (dag.edges || []).filter(e => !dropIds.has(e.from) && !dropIds.has(e.to));

  // Ensure direct A→Y edge exists
  if (interventionId && outcomeId) {
    const hasDirect = edges.some(e => e.from === interventionId && e.to === outcomeId);
    if (!hasDirect) edges = [...edges, { from: interventionId, to: outcomeId }];
  }

  return {
    ...dag,
    nodes,
    edges,
    adjustment_set: (dag.adjustment_set || []).filter(x => !dropIds.has(x)),
    collider_ids:   (dag.collider_ids   || []).filter(x => !dropIds.has(x)),
  };
}

// ── Layout engine ─────────────────────────────────────────────────────────────
const SVG_W = 860, SVG_H = 340;
const NODE_W = 130, NODE_H = 38;

function computeLayout(nodes) {
  const byRole = {
    confounder:            nodes.filter(n => n.role === "confounder"),
    intervention:          nodes.filter(n => n.role === "intervention"),
    outcome:               nodes.filter(n => n.role === "outcome"),
    mediator:              nodes.filter(n => n.role === "mediator"),
    effect_modifier:       nodes.filter(n => n.role === "effect_modifier"),
    unmeasured_confounder: nodes.filter(n => n.role === "unmeasured_confounder"),
  };

  const placed = {};

  // Row 1 — confounders
  const conf = byRole.confounder;
  if (conf.length) {
    const span  = Math.max(SVG_W - 40, conf.length * (NODE_W + 12));
    const step  = span / conf.length;
    const startX = (SVG_W - span) / 2 + step / 2;
    conf.forEach((n, i) => { placed[n.id] = { cx: startX + i * step, cy: 32 }; });
  }

  // Row 2 — intervention left, outcome right
  const treat = byRole.intervention[0];
  const out   = byRole.outcome[0];
  if (treat) placed[treat.id] = { cx: 80,        cy: 130 };
  if (out)   placed[out.id]   = { cx: SVG_W - 80, cy: 130 };

  // Row 3 — mediators centred
  const meds = byRole.mediator;
  if (meds.length) {
    const midX  = SVG_W / 2;
    const span  = (meds.length - 1) * (NODE_W + 14);
    const startX = midX - span / 2;
    meds.forEach((n, i) => { placed[n.id] = { cx: startX + i * (NODE_W + 14), cy: 210 }; });
  }

  // Row 4 — unmeasured + effect_modifier
  const bottom = [...byRole.unmeasured_confounder, ...byRole.effect_modifier];
  if (bottom.length) {
    const step  = SVG_W / (bottom.length + 1);
    bottom.forEach((n, i) => { placed[n.id] = { cx: step * (i + 1), cy: 278 }; });
  }

  return nodes.map(n => ({ ...n, ...(placed[n.id] || { cx: SVG_W / 2, cy: SVG_H / 2 }) }));
}

// ── DagRenderer — pure SVG from nodes + edges ─────────────────────────────────
export function DagRenderer({ nodes, edges, highlightIds = [] }) {
  if (!nodes?.length) return null;
  const laid = computeLayout(nodes);
  const byId = Object.fromEntries(laid.map(n => [n.id, n]));

  const uid = "dag-" + Math.abs(nodes.map(n=>n.id).join("").split("").reduce((a,c)=>a+c.charCodeAt(0),0));

  return (
    <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} style={{ width:"100%", height:"auto" }}
      xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id={`${uid}-main`} markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
          <path d="M0,0 L0,6 L8,3 Z" fill={C.green} />
        </marker>
        <marker id={`${uid}-conf`} markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L7,3 Z" fill={C.faint} />
        </marker>
        <marker id={`${uid}-med`} markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L7,3 Z" fill="#EF9F27" />
        </marker>
        <marker id={`${uid}-unc`} markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L7,3 Z" fill={C.faint} />
        </marker>
      </defs>
      <style>{`@keyframes augDagIn{from{opacity:0}to{opacity:1}}`}</style>

      {edges.map((e, i) => {
        const src = byId[e.from], tgt = byId[e.to];
        if (!src || !tgt) return null;

        const isMainEffect = src.role === "intervention" && tgt.role === "outcome";
        const isMed       = src.role === "mediator"     || tgt.role === "mediator";
        const isUnc       = src.role === "unmeasured_confounder";

        const stroke    = isMainEffect ? C.green : isMed ? "#EF9F27" : C.faint;
        const sw        = isMainEffect ? 2.2 : 1.2;
        const dash      = isUnc ? "5,3" : isMed && src.role !== "intervention" ? "3,2" : undefined;
        const markerId  = isMainEffect ? `${uid}-main` : isMed ? `${uid}-med` : isUnc ? `${uid}-unc` : `${uid}-conf`;

        const dx = tgt.cx - src.cx, dy = tgt.cy - src.cy;
        const dist = Math.sqrt(dx*dx + dy*dy) || 1;
        const rx = (NODE_W/2 + 2) * (dx / dist), ry = (NODE_H/2 + 2) * (dy / dist);
        const x1 = src.cx + rx, y1 = src.cy + ry;
        const x2 = tgt.cx - (NODE_W/2 + 2) * (dx / dist), y2 = tgt.cy - (NODE_H/2 + 2) * (dy / dist);

        return (
          <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={stroke} strokeWidth={sw} strokeDasharray={dash}
            markerEnd={`url(#${markerId})`}
            style={{ animation: "augDagIn .5s ease-out both", animationDelay: `${0.35 + i * 0.05}s` }} />
        );
      })}

      {(() => {
        const treat = laid.find(n => n.role === "intervention");
        const out   = laid.find(n => n.role === "outcome");
        if (!treat || !out) return null;
        const hasDirect = edges.some(e => e.from === treat.id && e.to === out.id);
        if (!hasDirect) return null;
        const mx = (treat.cx + out.cx) / 2, my = (treat.cy + out.cy) / 2 - 10;
        return (
          <text x={mx} y={my} textAnchor="middle" fontSize="9" fontFamily={MONO}
            fill={C.green} fontWeight="700">Causal Effect</text>
        );
      })()}

      {laid.map((n, ni) => {
        const s     = ROLE_STYLE[n.role] || ROLE_STYLE.confounder;
        const isHL  = highlightIds.includes(n.id);
        const dashed= n.role === "unmeasured_confounder";
        const x     = n.cx - NODE_W / 2;
        const y     = n.cy - NODE_H / 2;
        // Split label at word boundary if too long for one line (~18 chars at fontSize 9)
        const words = n.label.split(" ");
        let line1 = "", line2 = "";
        for (const w of words) {
          if ((line1 + " " + w).trim().length <= 20) line1 = (line1 + " " + w).trim();
          else line2 = (line2 + " " + w).trim();
        }
        if (line2.length > 22) line2 = line2.slice(0, 20) + "…";
        const twoLine = line2.length > 0;
        const sub   = s.label + (n.measured === false ? " · unmeas." : "");
        return (
          <g key={n.id} style={{ animation: "augDagIn .45s ease-out both", animationDelay: `${0.05 + ni * 0.06}s` }}>
            <rect x={x} y={y} width={NODE_W} height={NODE_H} rx="6"
              fill={s.fill} stroke={isHL ? "#EF9F27" : s.stroke}
              strokeWidth={isHL ? 2 : dashed ? 0.8 : 1}
              strokeDasharray={dashed ? "4,2" : undefined}
              opacity={n.measured === false ? 0.7 : 1} />
            <text textAnchor="middle" fontSize="9" fontFamily={FONT} fill={s.text} fontWeight="600">
              {twoLine ? (
                <>
                  <tspan x={n.cx} y={n.cy - 10}>{line1}</tspan>
                  <tspan x={n.cx} dy="11">{line2}</tspan>
                </>
              ) : (
                <tspan x={n.cx} y={n.cy - 4}>{line1}</tspan>
              )}
            </text>
            <text x={n.cx} y={n.cy + (twoLine ? 13 : 8)} textAnchor="middle" fontSize="7.5" fontFamily={MONO}
              fill={s.text} opacity="0.75">{sub}</text>
          </g>
        );
      })}

      {[
        { color: C.green,    dash: false, label: "Causal effect" },
        { color: C.faint,    dash: false, label: "Measured path (plain)" },
        { color: C.faint,    dash: true,  label: "Unmeasured path (dotted)" },
        { color: "#EF9F27",  dash: false, label: "Mediation path" },
      ].map((l, i) => (
        <g key={i} transform={`translate(${8 + i * 150}, ${SVG_H - 12})`}>
          <line x1="0" y1="0" x2="22" y2="0"
            stroke={l.color} strokeWidth="1.5" strokeDasharray={l.dash ? "4,2" : undefined} />
          <text x="26" y="4" fontSize="8" fontFamily={MONO} fill={C.faint}>{l.label}</text>
        </g>
      ))}
    </svg>
  );
}

export default function CausalModel({ studyType, product, outcome, dagCache, setDagCache, selectedOutcome = "hba1c", selectedCohort = "", cqExposure, cqPopulation, partnerLabel = 'Partner', candidateOutcomes = [], datasetVariables = null, chatProps = {} }) {

  const [cohort, setCohort] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchCohort(selectedCohort).then(({ members }) => {
      if (!alive || !members.length) return;
      const total  = members.length;
      const highN  = members.filter(isHighEngager).length;
      const restN  = total - highN;
      setCohort({ total, highN, highPct: Math.round(highN / total * 100), restN });
    });
    return () => { alive = false; };
  }, [selectedCohort]);

  const [dagData,     setDagDataLocal] = useState(dagCache);
  const [dagOriginal, setDagOriginal]  = useState(dagCache);
  const [dagLoading,  setDagLoading]   = useState(false);
  const [dagError,    setDagError]     = useState(null);
  // dagSource: "agent" = fresh API call this session, "cache" = restored from
  // sessionStorage (prior agent run), null = no DAG yet / agent errored.
  const [dagSource,   setDagSource]    = useState(dagCache ? "cache" : null);
  // True when the DAG originated from the agent (live or cached) — used to gate
  // editing affordances and rationale-derived UI sections.
  const dagFromAgent = dagSource === "agent" || dagSource === "cache";
  const [showEdit,    setShowEdit]     = useState(false);

  // Collapsible embedded DAG assistant (closed by default to stay out of the way).
  const [chatOpen,      setChatOpen]      = useState(false);
  // Local, DAG-scoped chat history so this panel's conversation stays separate
  // from the global Augura assistant. Falls back to chatProps if a host wires it.
  const [dagChat,       setDagChat]        = useState([]);

  // Gap detection state — populated before DAG call, displayed as data gap warnings
  const [gapVariables,  setGapVariables]  = useState([]);
  const [gapLoadStep,   setGapLoadStep]   = useState(null); // null | "gaps" | "dag"

  function setDagData(data) { setDagDataLocal(data); setDagCache(data); }
  function revertToOriginal() {
    if (!dagOriginal) return;
    setDagData(JSON.parse(JSON.stringify(dagOriginal)));
  }
  const isEdited = dagOriginal && dagData &&
    JSON.stringify(dagData) !== JSON.stringify(dagOriginal);

  const dag = dagData;
  const hasDag = !!dag?.nodes?.length;

  const confounders = hasDag ? dag.nodes.filter(n => n.role === "confounder") : [];
  const mediators   = hasDag ? dag.nodes.filter(n => n.role === "mediator") : [];
  const unmeasured  = hasDag ? dag.nodes.filter(n => n.role === "unmeasured_confounder") : [];
  const dataGaps    = hasDag ? dag.nodes.filter(n => !n.measured && (n.role === "confounder" || n.role === "mediator")) : [];
  const colliders   = hasDag ? dag.nodes.filter(n => n.role === "collider") : [];
  const safeAdjSet  = hasDag
    ? (dag.adjustment_set || []).filter(id => !colliders.some(c => c.id === id))
    : [];

  const D1_INTERVENTION = cqExposure || "High app engagement (top quartile of engagement score)";
  const D1_COMPARATOR   = "medium / low engagers (REST group)";
  const D1_OUTCOME_MAP  = {
    hba1c: "HbA1c % change at 12 months",
    ldl:   "LDL-C mg/dL change at 12 months",
    crp:   "hs-CRP mg/L change at 12 months",
  };
  const D1_OUTCOME    = D1_OUTCOME_MAP[selectedOutcome] || "HbA1c % change at 12 months";
  const D1_POPULATION = cqPopulation?.length
    ? cqPopulation.join(" · ") + (cohort ? ` · N=${cohort.total}` : "")
    : cohort
      ? `the study population · N=${cohort.total}`
      : "the study population";

  async function runDag() {
    setDagLoading(true);
    setDagError(null);
    setDagSource(null);
    setGapVariables([]);

    const intervention = cqExposure || "HIGH engagement (top quartile of engagement score) vs. REST (medium + low engagers)";
    const OUTCOME_LABEL_MAP = {
      hba1c: "HbA1c % change at 12 months (primary endpoint for prediabetes — gold standard cardiometabolic marker)",
      ldl:   "LDL-C mg/dL change at 12 months (lipid endpoint — statin confounding is a key validity threat)",
      crp:   "hs-CRP mg/L change at 12 months (inflammation marker — high within-person variability, regression to mean risk)",
    };
    const outcomeLabel = OUTCOME_LABEL_MAP[selectedOutcome] || outcome || "HbA1c change at 12 months";
    const population   = cqPopulation?.length
      ? `${cqPopulation.join(", ")}, longitudinal digital health cohort`
      : "the study population, longitudinal digital health cohort";
    const productDocs  = product ? product.slice(0, 500) : "";

    // Flatten confirmed measured variables to pass to gap detection
    const measuredVars = datasetVariables
      ? [
          ...(datasetVariables.measuredConfounders  || []).map(c => ({ column: c, role: "measured_confounder" })),
          ...(datasetVariables.mediators             || []).map(c => ({ column: c, role: "mediator" })),
          ...(datasetVariables.effectModifiers       || []).map(c => ({ column: c, role: "effect_modifier" })),
          ...(datasetVariables.exposures             || []).map(c => ({ column: c, role: "exposure" })),
          ...(datasetVariables.exposureComponents    || []).map(c => ({ column: c, role: "exposure_component" })),
          ...(datasetVariables.outcomes              || []).map(o => ({ column: o.column, role: "outcome" })),
        ]
      : [];

    // Step 1 — gap detection (fast, Haiku, non-fatal)
    let detectedGaps = [];
    try {
      setGapLoadStep("gaps");
      const gapData = await apiJson("/agents/gaps", {
        method: "POST",
        body: JSON.stringify({
          intervention,
          outcome: outcomeLabel,
          population,
          selected_outcome: selectedOutcome,
          measured_variables: measuredVars,
        }),
      });
      detectedGaps = gapData.missing_variables || [];
      setGapVariables(detectedGaps);
    } catch {
      // gap detection failure is non-fatal — DAG still runs
    }

    // Step 2 — DAG construction (with gap context injected)
    try {
      setGapLoadStep("dag");
      // apiJson lève sur non-2xx (ex. backend sans clé LLM → 503) ; le catch ci-dessous
      // surface un message propre au lieu d'une erreur JSON brute.
      let data;
      try {
        data = await apiJson("/agents/dag", {
          method: "POST",
          body: JSON.stringify({
            intervention, outcome: outcomeLabel, population,
            product_docs: productDocs, study_type: studyType,
            selected_outcome: selectedOutcome,
            candidate_outcomes: candidateOutcomes,
            dataset_variables: datasetVariables,
            gap_variables: detectedGaps,
          }),
        });
      } catch {
        throw new Error("the DAG service isn't reachable — check the connection and try again");
      }
      if (data.error) throw new Error(data.error);
      if (!data.nodes?.length) throw new Error("the DAG service returned no graph — try again");
      const sanitized = sanitizeDag(data, selectedOutcome, candidateOutcomes);
      setDagData(sanitized);
      setDagOriginal(JSON.parse(JSON.stringify(sanitized)));
      setDagSource("agent");
    } catch (err) {
      setDagError(err.message);
      setDagSource(null);
    } finally {
      setDagLoading(false);
      setGapLoadStep(null);
    }
  }

  useEffect(() => { if (!dagCache) runDag(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function removeNode(id) {
    if (!dagData) return;
    setDagData(prev => ({
      ...prev,
      nodes: prev.nodes.filter(n => n.id !== id),
      edges: prev.edges.filter(e => e.from !== id && e.to !== id),
      adjustment_set: prev.adjustment_set.filter(x => x !== id),
    }));
  }

  function reclassifyNode(id, newRole) {
    if (!dagData) return;
    setDagData(prev => ({
      ...prev,
      nodes: prev.nodes.map(n => n.id === id ? { ...n, role: newRole } : n),
      adjustment_set: newRole === "confounder"
        ? [...new Set([...prev.adjustment_set, id])]
        : prev.adjustment_set.filter(x => x !== id),
    }));
  }

  return (
    <div className="flex flex-col gap-5">
      <InfoBar sources={["Causal Roadmap · Dang et al. 2023"]}>
        <strong>Causal Model review.</strong> The DAG below was constructed by the Augura agent from
        product documentation and clinical domain knowledge. Review and edit before proceeding to simulation.
      </InfoBar>

      {/* D1 — Causal question card */}
      <Card className="gap-0 rounded-xl border border-primary/40 p-5">
        <div className="mb-3 text-[13px] font-semibold text-foreground">
          Causal question
        </div>
        <div className="mb-4 rounded-lg border border-primary/40 bg-secondary p-[10px_14px] text-[13.5px] font-semibold leading-[1.7] text-foreground">
          Does{" "}
          <span className="text-primary">{D1_INTERVENTION}</span>
          {" "}(vs. {D1_COMPARATOR}) cause a reduction in{" "}
          <span className="text-[#3172B0]">{D1_OUTCOME}</span>
          {" "}in{" "}
          <span className="text-muted-foreground">{D1_POPULATION}</span>
          ?
        </div>
        <div className="mb-4 grid grid-cols-3 gap-3">
          {[
            { code:"A", label:"Exposure",   value:D1_INTERVENTION,    color:"text-primary" },
            { code:"Y", label:"Outcome",    value:D1_OUTCOME,         color:"text-[#3172B0]" },
            { code:"P", label:"Population", value:D1_POPULATION,      color:"text-muted-foreground" },
          ].map(({ code, label, value, color }) => (
            <div key={code} className="rounded-lg border border-border bg-muted/40 p-3">
              <div className="mb-1 text-[11px] font-semibold text-muted-foreground">
                <span className="font-mono">{code}</span> · {label}
              </div>
              <div className={`text-[12px] font-semibold leading-snug ${color}`}>{value}</div>
            </div>
          ))}
        </div>
        {/* Inline dataset convergence summary */}
        {(datasetVariables?.outcomes?.length > 0 || datasetVariables?.primaryExposure || datasetVariables?.exposureComponents?.length > 0 || gapVariables.length > 0) && (
          <div className="mt-2 mb-4 rounded-lg border border-border bg-muted/40 p-3">
            <div className="mb-2 text-[12px] font-semibold text-foreground">
              Dataset coverage
            </div>
            <div className="flex flex-col gap-1.5">
              {datasetVariables?.primaryExposure && (
                <div className="flex items-center gap-1.5 text-[12px]">
                  <Check size={14} className="flex-shrink-0 text-primary" />
                  <span className="font-mono font-semibold text-foreground">{datasetVariables.primaryExposure}</span>
                  <span className="text-muted-foreground">— exposure confirmed in dataset</span>
                </div>
              )}
              {datasetVariables?.exposureComponents?.map(c => (
                <div key={c} className="flex items-center gap-1.5 text-[12px]">
                  <Check size={14} className="flex-shrink-0 text-primary" />
                  <span className="font-mono font-semibold text-foreground">{c}</span>
                  <span className="text-muted-foreground">— exposure component in dataset</span>
                </div>
              ))}
              {datasetVariables?.outcomes?.map(o => (
                <div key={o.column} className="flex items-center gap-1.5 text-[12px]">
                  <Check size={14} className="flex-shrink-0 text-primary" />
                  <span className="font-mono font-semibold text-foreground">{o.column}</span>
                  <span className="text-muted-foreground">— outcome confirmed in dataset</span>
                </div>
              ))}
              {gapVariables.map((v, i) => (
                <div key={i} className="flex items-center gap-1.5 text-[12px]">
                  {v.severity === "critical"
                    ? <X size={14} className="flex-shrink-0 text-[#C0392B]" />
                    : <AlertTriangle size={14} className="flex-shrink-0 text-[#B98900]" />}
                  <span className={`font-mono font-semibold ${v.severity === "critical" ? "text-[#C0392B]" : "text-[#633806]"}`}>{v.name}</span>
                  <span className={v.severity === "critical" ? "text-[#C0392B]" : "text-[#854F0B]"}>
                    — not in dataset → flagged for gap detection
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          <Info size={13} className="flex-shrink-0" /> This is a <strong>total effect</strong> question (A → Y, not mediated).
          To decompose direct vs. indirect effects, select the Causal Mediation study design.
        </div>
      </Card>

      <div className="flex flex-col gap-4">

        {/* DAG full width */}
        <Card className="gap-0 rounded-xl border border-border p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-foreground">
              Causal graph (DAG)
            </div>
            <div className="flex items-center gap-1.5">
              {dagLoading ? (
                <span className="flex items-center gap-1 rounded-md border border-[#85B7EB] bg-[#E6F1FB] px-2 py-0.5 text-[11px] font-medium text-[#3172B0]">
                  <Circle size={9} className="flex-shrink-0" /> {gapLoadStep === "gaps" ? "Detecting gaps…" : "Building DAG…"}
                </span>
              ) : dagSource === "agent" ? (
                <span className="rounded-md border border-primary/40 bg-secondary px-2 py-0.5 text-[11px] font-semibold text-[#27500A]">Augura agent</span>
              ) : dagSource === "cache" ? (
                <span className="rounded-md border border-[#EF9F27] bg-[#FAEEDA] px-2 py-0.5 text-[11px] font-semibold text-[#633806]">Served from cache</span>
              ) : null}
              {!dagLoading && (
                <Button variant="outline" size="sm"
                  onClick={() => { setDagData(null); setDagDataLocal(null); runDag(); }}
                  title="Re-generate DAG from agent"
                  className="h-auto gap-1 px-2 py-0.5 text-[11px] text-muted-foreground">
                  <RotateCcw size={12} /> Re-generate
                </Button>
              )}
            </div>
          </div>

          {dagLoading && (
            <div className="py-8 text-center">
              <div className="mb-2.5 flex items-center justify-center gap-4">
                {[
                  { key:"gaps", label:"Identifying data gaps", done: gapLoadStep === "dag" },
                  { key:"dag",  label:"Building causal DAG",   done: false },
                ].map(({ key, label, done }) => {
                  const active = gapLoadStep === key;
                  return (
                    <div key={key}
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] ${
                        done ? "border-primary/40 bg-secondary text-[#27500A]"
                        : active ? "animate-pulse border-[#85B7EB] bg-[#E6F1FB] text-[#3172B0]"
                        : "border-border bg-muted/40 text-muted-foreground"
                      }`}>
                      {done ? <Check size={13} className="flex-shrink-0" /> : <Circle size={13} className="flex-shrink-0" />}{label}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Role legend — chips above the DAG, colors mirror ROLE_STYLE */}
          {!dagLoading && hasDag && (
            <div className="mb-4 flex flex-wrap gap-2 rounded-lg border border-border bg-card p-3">
              {[
                { label: "Exposure (Treatment)",     role: "intervention" },
                { label: "Mediator",                 role: "mediator" },
                { label: "Outcome",                  role: "outcome" },
                { label: "Confounder (measured)",    role: "confounder" },
                { label: "Confounder (unmeasured)",  role: "unmeasured_confounder", dashed: true },
                { label: "Effect modifier",          role: "effect_modifier" },
                { label: "Collider (do not adjust)", role: "collider" },
              ].map(({ label, role, dashed }) => {
                const s = ROLE_STYLE[role];
                if (!s) return null;
                return (
                  <div key={label}
                    className="rounded-md px-2.5 py-1 text-[11px] font-semibold"
                    style={{
                      background: s.fill,
                      color: s.text,
                      border: `${dashed ? "1px dashed" : "1px solid"} ${s.stroke}`,
                      fontFamily: FONT,
                    }}>{label}</div>
                );
              })}
            </div>
          )}
          {!dagLoading && hasDag && (
            <DagRenderer nodes={dag.nodes} edges={dag.edges} />
          )}

          {/* Data gap panel — shown after DAG when gap agent found missing variables */}
          {!dagLoading && gapVariables.length > 0 && (
            <div className="mt-4 rounded-lg border border-[#EF9F27] bg-[#FAEEDA] p-[10px_14px]">
              <div className="mb-2 flex items-center gap-1.5 text-[12.5px] font-semibold text-[#633806]">
                <AlertTriangle size={14} className="flex-shrink-0 text-[#B98900]" />
                Data gaps · {gapVariables.length} variable{gapVariables.length > 1 ? "s" : ""} absent from dataset
              </div>
              <div className="flex flex-col gap-1.5">
                {gapVariables.map((v, i) => (
                  <div key={i} className="flex items-start gap-2 rounded-md border border-[#EF9F27] bg-[#FFF8EC] p-[6px_10px]">
                    <span className={`flex-shrink-0 rounded border px-1.5 py-px text-[11px] font-semibold ${
                      v.severity === "critical" ? "border-[#E24B4A] bg-[#FDECEA] text-[#7A2020]" : "border-[#EF9F27] bg-[#FFF3CD] text-[#633806]"
                    }`}>
                      {v.severity}
                    </span>
                    <div>
                      <div className="text-[12.5px] font-semibold text-[#3D2100]">{v.name}</div>
                      <div className="mt-0.5 text-[12px] leading-snug text-[#633806]">{v.rationale}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-[12px] text-[#633806]">
                These variables appear as U-nodes in the DAG above. Use E-value analysis in the Sensitivity tab to quantify their impact.
              </div>
            </div>
          )}

          {!dagLoading && !hasDag && (
            <div className="flex flex-col items-center rounded-lg border border-border bg-muted/30 p-10 text-center">
              <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
                {dagError
                  ? <AlertTriangle size={22} className="text-[#B98900]" />
                  : <Network size={22} className="text-primary" />}
              </span>
              <div className="mb-1.5 text-[15px] font-semibold text-foreground">
                {dagError ? "DAG could not be generated" : "No DAG yet for this configuration"}
              </div>
              <div className="mx-auto mb-5 max-w-[480px] text-[13px] leading-relaxed text-muted-foreground">
                {dagError
                  ? `The Augura agent returned an error: ${dagError}. This usually means a temporary connectivity issue. Try regenerating in a moment.`
                  : "The Augura agent has not yet been run for the current outcome and causal question. Click below to build the DAG from the published clinical literature."}
              </div>
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Button variant="outline"
                  onClick={() => { setDagData(null); setDagDataLocal(null); runDag(); }}
                  className="gap-1.5 border-primary/40 bg-secondary font-semibold text-primary">
                  <RotateCcw size={15} /> {dagError ? "Try again" : "Generate DAG"}
                </Button>
              </div>
            </div>
          )}

          {hasDag && (
            <div className="mt-4 border-t border-border pt-3 text-center text-[12px] text-muted-foreground">
              <span className="font-mono">{dag.nodes.length}</span> nodes · <span className="font-mono">{dag.edges.length}</span> edges · {dagSource === "agent"
                ? `Augura agent · ${new Date().toLocaleDateString()}`
                : `served from cache (prior agent run, no live call) · ${new Date().toLocaleDateString()}`}
            </div>
          )}
        </Card>

        {/* Adjustment set */}
        <div className="grid grid-cols-1 items-start gap-4">

          {/* Adjustment set */}
          <Card className="flex-1 gap-0 rounded-xl border border-border p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[13px] font-semibold text-foreground">
                Adjustment set
              </div>
              <span className="flex items-center gap-1 rounded-md border border-primary/40 bg-secondary px-2 py-0.5 text-[11px] font-semibold text-[#27500A]"><Check size={12} className="flex-shrink-0" /> {safeAdjSet.length} to adjust</span>
            </div>

            {confounders.map(c => (
              <div key={c.id} className="mb-1.5 rounded-md bg-muted/40 p-[8px_10px]">
                <div className="mb-0.5 flex items-center justify-between">
                  <span className="font-mono text-[12.5px] font-semibold text-foreground">{c.label}</span>
                  {dagFromAgent && (
                    <button onClick={() => removeNode(c.id)}
                      title="Remove from DAG"
                      className="cursor-pointer border-none bg-transparent px-1 leading-none text-muted-foreground">
                      <X size={13} />
                    </button>
                  )}
                </div>
                {c.rationale && (
                  <div className="text-[12px] leading-snug text-foreground/80">{c.rationale}</div>
                )}
              </div>
            ))}

            {mediators.length > 0 && (
              <>
                <div className="mx-0 mt-4 mb-2 text-[12px] font-semibold text-foreground">
                  Mediators (not adjusted)
                </div>
                {mediators.map(m => (
                  <div key={m.id} className="mb-1.5 rounded-md border border-[#EF9F27] bg-[#FFF8E6] p-[6px_10px]">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[12px] font-semibold text-[#633806]">{m.label}</span>
                      {dagFromAgent && (
                        <button onClick={() => removeNode(m.id)}
                          className="cursor-pointer border-none bg-transparent px-1 text-muted-foreground">
                          <X size={13} />
                        </button>
                      )}
                    </div>
                    {m.rationale && (
                      <div className="text-[12px] leading-snug text-[#7A4A10]">{m.rationale}</div>
                    )}
                  </div>
                ))}
              </>
            )}

            {unmeasured.length > 0 && (
              <>
                <div className="mx-0 mt-4 mb-2 text-[12px] font-semibold text-foreground">
                  Unmeasured (retained for E-value)
                </div>
                {unmeasured.map(u => (
                  <div key={u.id} className="mb-1.5 rounded-md border border-dashed border-border bg-muted/40 p-[6px_10px] opacity-80">
                    <span className="font-mono text-[12px] font-medium text-muted-foreground">{u.label}</span>
                    {u.rationale && (
                      <div className="text-[12px] leading-snug text-muted-foreground/80">{u.rationale}</div>
                    )}
                  </div>
                ))}
              </>
            )}

            {colliders.length > 0 && (
              <>
                <div className="mx-0 mt-4 mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-[#C0392B]">
                  <Ban size={13} /> Colliders — do NOT adjust
                </div>
                {colliders.map(col => (
                  <div key={col.id} className="mb-1.5 rounded-md border border-[#F5C6CB] bg-[#FDECEA] p-[6px_10px]">
                    <div className="mb-0.5 flex items-center justify-between">
                      <span className="font-mono text-[12px] font-bold text-[#C0392B]">{col.label}</span>
                      <span className="rounded-md bg-[#C0392B] px-1.5 py-px text-[11px] font-semibold text-white">
                        collider
                      </span>
                    </div>
                    {col.rationale && (
                      <div className="text-[12px] leading-snug text-[#922B21]">{col.rationale}</div>
                    )}
                    <div className="mt-1 flex items-center gap-1 text-[12px] text-[#C0392B]">
                      <AlertTriangle size={12} className="flex-shrink-0 text-[#C0392B]" /> Adjusting for this variable opens non-causal paths (collider bias). Never include in regression.
                    </div>
                  </div>
                ))}
              </>
            )}

            {dagFromAgent && (
              <div className="mt-4 flex gap-2">
                <Button variant="outline" size="sm"
                  onClick={() => setShowEdit(e => !e)}
                  className="h-auto flex-1 gap-1 border-border bg-muted/40 px-2 py-1.5 text-[12px] font-normal text-foreground/80">
                  {showEdit ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  {showEdit ? "Hide variable editor" : "Edit variables / reclassify"}
                </Button>
                <Button variant="outline" size="sm"
                  onClick={revertToOriginal}
                  disabled={!isEdited}
                  title={isEdited ? "Restore the original agent-generated DAG" : "DAG has not been edited"}
                  className="h-auto gap-1 border-border bg-muted/40 px-2.5 py-1.5 text-[12px] font-normal text-foreground/80">
                  <Undo2 size={13} /> Revert to original
                </Button>
                <Button variant="outline" size="sm"
                  onClick={() => {
                    if (isEdited && !window.confirm("Regenerating will discard your manual edits. Continue?")) return;
                    runDag();
                  }}
                  disabled={dagLoading}
                  title="Re-run the agent. Discards manual edits."
                  className="h-auto gap-1 border-primary/40 bg-secondary px-2.5 py-1.5 text-[12px] font-semibold text-primary">
                  <RefreshCw size={13} className={dagLoading ? "animate-spin" : undefined} />
                  {dagLoading ? "Regenerating…" : "Regenerate from agent"}
                </Button>
              </div>
            )}

            {showEdit && dagFromAgent && (() => {
              const editable = dag.nodes.filter(n => n.role !== "intervention" && n.role !== "outcome");
              const groups = [
                { key: "confounder",            label: "Adjustment set",       color: "#4B3070" },
                { key: "mediator",              label: "Mediators (not adjusted)", color: "#633806" },
                { key: "effect_modifier",       label: "Effect modifiers",     color: "#0C447C" },
                { key: "unmeasured_confounder", label: "Unmeasured",           color: "#444441" },
                { key: "collider",              label: "Colliders (never adjust)", color: "#C0392B" },
              ];
              return (
                <div className="mt-3 rounded-lg border border-border bg-muted/40 p-3">
                  <div className="mb-3 text-[12px] text-foreground/80">
                    Reclassify variables or remove them from the DAG. Changes update the SVG live.
                    <span className="text-muted-foreground"> Note: edits do not re-run the agent — use Regenerate above for a fresh agent draft.</span>
                  </div>
                  {groups.map(g => {
                    const items = editable.filter(n => n.role === g.key);
                    if (!items.length) return null;
                    return (
                      <div key={g.key} className="mb-3">
                        <div className="mb-1.5 text-[12px] font-semibold" style={{ color:g.color }}>
                          {g.label} ({items.length})
                        </div>
                        {items.map(n => (
                          <div key={n.id} className="mb-1 flex items-center gap-1.5 rounded-md border border-border bg-card p-[5px_8px] leading-tight">
                            <span className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[12px] text-foreground">{n.label}</span>
                            <select value={n.role}
                              onChange={e => reclassifyNode(n.id, e.target.value)}
                              className="cursor-pointer rounded border border-border bg-card px-1.5 py-0.5 text-[11px] text-foreground/80">
                              <option value="confounder">Confounder</option>
                              <option value="mediator">Mediator</option>
                              <option value="effect_modifier">Effect modifier</option>
                              <option value="unmeasured_confounder">Unmeasured</option>
                              <option value="collider">Collider (do not adjust)</option>
                            </select>
                            <button onClick={() => removeNode(n.id)} title="Remove from DAG"
                              className="cursor-pointer border-none bg-transparent px-0.5 leading-none text-[#C0392B]">
                              <X size={13} />
                            </button>
                          </div>
                        ))}
                      </div>
                    );
                  })}
                  {dag.rationale && (
                    <div className="mt-2 border-t border-border pt-2 text-[12px] leading-relaxed text-muted-foreground">
                      {dag.rationale}
                    </div>
                  )}
                </div>
              );
            })()}
          </Card>

        </div>
      </div>

      {/* Embedded DAG assistant — collapsible chat about the causal model */}
      <Card className="gap-0 rounded-xl border border-border p-0">
        <button type="button"
          onClick={() => setChatOpen(v => !v)}
          className="flex w-full cursor-pointer items-center justify-between gap-2 border-none bg-transparent p-5 text-left">
          <div className="flex items-center gap-2">
            <MessageSquare size={15} className="flex-shrink-0 text-primary" />
            <div>
              <div className="text-[13px] font-semibold text-foreground">DAG assistant</div>
              <div className="mt-0.5 text-[12px] text-muted-foreground">
                Ask about the causal model — confounders, mediators, colliders, or add/remove a variable.
              </div>
            </div>
          </div>
          {chatOpen ? <ChevronUp size={16} className="text-muted-foreground" /> : <ChevronDown size={16} className="text-muted-foreground" />}
        </button>
        {chatOpen && (
          <div className="px-5 pb-5">
            <InlineChatbot
              history={chatProps.history ?? dagChat}
              onHistory={chatProps.onHistory ?? setDagChat}
              system={chatProps.system ?? DAG_CHAT_SYSTEM}
              suggestions={chatProps.suggestions ?? DAG_CHAT_SUGGESTIONS}
            />
          </div>
        )}
      </Card>

      {/* D4 — Data Gaps */}
      {dataGaps.length > 0 && (
        <Card className="gap-0 rounded-xl border border-[#EF9F27] bg-[#FFFBF0] p-5">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle size={15} className="text-[#B98900]" />
            <div className="text-[13px] font-semibold text-[#633806]">
              Data gaps — {dataGaps.length} variable{dataGaps.length !== 1 ? "s" : ""} important for this outcome but absent from dataset
            </div>
          </div>
          <div className="mb-3 text-[12.5px] leading-relaxed text-[#633806]">
            The Augura agent identified the following variables as important confounders or mediators for{" "}
            <strong>{{ hba1c:"HbA1c", ldl:"LDL-C", crp:"hs-CRP" }[selectedOutcome] ?? "this outcome"}</strong>{" "}
            based on published literature, but they are <strong>not present in the {partnerLabel} dataset</strong>.
          </div>
          <div className="flex flex-col gap-2">
            {dataGaps.map(n => (
              <div key={n.id} className="flex items-start gap-2.5 rounded-lg border border-[#EF9F27] bg-[#FFF3CD] p-[8px_12px]">
                <AlertTriangle size={13} className="mt-0.5 flex-shrink-0 text-[#A0650A]" />
                <div className="flex-1">
                  <div className="mb-1 flex items-center gap-1.5">
                    <span className="text-[12.5px] font-semibold text-[#633806]">{n.label}</span>
                    <span className="rounded-full border border-[#EF9F27] bg-[#EF9F2720] px-2 py-px text-[11px] text-[#633806]">
                      {n.role === "confounder" ? "Unmeasured confounder" : "Unmeasured mediator"}
                    </span>
                  </div>
                  <div className="text-[12px] leading-snug text-[#7A4B15]">
                    {n.rationale || "Clinically important — not captured in current dataset."}
                  </div>
                  <div className="mt-1 text-[12px] text-[#A0650A]">
                    Mitigation: {n.role === "confounder"
                      ? "E-value sensitivity analysis · proxy variable if available · flag in limitations"
                      : "Proxy adherence metric from platform · report as study limitation"}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-[#EF9F2760] pt-3 text-[12px] text-[#A0650A]">
            Source: Augura causal agent · Based on published RWE literature for this intervention-outcome pair
          </div>
        </Card>
      )}

    </div>
  );
}
