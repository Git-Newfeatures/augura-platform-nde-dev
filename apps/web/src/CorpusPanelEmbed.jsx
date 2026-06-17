// =============================================================================
// Augura · CorpusPanelEmbed
// Compact inline corpus intelligence panel for embedding in ProductProfile.
// =============================================================================

import { useState, useEffect, useMemo } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const ET_LABELS = {
  guidance:       "Guidance",
  rwe_study:      "RWE study",
  rct:            "RCT",
  preprint:       "Preprint",
  trial_record:   "Trial record",
  meta_analysis:  "Meta-analysis",
  adverse_events: "Adverse events",
  other:          "Other",
};

// Long-form descriptions surfaced as hover tooltips on the coverage matrix
// row/column labels. Targeted at clinical reviewers who asked what each tag means.
const ET_DESCRIPTIONS = {
  guidance:       "Regulatory guidance documents (FDA, EMA, HAS, etc.) describing how a device or therapy should be evaluated, classified, or submitted.",
  rwe_study:      "Real-world evidence studies — observational research using routinely collected data (claims, EHR, registries, digital cohorts), not protocolised trials.",
  rct:            "Randomised controlled trials — protocolised interventional studies with random assignment to treatment groups.",
  preprint:       "Pre-publication manuscripts (e.g. medRxiv, bioRxiv) — not yet peer-reviewed.",
  trial_record:   "ClinicalTrials.gov or similar registry entries describing trial protocols, recruitment status, and primary endpoints.",
  meta_analysis:  "Systematic reviews and meta-analyses aggregating evidence across multiple primary studies.",
  adverse_events: "Post-market safety reports submitted to regulators (e.g. MAUDE) describing device-related incidents or failures.",
  other:          "Documents not classified into a primary evidence type.",
};

const SOURCE_DESCRIPTIONS = {
  pubmed:         "Peer-reviewed biomedical literature indexed in PubMed.",
  clinicaltrials: "Trial protocols and registry entries from ClinicalTrials.gov.",
  maude:          "FDA's adverse event database for medical devices.",
  fda_guidance:   "FDA regulatory guidance documents — frameworks and submission requirements.",
  guidance:       "FDA regulatory guidance documents — frameworks and submission requirements.",
  "510k":         "FDA 510(k) premarket notifications — substantial equivalence submissions for medical devices.",
  semantic_scholar: "AI/ML literature indexed by Semantic Scholar (complements PubMed for compsci-leaning publications).",
};

// Data-driven badge colors for the latest-evidence feed — kept inline.
const ET_COLORS = {
  guidance:      { bg:"#FEF3C7", text:"#92400E" },
  rwe_study:     { bg:"#E1F5EE", text:"#085041" },
  rct:           { bg:"#E6F1FB", text:"#0C447C" },
  preprint:      { bg:"#EEEDFE", text:"#3C3489" },
  trial_record:  { bg:"#FAEEDA", text:"#633806" },
  meta_analysis: { bg:"#FCE7F3", text:"#831843" },
};

const DOMAIN_LABELS = {
  cardiometabolic:    "Cardiometabolic",
  womens_health:      "Women's health",
  preventive_health:  "Preventive health",
  patient_monitoring: "Patient monitoring",
  oncology_dx:        "Oncology DX",
  neurology:          "Neurology",
  respiratory:        "Respiratory",
  infectious_disease: "Infectious disease",
  ophthalmology:      "Ophthalmology",
  radiology_ai:       "Radiology AI",
  mental_health:      "Mental health",
  gastroenterology:   "Gastroenterology",
  samd_general:       "SaMD general",
  samd_biomarker:     "SaMD biomarker",
  regulatory_general: "Regulatory general",
  adverse_events:     "Adverse events",
  other:              "Other",
};

const JUR_LABELS = {
  fda:"FDA 🇺🇸", ema:"EMA 🇪🇺", mhra:"MHRA 🇬🇧",
  health_ca:"Health CA 🇨🇦", tga:"TGA 🇦🇺",
  imdrf:"IMDRF 🌐", global:"Global 🌐",
};

// Coverage map columns — all declared sources, ordered by volume descending.
// Low-count sources are included here but filtered at render time by MIN_COL_DOCS.
const COVERAGE_COLS = [
  "clinicaltrials",
  "guidance",
  "maude",
  "pubmed",
  "510k",
  "fda.gov",
  "medrxiv",
  "imdrf.org",
  "ema.europa.eu",
  "mhra.gov.uk",
];
const COL_LABELS = {
  clinicaltrials: "CT.gov",
  guidance:       "FDA",
  maude:          "MAUDE",
  pubmed:         "PubMed",
  "510k":         "510(k)",
  "fda.gov":      "FDA.gov",
  medrxiv:        "medRxiv",
  "imdrf.org":    "IMDRF",
  "ema.europa.eu":"EMA",
  "mhra.gov.uk":  "MHRA",
};
// Hide columns where every cell in the matrix is below this threshold.
// Prevents near-empty sources (1–2 docs) from wasting heatmap real estate.
const MIN_COL_DOCS = 10;

const SOURCE_LABEL_FALLBACK = {
  pubmed:        "PubMed",
  clinicaltrials:"CT.gov",
  maude:         "MAUDE",
  fda_guidance:  "FDA Guidance",
  guidance:      "FDA Guidance",
};

// Module-level — called from AgentMiniMap and CorpusPanelEmbed alike.
// agentSources is passed in; falls back to COL_LABELS then SOURCE_LABEL_FALLBACK.
function sourceLabel(code, agentSources = []) {
  return (agentSources ?? []).find(s => s.code === code)?.label
    ?? COL_LABELS[code]
    ?? SOURCE_LABEL_FALLBACK[code]
    ?? code;
}

// Fallback evidence_type when cesl_tags classification is absent
const SOURCE_ET_DEFAULTS = {
  clinicaltrials: "trial_record",
  maude:          "adverse_events",
  guidance:       "guidance",
  pubmed:         "rwe_study",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtCount = n =>
  n >= 10000 ? `${Math.round(n / 1000)}k`
  : n >= 1000 ? `${(n / 1000).toFixed(1)}k`
  : String(n);

function cellColorLog(count, norm) {
  if (count === 0) return { bg:"#FCEBEB", text:"#791F1F", border:"#F09595" };
  if (norm >= 0.6)  return { bg:"#E6F1FB", text:"#0C447C", border:"#85B7EB" };
  if (norm >= 0.3)  return { bg:"#E1F5EE", text:"#085041", border:"#5DCAA5" };
  if (norm >= 0.05) return { bg:"#FAEEDA", text:"#633806", border:"#EF9F27" };
  return                   { bg:"#FCEBEB", text:"#791F1F", border:"#F09595" };
}

function sourceBadgeStyle(sourceId) {
  const id = (sourceId ?? "").toLowerCase();
  if (id.includes("pubmed"))          return { bg:"#FCE7F3", text:"#831843" };
  if (id.includes("clinicaltrials"))  return { bg:"#E0F2FE", text:"#075985" };
  if (id.includes("maude"))           return { bg:"#FAEEDA", text:"#633806" };
  if (id === "guidance")              return { bg:"#FEF3C7", text:"#92400E" };
  if (id === "510k")                  return { bg:"#FEF3C7", text:"#92400E" };
  if (id.includes("fda"))             return { bg:"#FEF3C7", text:"#92400E" };
  if (id.includes("ema"))             return { bg:"#E1F5EE", text:"#085041" };
  if (id.includes("mhra"))            return { bg:"#EEEDFE", text:"#3C3489" };
  if (id.includes("imdrf"))           return { bg:"#E6F1FB", text:"#0C447C" };
  if (id.includes("medrxiv"))         return { bg:"#F1EFE8", text:"#444441" };
  return                                     { bg:"#F1EFE8", text:"#444441" };
}

function formatSourceId(sourceId) {
  if (!sourceId) return null;
  const id = sourceId.toLowerCase();
  if (id.includes("pubmed"))         return "PubMed";
  if (id.includes("clinicaltrials")) return "ClinicalTrials";
  if (id.includes("maude"))          return "MAUDE";
  if (id === "guidance" || id === "510k") return "FDA Guidance";
  if (id.includes("fda"))            return "FDA";
  if (id.includes("ema"))            return "EMA";
  if (id.includes("mhra"))           return "MHRA";
  if (id.includes("imdrf"))          return "IMDRF";
  if (id.includes("medrxiv"))        return "medRxiv";
  return sourceId.slice(0, 14);
}

function getFallbackUrl(sourceId, title) {
  const q = encodeURIComponent(title ?? "");
  switch ((sourceId ?? "").toLowerCase()) {
    case "pubmed":         return `https://pubmed.ncbi.nlm.nih.gov/?term=${q}`;
    case "clinicaltrials": return `https://clinicaltrials.gov/search?query=${q}`;
    case "fda_guidance":
    case "guidance":       return "https://www.fda.gov/medical-devices/guidance-documents-medical-devices-and-radiation-emitting-products";
    case "maude":          return "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfmaude/search.cfm";
    case "510k":           return `https://www.fda.gov/search?q=${q}`;
    default:               return "#";
  }
}

function docUrl(doc) {
  const raw = doc.url ?? doc.canonical_url;
  let finalUrl;
  if (!raw) {
    finalUrl = getFallbackUrl(doc.source_id, doc.title);
  } else if (doc.source_id === "fda_guidance" || doc.source_id === "guidance") {
    const idMatch = raw.match(/[?&]id=([^&]+)/i);
    finalUrl = idMatch
      ? `https://www.fda.gov/media/${idMatch[1]}/download`
      : raw;
  } else {
    finalUrl = raw;
  }
  return finalUrl;
}


// ── Feed Filter Bar ───────────────────────────────────────────────────────────
function FeedFilterBar({ etFilter, onEtFilter, srcFilter, onSrcFilter, availableEts, sourceTotals, agentSources = [] }) {
  const PillBtn = ({ active, disabled, onClick, children }) => (
    <button
      onClick={disabled ? undefined : onClick}
      className={`rounded-full border px-2 py-0.5 text-[9.5px] leading-[1.4] ${
        active
          ? "border-[#3172B0] bg-[#E6F1FB] text-[#3172B0]"
          : "border-border bg-card text-muted-foreground"
      } ${disabled ? "cursor-default opacity-40" : "cursor-pointer"}`}
    >
      {children}
    </button>
  );

  const srcOptions = [
    { label: "All sources",                  value: null },
    { label: sourceLabel("clinicaltrials", agentSources),  value: "clinicaltrials" },
    { label: sourceLabel("guidance",       agentSources),  value: "guidance" },
    { label: sourceLabel("maude",          agentSources),  value: "maude" },
    { label: sourceLabel("pubmed",         agentSources),  value: "pubmed" },
  ];

  return (
    <div className="mb-2.5 flex flex-wrap gap-1">
      <PillBtn active={etFilter === null} onClick={() => onEtFilter(null)}>All types</PillBtn>
      {availableEts.map(et => (
        <PillBtn key={et} active={etFilter === et} onClick={() => onEtFilter(et)}>
          {ET_LABELS[et] ?? et}
        </PillBtn>
      ))}
      <div className="my-0.5 mx-1 w-px self-stretch bg-border" />
      {srcOptions.map(o => {
        const hasData = o.value === null || (sourceTotals?.[o.value] ?? 0) > 0;
        return (
          <PillBtn
            key={o.value ?? "all-src"}
            active={srcFilter === o.value}
            disabled={!hasData}
            onClick={() => onSrcFilter(o.value)}
          >
            {o.label}
          </PillBtn>
        );
      })}
    </div>
  );
}

// ── Latest Evidence Feed ──────────────────────────────────────────────────────
function MiniPulseFeed({ documents, loading }) {
  if (loading) return (
    <div className="py-4 text-center text-[11px] text-muted-foreground">
      Loading…
    </div>
  );

  if (!documents?.length) return (
    <div className="py-3 text-center text-[11px] text-muted-foreground">
      No documents in this category yet.
    </div>
  );

  return (
    <div className="flex flex-col">
      {documents.map((doc, i) => {
        const etCol    = ET_COLORS[doc.evidence_type] ?? { bg: "#E6F1FB", text: "#0C447C" };
        const srcStyle = sourceBadgeStyle(doc.source_id);
        const srcLabel = formatSourceId(doc.source_id);
        const url      = docUrl(doc);

        return (
          <div key={doc.id ?? i}
            className={`py-[11px] ${i < documents.length - 1 ? "border-b-[0.5px] border-border" : ""}`}>
            <div className="mb-1 flex flex-wrap items-center gap-1.5">
              <Badge
                className="rounded-full px-[7px] py-[1.5px] text-[9.5px] font-medium"
                style={{ background: etCol.bg, color: etCol.text }}
              >
                {ET_LABELS[doc.evidence_type] ?? doc.evidence_type}
              </Badge>
              {srcLabel && (
                url ? (
                  <a href={url} target="_blank" rel="noreferrer" className="no-underline">
                    <Badge
                      className="cursor-pointer rounded-full px-[7px] py-[1.5px] text-[9.5px] font-medium"
                      style={{ background: srcStyle.bg, color: srcStyle.text }}
                    >
                      {srcLabel}
                    </Badge>
                  </a>
                ) : (
                  <Badge
                    className="rounded-full px-[7px] py-[1.5px] text-[9.5px] font-medium"
                    style={{ background: srcStyle.bg, color: srcStyle.text }}
                  >
                    {srcLabel}
                  </Badge>
                )
              )}
              {doc.is_new && (
                <Badge className="rounded-full border-[0.5px] border-[#5DCAA5] bg-secondary px-1.5 py-px text-[9.5px] font-normal text-primary">
                  New
                </Badge>
              )}
              <span className="ml-auto text-[9.5px] text-muted-foreground">
                {doc.age_label}
              </span>
            </div>
            {url ? (
              <a href={url} target="_blank" rel="noreferrer" className="no-underline">
                <div
                  className="mb-1 cursor-pointer text-[12px] font-medium leading-snug text-foreground"
                  onMouseEnter={e => { e.currentTarget.style.textDecoration = "underline"; }}
                  onMouseLeave={e => { e.currentTarget.style.textDecoration = "none"; }}
                >
                  {doc.title}
                </div>
              </a>
            ) : (
              <div className="mb-1 text-[12px] font-medium leading-snug text-foreground">
                {doc.title}
              </div>
            )}
            {doc.summary && (
              <div className="overflow-hidden text-[11px] leading-relaxed text-muted-foreground"
                style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                {doc.summary}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Title cleaner for agent-retrieved docs ────────────────────────────────────
function cleanRefTitle(title) {
  if (!title) return "Untitled document";
  let t = title.replace(/^Report ID:[^|]+\|?\s*/i, "");
  t = t.replace(/Device:\s*PDF[^|]*/gi, "");
  t = t.replace(/\|\s*/g, " · ").trim();
  t = t.replace(/PDF\s*\(\d+[\d.]+\s*KB\)PDF[^)]+\)/gi, "");
  const mesh = t.indexOf("MeSH:");
  if (mesh > 0) t = t.slice(0, mesh).trim();
  const cleaned = t.replace(/\s+/g, " ").trim();
  if (cleaned.length >= 10) return cleaned;
  return title.slice(0, 120).trim() || "Untitled document";
}

// ── Agent Mini Map — built from referencedDocs ────────────────────────────────
// Rows: distinct evidence_types; Columns: distinct source_ids.
// Clicking a cell filters the document list on the right.
function AgentMiniMap({ docs, agentFilter, onFilter, agentSources = [] }) {
  const sources = useMemo(() => {
    const s = new Set();
    for (const d of docs) if (d.source_id) s.add(d.source_id);
    return [...s].sort();
  }, [docs]);

  const evidenceTypes = useMemo(() => {
    const s = new Set();
    for (const d of docs) {
      if (!d.source_id) continue;
      s.add(d.evidence_type || SOURCE_ET_DEFAULTS[d.source_id] || "other");
    }
    return [...s].sort();
  }, [docs]);

  const counts = useMemo(() => {
    const map = {};
    for (const d of docs) {
      if (!d.source_id) continue;
      const et = d.evidence_type || SOURCE_ET_DEFAULTS[d.source_id] || "other";
      const k  = `${d.source_id}::${et}`;
      map[k] = (map[k] || 0) + 1;
    }
    return map;
  }, [docs]);

  const maxCount = useMemo(() =>
    Math.max(...Object.values(counts), 1)
  , [counts]);

  if (!sources.length || !evidenceTypes.length) return null;

  return (
    <div>
      <div className="overflow-x-auto">
        <table style={{ borderCollapse: "separate", borderSpacing: 3 }}>
          <thead>
            <tr>
              <th className="w-20" />
              {sources.map(src => (
                <th key={src}
                  title={SOURCE_DESCRIPTIONS[src] ? `${sourceLabel(src, agentSources)} — ${SOURCE_DESCRIPTIONS[src]}` : sourceLabel(src, agentSources)}
                  className="max-w-[44px] cursor-help overflow-hidden text-ellipsis whitespace-nowrap px-px pb-1.5 text-center font-mono text-[10px] font-medium text-muted-foreground">
                  {sourceLabel(src, agentSources)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {evidenceTypes.map(et => (
              <tr key={et}>
                <td
                  title={ET_DESCRIPTIONS[et] ? `${ET_LABELS[et] ?? et} — ${ET_DESCRIPTIONS[et]}` : (ET_LABELS[et] ?? et)}
                  className="cursor-help whitespace-nowrap pr-2 text-right font-mono text-[10px] text-muted-foreground">
                  {ET_LABELS[et] ?? et}
                </td>
                {sources.map(src => {
                  const count    = counts[`${src}::${et}`] ?? 0;
                  const norm     = count === 0 ? 0 : Math.log10(count + 1) / Math.log10(maxCount + 1);
                  const col      = cellColorLog(count, norm);
                  const isActive = agentFilter?.source_id === src && agentFilter?.evidence_type === et;
                  return (
                    <td key={src} className="p-0">
                      <div
                        onClick={() => count > 0 && onFilter(isActive ? null : { source_id: src, evidence_type: et })}
                        title={count > 0 ? `${count} doc${count !== 1 ? "s" : ""} · ${sourceLabel(src, agentSources)} × ${ET_LABELS[et] ?? et}` : undefined}
                        className={`flex h-9 w-11 items-center justify-center rounded-[5px] transition-[border] duration-100 ${count > 0 ? "cursor-pointer" : "cursor-default"}`}
                        style={{
                          background: count === 0 ? "#F9F8F5" : col.bg,
                          border: isActive
                            ? `2px solid #047857`
                            : `0.5px solid ${count === 0 ? "#D8D6CE" : col.border}`,
                        }}
                      >
                        <span
                          className="text-[12px] font-medium leading-none"
                          style={{ color: count === 0 ? "#888780" : col.text }}
                        >
                          {count === 0 ? "—" : fmtCount(count)}
                        </span>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── E1 References Section ─────────────────────────────────────────────────────
// Accepts already-deduped docs. filter = {source_id, evidence_type} | null.
function E1ReferencesSection({ docs, filter, onClearFilter, agentSources = [] }) {
  const [expanded, setExpanded] = useState(false);

  // Reset expand when filter changes
  useEffect(() => { setExpanded(false); }, [filter]);

  const COLLAPSED_LIMIT = 10;

  // Apply active filter — use effectiveEt so cells using SOURCE_ET_DEFAULTS still match
  const filtered = useMemo(() => {
    if (!filter) return docs;
    return docs.filter(d => {
      if (d.source_id !== filter.source_id) return false;
      const et = d.evidence_type || SOURCE_ET_DEFAULTS[d.source_id] || "other";
      return et === filter.evidence_type;
    });
  }, [docs, filter]);

  const extraCount = filtered.length - COLLAPSED_LIMIT;
  const displayDocs = filter ? filtered : (expanded ? filtered : filtered.slice(0, COLLAPSED_LIMIT));

  const DocRow = ({ doc, showBorder }) => {
    const src = sourceBadgeStyle(doc.source_id);
    const lbl = formatSourceId(doc.source_id);
    return (
      <a
        href={docUrl(doc)}
        target="_blank"
        rel="noreferrer"
        className={`flex cursor-pointer items-center gap-2 rounded-[4px] px-1.5 py-[7px] no-underline transition-colors duration-100 ${showBorder ? "border-b-[0.5px] border-border" : ""}`}
        onMouseEnter={e => { e.currentTarget.style.background = "#F6F4F1"; }}
        onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
      >
        {lbl && (
          <Badge
            className="flex-shrink-0 rounded-full px-[7px] py-[1.5px] text-[9.5px] font-medium"
            style={{ background: src.bg, color: src.text }}
          >
            {lbl}
          </Badge>
        )}
        <span className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] font-medium leading-snug text-foreground">
          {cleanRefTitle(doc.title)}
        </span>
        {doc.similarity_score != null && (
          <span
            title="Semantic similarity score — how closely this document matches the agent query (0–1 scale)"
            className="flex-shrink-0 cursor-help font-mono text-[10px] text-muted-foreground"
          >
            {doc.similarity_score.toFixed(2)}
          </span>
        )}
      </a>
    );
  };

  // Empty state
  if (!docs.length) {
    return (
      <div className="py-4 text-[11px] italic text-muted-foreground">
        Run the profiling agent to see which documents the Augura agent retrieved for this client.
      </div>
    );
  }

  // Column header
  const ColHeader = () => (
    <div className="mb-0.5 flex items-center border-b-[0.5px] border-border px-1.5 pb-1.5">
      <span className="flex-1 font-mono text-[9px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        Document
      </span>
      <span className="flex-shrink-0 font-mono text-[9px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        Relevance
      </span>
    </div>
  );

  return (
    <div>
      {/* Filter indicator */}
      {filter && (
        <div className="mb-2 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          <span>
            Showing {filtered.length} · {sourceLabel(filter.source_id, agentSources)} × {ET_LABELS[filter.evidence_type] ?? filter.evidence_type}
          </span>
          <button
            onClick={onClearFilter}
            title="Clear filter"
            className="cursor-pointer border-none bg-transparent px-0.5 text-[13px] leading-none text-muted-foreground"
          >
            ×
          </button>
        </div>
      )}

      <ColHeader />

      {displayDocs.map((doc, i) => (
        <DocRow
          key={doc.canonical_url ?? doc.url ?? i}
          doc={doc}
          showBorder={i < displayDocs.length - 1}
        />
      ))}

      {/* Show more / less — only when not filtered */}
      {!filter && extraCount > 0 && !expanded && (
        <button onClick={() => setExpanded(true)}
          className="mt-2 cursor-pointer border-none bg-transparent p-0 text-[10.5px] text-[#3172B0] underline underline-offset-[3px]">
          Show {extraCount} more →
        </button>
      )}
      {!filter && expanded && (
        <button onClick={() => setExpanded(false)}
          className="mt-1 cursor-pointer border-none bg-transparent p-0 text-[10.5px] text-[#3172B0] underline underline-offset-[3px]">
          Show less ←
        </button>
      )}
    </div>
  );
}

// ── Agent Retrieval Section — Section 1 ───────────────────────────────────────
// Owns dedup, agentFilter state, and mini map + document list layout.
function AgentRetrievalSection({ referencedDocs, agentSources = [] }) {
  const [agentFilter, setAgentFilter] = useState(null);

  // Dedup by composite key; keep highest similarity_score per key
  const deduped = useMemo(() => {
    if (!referencedDocs?.length) return [];
    const seen = new Map();
    for (const doc of referencedDocs) {
      const key = (doc.url || doc.canonical_url || "") + "::" + (doc.title || doc.filename || "");
      if (!key || key === "::") continue;
      if (!seen.has(key) || (doc.similarity_score ?? 0) > (seen.get(key).similarity_score ?? 0)) {
        seen.set(key, doc);
      }
    }
    return [...seen.values()].sort((a, b) => (b.similarity_score ?? 0) - (a.similarity_score ?? 0));
  }, [referencedDocs]);


  // N and M for the description line
  const distinctSources = useMemo(() => {
    const s = new Set(deduped.map(d => d.source_id).filter(Boolean));
    return s.size;
  }, [deduped]);

  // Map is always shown when docs are present — SOURCE_ET_DEFAULTS ensures rows exist
  const showMap = deduped.length > 0;

  // Description: report unique document count only (chunks are an internal detail)
  const description = useMemo(() => {
    if (!deduped.length) return "Run the profiling agent to populate agent retrieval.";
    return `The Augura agent retrieved ${deduped.length} unique document${deduped.length !== 1 ? "s" : ""} in this profiling run across ${distinctSources} source${distinctSources !== 1 ? "s" : ""}.`;
  }, [deduped.length, distinctSources]);

  return (
    <div>
      {/* Section label */}
      <div className="mb-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
        Augura agent retrieval · this profiling run
      </div>

      {/* Description */}
      <div className="mb-3 text-[11px] leading-relaxed text-muted-foreground">
        {description}
      </div>

      {/* 2-column layout when docs present (map always shown — SOURCE_ET_DEFAULTS fills rows) */}
      {showMap ? (
        <div className="grid grid-cols-[auto_1fr] gap-0">
          {/* Left: mini map */}
          <div className="border-r-[0.5px] border-border pr-4">
            <div className="mb-2.5">
              <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
                By source &amp; type
              </div>
              <div className="mt-[3px] font-mono text-[9px] text-muted-foreground">
                {deduped.length} unique documents
              </div>
            </div>
            <AgentMiniMap
              docs={deduped}
              agentFilter={agentFilter}
              onFilter={setAgentFilter}
              agentSources={agentSources}
            />
          </div>
          {/* Right: document list */}
          <div className="pl-4">
            <E1ReferencesSection
              docs={deduped}
              filter={agentFilter}
              onClearFilter={() => setAgentFilter(null)}
              agentSources={agentSources}
            />
          </div>
        </div>
      ) : (
        /* No docs yet */
        <E1ReferencesSection
          docs={deduped}
          filter={null}
          onClearFilter={null}
          agentSources={agentSources}
        />
      )}
    </div>
  );
}

// ── Main CorpusPanelEmbed ─────────────────────────────────────────────────────
export function CorpusPanelEmbed({ onViewFull, referencedDocs = [], clientDomains = [], clientEvidenceTypes = [], rawRetrievalCount = 0, agentSources = [] }) {
  const [sourceData,    setSourceData]    = useState(null);
  const [feedData,      setFeedData]      = useState(null);
  const [, setSourceLoading] = useState(true);
  const [feedLoading,   setFeedLoading]   = useState(true);
  const [collapsed,     setCollapsed]     = useState(false);
  const [showMore,      setShowMore]      = useState(false);
  const [etFilter,      setEtFilter]      = useState(null);
  const [srcFilter,     setSrcFilter]     = useState(null);
  // Section 2 collapsed by default; auto-expand when there's no agent run yet
  const [corpusExpanded, setCorpusExpanded] = useState(() => referencedDocs.length === 0);

  const domainsKey       = clientDomains.join(",");
  const evidenceTypesKey = clientEvidenceTypes.join(",");

  // Fetch coverage map (source × evidence_type) — used for filter pills + feed totals
  useEffect(() => {
    setSourceLoading(true);
    const params = new URLSearchParams();
    if (domainsKey)       params.set("domains",        domainsKey);
    if (evidenceTypesKey) params.set("evidence_types", evidenceTypesKey);
    const qs = params.toString() ? `?${params}` : "";
    fetch(`/api/corpus-sources${qs}`)
      .then(r => r.json())
      .then(setSourceData)
      .catch(console.error)
      .finally(() => setSourceLoading(false));
  }, [domainsKey, evidenceTypesKey]);

  // Fetch pulse feed — re-runs on filter changes
  useEffect(() => {
    setFeedLoading(true);
    const params = new URLSearchParams();
    params.set("limit", showMore ? "50" : "5");
    if (domainsKey)         params.set("domains",         domainsKey);
    if (evidenceTypesKey)   params.set("evidence_types",  evidenceTypesKey);
    if (etFilter)           params.set("evidence_type",   etFilter);
    if (srcFilter)          params.set("source_id",       srcFilter);
    const url = `/api/pulse-feed?${params}`;
    fetch(url)
      .then(r => r.json())
      .then(setFeedData)
      .catch(console.error)
      .finally(() => setFeedLoading(false));
  }, [showMore, etFilter, srcFilter, domainsKey, evidenceTypesKey]);

  function handleEtFilter(v)  { setEtFilter(v);  setShowMore(false); }
  function handleSrcFilter(v) { setSrcFilter(v); setShowMore(false); }
  function handleShowMore()   { setShowMore(true); }

  const matrix        = sourceData?.matrix ?? [];
  const evidenceTypes = sourceData?.meta?.evidence_types ?? [];
  const totalDocs     = sourceData?.meta?.total_docs;
  const feedCount     = feedData?.meta?.total ?? "—";

  // Evidence types available in corpus (for filter pills)
  const availableEts = evidenceTypes;

  // Per-source total doc counts — drives disabled state on source filter pills
  const sourceTotals = useMemo(() => {
    const totals = {};
    for (const src of COVERAGE_COLS) totals[src] = 0;
    for (const cell of matrix) {
      if (totals[cell.source_id] !== undefined)
        totals[cell.source_id] += Number(cell.doc_count ?? 0);
    }
    return totals;
  }, [matrix]);

  // Domain label for Section 2 heading
  const primaryDomain    = clientDomains[0] ?? null;
  const primaryDomainLbl = primaryDomain
    ? (DOMAIN_LABELS[primaryDomain] ?? primaryDomain.replace(/_/g, " "))
    : null;

  // Total docs description
  const totalDocsLbl = typeof totalDocs === "number" ? totalDocs.toLocaleString() : "—";

  return (
    <Card className="gap-0 overflow-hidden rounded-xl border-[0.5px] p-0 shadow-none">
      {/* ── Panel header ── */}
      <div className={`flex items-center justify-between bg-muted px-4 py-3 ${collapsed ? "" : "border-b-[0.5px] border-border"}`}>
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[7px] bg-[#E6F1FB] text-[13px] text-[#3172B0]">◈</div>
          <div>
            <div className="text-[12px] font-semibold text-foreground">
              Corpus Intelligence
            </div>
            <div className="font-mono text-[9px] text-muted-foreground">
              EVIDENCE LANDSCAPE
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onViewFull && (
            <Button variant="outline" onClick={onViewFull}
              className="h-auto rounded-[7px] px-3 py-[5px] text-[11px] font-normal text-muted-foreground">
              Full view →
            </Button>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? "Expand panel" : "Collapse panel"}
            className="flex h-7 w-7 flex-shrink-0 cursor-pointer items-center justify-center rounded-md border-[0.5px] border-border bg-card text-[14px] leading-none text-muted-foreground"
          >
            {collapsed ? "▴" : "▾"}
          </button>
        </div>
      </div>

      {/* ── Panel body ── */}
      {!collapsed && (
        <>
          {/* ── Section 1: Augura agent retrieval ── */}
          <div className="px-4 py-5">
            <AgentRetrievalSection referencedDocs={referencedDocs} rawRetrievalCount={rawRetrievalCount} agentSources={agentSources} />
          </div>

          {/* ── Divider ── */}
          <div className="border-t-[0.5px] border-border" />

          {/* ── Section 2: Indexed corpus ── */}
          <div className="px-4 py-5">
            {/* Section 2 header row with collapse toggle */}
            <div className="mb-1.5 flex items-center justify-between">
              <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
                Indexed corpus{primaryDomainLbl ? ` · ${primaryDomainLbl}` : ""}
              </div>
              <button
                onClick={() => setCorpusExpanded(e => !e)}
                title={corpusExpanded ? "Collapse section" : "Expand section"}
                className="flex h-[22px] w-[22px] flex-shrink-0 cursor-pointer items-center justify-center rounded-[5px] border-[0.5px] border-border bg-card text-[11px] leading-none text-muted-foreground"
              >
                {corpusExpanded ? "▾" : "▸"}
              </button>
            </div>

            {/* Description — always visible */}
            <div className="mb-2.5 text-[11px] leading-relaxed text-muted-foreground">
              {totalDocsLbl} documents indexed for this client&apos;s clinical profile across all sources. The Augura agent searches this corpus during profiling.
            </div>

            {/* Domain pills — always visible */}
            {clientDomains.length > 0 && (
              <div className={`flex flex-wrap gap-1.5 ${corpusExpanded ? "mb-4" : ""}`}>
                {clientDomains.map(d => (
                  <Badge key={d}
                    className="rounded-full border-[0.5px] border-[#B8D6F5] bg-[#E6F1FB] px-[9px] py-0.5 text-[9.5px] font-normal text-[#3172B0]">
                    {DOMAIN_LABELS[d] ?? d.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            )}

            {/* Pulse feed — only when expanded */}
            {corpusExpanded && (
              <>
                <div className="mb-2.5 flex items-center justify-between">
                  <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">
                    Pulse feed · latest evidence
                  </div>
                  <span className="font-mono text-[9px] text-muted-foreground">
                    {feedCount !== "—" ? `${feedCount} documents` : ""}
                  </span>
                </div>

                <FeedFilterBar
                  etFilter={etFilter}
                  onEtFilter={handleEtFilter}
                  srcFilter={srcFilter}
                  onSrcFilter={handleSrcFilter}
                  availableEts={availableEts}
                  sourceTotals={sourceTotals}
                  agentSources={agentSources}
                />

                <MiniPulseFeed
                  documents={feedData?.documents ?? []}
                  loading={feedLoading}
                />

                {(feedData?.documents?.length > 0) && !feedLoading && (
                  <button
                    onClick={showMore ? () => setShowMore(false) : handleShowMore}
                    className="mt-3 cursor-pointer border-none bg-transparent p-0 text-[10.5px] text-[#3172B0] underline underline-offset-[3px]"
                  >
                    {showMore ? "Show less ←" : "Show more →"}
                  </button>
                )}
              </>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

export default CorpusPanelEmbed;
