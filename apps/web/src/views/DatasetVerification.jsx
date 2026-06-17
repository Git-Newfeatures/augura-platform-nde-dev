import React, { useState, useEffect, useRef, useMemo } from "react";
import { Check, AlertTriangle, ChevronDown, ChevronUp, Database, Sparkles } from "lucide-react";
import { Card, Tag } from "../ui/components";
import { Button } from "@/components/ui/button";
import ExcelUpload from "@/components/ExcelUpload";
import { apiJson } from "@/api";
import { useReference } from "@/workspace/dataClient";

// ── PII column-name scan ──────────────────────────────────────────────────────
// Patterns are sourced from /reference/dq-rules; passed in from the component.
function scanForPII(sheets, piiPatterns) {
  const flagged = [];
  for (const sheet of sheets || []) {
    for (const h of sheet.headers || []) {
      const name = String(h || "").toLowerCase().trim();
      if (!name) continue;
      for (const p of piiPatterns || []) {
        if (p.rx.test(name)) { flagged.push({ sheet: sheet.name, column: h, reason: p.reason }); break; }
      }
    }
  }
  return { status: flagged.length ? "error" : "ok", flagged };
}

// Presentation-only group colors (the API carries no per-group color). Reused by
// the GROUPS memo in the component; falls back to ROLE_TAG / 'b' when absent.
const GROUP_TAG = {
  outcomes: "b", exposure: "g", engagement: "p", administrative: "b", other: "r",
};

const ROLE_TAG = {
  outcome: "b", exposure: "g", exposure_component: "g",
  measured_confounder: "a", unmeasured_confounder: "r",
  mediator: "p", effect_modifier: "p", collider: "r",
  id: "b", time: "b", unused: "r", other: "r",
};

const LOW_CONFIDENCE = 0.7;

// ── Launch progress stages (estimated — the API is a single round-trip) ────────
const STAGES = [
  { key: "scan",      label: "Scanning columns" },
  { key: "classify",  label: "Classifying variables" },
  { key: "structure", label: "Inferring study structure" },
];

// ── DQ badges ─────────────────────────────────────────────────────────────────
function DQBadges({ stat }) {
  if (!stat) return null;
  const nullPct = stat.null_pct ?? 0;
  const nullClass = nullPct >= 0.3 ? "text-[#C0392B]" : nullPct >= 0.1 ? "text-[#C47F0A]" : "text-muted-foreground";
  return (
    <div className="flex flex-wrap gap-1.5 font-mono text-[12px] text-muted-foreground">
      <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
        {stat.value_kind}
      </span>
      <span className={`rounded-full border border-border bg-secondary/40 px-2 py-0.5 ${nullClass}`}>
        null {(nullPct*100).toFixed(1)}%
      </span>
      {stat.n_distinct != null && (
        <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
          {stat.n_distinct} distinct
        </span>
      )}
      {stat.value_kind === "numeric" && stat.min != null && (
        <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
          {stat.min}–{stat.max}
        </span>
      )}
    </div>
  );
}

// ── Confidence bar ────────────────────────────────────────────────────────────
function ConfBar({ value }) {
  const pct = Math.max(0, Math.min(1, value || 0));
  const color = pct >= 0.8 ? "#047857" : pct >= LOW_CONFIDENCE ? "#C47F0A" : "#C0392B";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-12 overflow-hidden rounded-full border border-border bg-secondary/40">
        <div className="h-full" style={{ width:`${pct*100}%`, background:color }} />
      </div>
      <span className="font-mono text-[12px] font-semibold" style={{ color }}>{(pct*100).toFixed(0)}%</span>
    </div>
  );
}

// ── Single column row (inside an expanded group) ──────────────────────────────
function ColumnRow({ match, stat, decision, onDecide, roles, roleLabel }) {
  const [expanded, setExpanded] = useState(false);
  const role = decision?.final_role || match.proposed_role;
  const status = decision?.user_decision;

  const dotColor = status === "agreed" ? "#047857" : status === "corrected" ? "#C47F0A" :
                   status === "rejected" ? "#C0392B" : "#C4C2BA";

  return (
    <div
      className={`border-b border-border last:border-b-0 ${role === "unused" ? "bg-secondary/40 opacity-70" : "bg-card opacity-100"}`}
    >
      {/* Compact row */}
      <div className="flex cursor-pointer items-center gap-2.5 px-4 py-2.5" onClick={() => setExpanded(v => !v)}>
        {/* Status dot */}
        <div className="h-2 w-2 flex-shrink-0 rounded-full" style={{ background: dotColor }} />
        {/* Column name */}
        <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[12px] font-medium text-foreground">
          {match.column}
        </span>
        {/* Role tag */}
        <Tag color={ROLE_TAG[role]}>{roleLabel[role]}</Tag>
        {match.proposed_canonical_label && (
          <span className="max-w-[140px] overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-muted-foreground">
            → {match.proposed_canonical_label}
          </span>
        )}
        <ConfBar value={match.confidence} />
        {expanded
          ? <ChevronUp size={15} className="text-muted-foreground/60" />
          : <ChevronDown size={15} className="text-muted-foreground/60" />}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border bg-secondary/40 px-4 pb-4 pl-9 pt-3">
          <DQBadges stat={stat} />
          {match.rationale && (
            <div className="mt-2 rounded-md border-l-2 border-l-[#3172B0] bg-card px-3 py-2 text-[12.5px] leading-relaxed text-muted-foreground">
              {match.rationale}
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="sm" variant={status !== "agreed" ? "default" : "outline"}
              className="text-xs font-medium"
              onClick={() => onDecide({ user_decision:"agreed", final_role:match.proposed_role, final_canonical_id:match.proposed_canonical_id })}
              style={{ opacity: status === "agreed" ? 0.6 : 1 }}>
              {status === "agreed" ? <><Check size={13} className="mr-1" />Agreed</> : "Agree"}
            </Button>
            <select
              value={status === "corrected" ? decision.final_role : ""}
              onChange={e => e.target.value && onDecide({ user_decision:"corrected", final_role:e.target.value, final_canonical_id: e.target.value === "outcome" ? match.proposed_canonical_id : null })}
              className="cursor-pointer rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground">
              <option value="">Reassign role…</option>
              {roles.filter(r => r !== match.proposed_role).map(r => (
                <option key={r} value={r}>{roleLabel[r]}</option>
              ))}
            </select>
            <Button size="sm" variant="outline" className="text-xs font-medium"
              onClick={() => onDecide({ user_decision:"corrected", final_role:"unused", final_canonical_id:null })}>
              Mark unused
            </Button>
            {match.alternatives?.length > 0 && (
              <span className="text-[12px] italic text-muted-foreground">
                alt: {match.alternatives.join(", ")}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Group accordion ───────────────────────────────────────────────────────────
function GroupAccordion({ group, matches, statFor, variableMappings, onDecide, onAgreeAll, defaultOpen, roles, roleLabel }) {
  const [open, setOpen] = useState(defaultOpen);
  if (!matches.length) return null;

  const decided = matches.filter(m => {
    const d = variableMappings?.[`${m.sheet}::${m.column}`];
    return d?.user_decision && d.user_decision !== "pending";
  }).length;
  const allDone = decided === matches.length;

  function agreeAll() {
    onAgreeAll(matches);
  }

  const tagColor = group.tagColor;

  return (
    <Card className={`gap-0 overflow-hidden p-0 ${allDone ? "border-[#5DCAA5]" : ""}`}>
      {/* Group header */}
      <div className={`flex cursor-pointer items-center gap-3 px-4 py-3 ${allDone ? "bg-secondary" : "bg-card"}`}
        onClick={() => setOpen(v => !v)}>
        <Tag color={tagColor}>{matches.length}</Tag>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-foreground">{group.label}</div>
          <div className="mt-0.5 text-[12px] text-muted-foreground">{group.description}</div>
        </div>
        <div className="flex items-center gap-2.5">
          {allDone ? (
            <span className="flex items-center gap-1 text-[12px] font-semibold text-primary"><Check size={13} /> All confirmed</span>
          ) : (
            <span className="font-mono text-[12px] text-muted-foreground">{decided}/{matches.length} confirmed</span>
          )}
          {!allDone && (
            <Button size="sm" className="text-xs font-medium" onClick={e => { e.stopPropagation(); agreeAll(); }}>
              Agree all
            </Button>
          )}
          {open
            ? <ChevronUp size={15} className="text-muted-foreground/60" />
            : <ChevronDown size={15} className="text-muted-foreground/60" />}
        </div>
      </div>

      {/* Column rows */}
      {open && (
        <div className="border-t border-border">
          {matches.map(m => {
            const key = `${m.sheet}::${m.column}`;
            return (
              <ColumnRow
                key={key}
                match={m}
                stat={statFor(m.sheet, m.column)}
                decision={variableMappings?.[key]}
                onDecide={patch => onDecide(m, patch)}
                roles={roles}
                roleLabel={roleLabel}
              />
            );
          })}
        </div>
      )}
    </Card>
  );
}

// ── Dataset-level questions (DGM Q1–Q4) ──────────────────────────────────────
const DATASET_Q_LABELS = {
  study_type:          "How was this data collected?",
  temporal_structure:  "Is this data cross-sectional or longitudinal?",
  exposure_assignment: "How were users assigned to the exposure?",
  control_group:       "Is there an unexposed control group?",
};

function DatasetQuestionCard({ q }) {
  const [decision, setDecision] = useState({ status:"pending", answer:q.answer });
  return (
    <Card className={`gap-2 p-4 ${decision.status === "agreed" ? "border-[#5DCAA5]" : ""}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-[13px] font-semibold text-foreground">
          {DATASET_Q_LABELS[q.question_code] || q.question_code}
        </div>
        {decision.status === "agreed" && (
          <span className="flex items-center gap-1 rounded-full border border-[#5DCAA5] bg-secondary px-2.5 py-0.5 text-[12px] font-semibold text-primary"><Check size={12} /> Agreed</span>
        )}
        {decision.status === "corrected" && (
          <span className="rounded-full border border-[#EF9F27] bg-[#FAEEDA] px-2.5 py-0.5 text-[12px] font-semibold text-[#854F0B]">Corrected</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12px] font-medium text-muted-foreground">Agent answer</span>
        <Tag color="b">{decision.answer}</Tag>
        <span className="font-mono text-[12px] text-muted-foreground">
          {(q.confidence*100).toFixed(0)}% confidence
        </span>
      </div>
      {q.rationale && (
        <div className="rounded-md border-l-2 border-l-[#3172B0] bg-secondary/40 px-3 py-2 text-[12.5px] leading-relaxed text-muted-foreground">
          {q.rationale}
          {q.evidence_columns?.length > 0 && (
            <div className="mt-1 font-mono text-[12px] text-muted-foreground/70">
              evidence: {q.evidence_columns.slice(0,6).join(" · ")}
            </div>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={decision.status !== "agreed" ? "default" : "outline"}
          className="text-xs font-medium"
          onClick={() => setDecision({ status:"agreed", answer:q.answer })}
          style={{ opacity: decision.status === "agreed" ? 0.6 : 1 }}>
          {decision.status === "agreed" ? <><Check size={13} className="mr-1" />Agreed</> : "Agree"}
        </Button>
        {q.options?.length > 0 && (
          <select
            value={decision.status === "corrected" ? decision.answer : ""}
            onChange={e => e.target.value && setDecision({ status:"corrected", answer:e.target.value })}
            className="cursor-pointer rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground">
            <option value="">Choose a different answer…</option>
            {q.options.filter(o => o !== q.answer).map(o => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        )}
      </div>
    </Card>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────
export default function DatasetVerification({
  uploadedData, onUploadData,
  product, users, outcome,
  tenantSlug,
  selectedCohort, onCohortSelect,
  variableMappings, setVariableMappings,
  variableCheckResult, setVariableCheckResult,
  onRunProfiling,
}) {
  const { data: dqRules } = useReference("dq_rules");
  const { data: varRoles } = useReference("variable_roles");

  const PII_PATTERNS = useMemo(
    () => (dqRules?.pii_patterns ?? []).map((p) => ({ rx: new RegExp(p.pattern, "i"), reason: p.label })),
    [dqRules]);
  const GROUPS = useMemo(
    () => (varRoles?.groups ?? []).map((g) => ({
      id: g.code, label: g.label, description: g.description, tagColor: GROUP_TAG[g.code] ?? ROLE_TAG[g.code] ?? "b",
    })), [varRoles]);
  const GROUP_REMAP = useMemo(() => varRoles?.group_aliases ?? {}, [varRoles]);
  const ROLES = useMemo(
    () => (varRoles?.roles ?? []).filter((r) => r.selectable).map((r) => r.code), [varRoles]);
  const ROLE_LABEL = useMemo(
    () => Object.fromEntries((varRoles?.roles ?? []).map((r) => [r.code, r.label])), [varRoles]);

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);

  // Animate an estimated progress curve while the agent runs. Eases toward 0.92
  // and never reaches 1 until the response lands (set in runCheck's finally).
  useEffect(() => {
    if (!loading) return;
    setProgress(0.05);
    const started = Date.now();
    const EST_MS = 14000; // typical run after parallelization + haiku
    const id = setInterval(() => {
      const t = (Date.now() - started) / EST_MS;
      setProgress(Math.min(0.92, 1 - Math.exp(-2.3 * t)));
    }, 150);
    return () => clearInterval(id);
  }, [loading]);
  const [error, setError] = useState(null);

  const result = variableCheckResult;
  function setResult(data) { setVariableCheckResult(data); }

  // Persist the verified dataset to the library (existing endpoints). Idempotent per
  // upload via savedDatasetId; non-blocking so profiling proceeds even if it fails.
  const savedDatasetId = useRef(null);
  const isUuid = (s) =>
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s || "");

  async function persistDataset() {
    if (!uploadedData) return;
    try {
      const name = (uploadedData.filename || "cohort").replace(/\.(xlsx?|csv)$/i, "");
      const rowCount = uploadedData.sheets.reduce(
        (a, s) => a + (s.totalRowCount ?? s.data?.length ?? 0), 0,
      );
      const columns = [];
      for (const sheet of uploadedData.sheets || []) {
        for (const st of (sheet.column_stats || [])) {
          const key = `${sheet.name}::${st.column}`;
          const dec = variableMappings?.[key] || {};
          const match = result?.matches?.find(
            (m) => m.sheet === sheet.name && m.column === st.column,
          );
          columns.push({
            sheet: sheet.name,
            name: st.column,
            value_kind: st.value_kind ?? null,
            n_total: st.n_total ?? null,
            n_non_null: st.n_non_null ?? null,
            null_pct: st.null_pct ?? null,
            n_distinct: st.n_distinct ?? null,
            min: st.min ?? null,
            max: st.max ?? null,
            top_values: st.top_values ?? null,
            proposed_role: match?.proposed_role ?? null,
            proposed_group: match?.proposed_group ?? null,
            proposed_canonical_id: match?.proposed_canonical_id ?? null,
            confidence: match?.confidence ?? null,
            rationale: match?.rationale ?? null,
            user_decision: dec.user_decision ?? "pending",
            final_role: dec.final_role ?? null,
            final_canonical_id: dec.final_canonical_id ?? null,
          });
        }
      }
      let id = savedDatasetId.current;
      if (!id) {
        const ds = await apiJson("/datasets", {
          method: "POST",
          body: JSON.stringify({
            name,
            study_id: isUuid(tenantSlug) ? tenantSlug : null,
            row_count: rowCount,
          }),
        });
        id = ds.id;
        savedDatasetId.current = id;
      }
      if (columns.length) {
        await apiJson(`/datasets/${id}/columns`, {
          method: "PUT",
          body: JSON.stringify({ columns }),
        });
      }
    } catch (e) {
      // Non-blocking — the profiling run continues regardless.
      console.warn("[dataset persist]", e?.message);
    }
  }

  // Gate the PII scan on the dq-rules catalog so the auto-run below never fires
  // (status "ok") before the real PII patterns have loaded.
  const piiScan = (uploadedData && dqRules) ? scanForPII(uploadedData.sheets, PII_PATTERNS) : null;

  const productDescription = [
    product  && `PRODUCT:\n${product}`,
    users    && `USERS:\n${users}`,
    outcome  && `OUTCOMES OF INTEREST:\n${outcome}`,
  ].filter(Boolean).join("\n\n");

  function statFor(sheetName, column) {
    const sheet = uploadedData?.sheets?.find(s => s.name === sheetName);
    return sheet?.column_stats?.find(s => s.column === column);
  }

  function handleUpload(data) {
    onUploadData(data);
    if (!data) setResult(null);
    setError(null);
    if (data && onCohortSelect) {
      const name = data.filename.replace(/\.(xlsx?|csv)$/i,"").replace(/\s+/g,"_").toLowerCase();
      const rowCount = data.sheets.reduce((a,s) => a+(s.data?.length??0), 0);
      onCohortSelect(name, rowCount);
    }
    if (!data && onCohortSelect) onCohortSelect(selectedCohort, null);
  }

  async function runCheck() {
    if (!uploadedData) return;
    setLoading(true); setError(null);
    try {
      const payload = {
        projectId: tenantSlug,
        product_description: productDescription,
        sheets: uploadedData.sheets.map(s => ({
          name: s.name, headers: s.headers,
          sample: s.data?.slice(0,5) || [],
          column_stats: s.column_stats || [],
        })),
      };
      const data = await apiJson("/agents/variable-check", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(data);
      // Seed decisions — keep any existing decisions, only seed missing ones
      const seed = { ...(variableMappings || {}) };
      for (const m of data.matches) {
        const key = `${m.sheet}::${m.column}`;
        if (!seed[key]) {
          seed[key] = { user_decision:"pending", final_role:m.proposed_role, final_canonical_id:m.proposed_canonical_id };
        }
      }
      setVariableMappings(seed);
      setProgress(1);
    } catch(e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Auto-run on first upload if no cached result
  const [autoRan, setAutoRan] = useState(false);
  useEffect(() => {
    if (uploadedData && !result && !loading && !error && piiScan?.status === "ok" && !autoRan) {
      setAutoRan(true);
      runCheck();
    }
  }, [uploadedData, result, loading, error, piiScan, autoRan]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset cached results when a freshly uploaded file replaces the prior one.
  function handleUploadAndReset(data) {
    setResult(null); setError(null); setAutoRan(false);
    savedDatasetId.current = null; // a new file → a new library entry on next save
    handleUpload(data);
  }

  function onDecide(match, patch) {
    const key = `${match.sheet}::${match.column}`;
    setVariableMappings({ ...(variableMappings||{}), [key]: { ...(variableMappings?.[key]||{}), ...patch } });
  }

  function onAgreeAll(groupMatches) {
    const batch = { ...(variableMappings || {}) };
    for (const m of groupMatches) {
      batch[`${m.sheet}::${m.column}`] = {
        user_decision: "agreed",
        final_role: m.proposed_role,
        final_canonical_id: m.proposed_canonical_id,
      };
    }
    setVariableMappings(batch);
  }

  // Master agree-all: accept every agent proposal across all groups in one click.
  function onAgreeAllGlobal() {
    onAgreeAll(result?.matches || []);
  }

  // ── Derived data ────────────────────────────────────────────────────────────
  const matches = result?.matches || [];
  const nTotal = matches.length;
  const nDecided = Object.values(variableMappings || {})
    .filter(d => d.user_decision && d.user_decision !== "pending").length;

  // Needs review: low confidence AND not yet decided
  const needsReview = matches.filter(m => {
    const key = `${m.sheet}::${m.column}`;
    const decided = variableMappings?.[key]?.user_decision;
    return m.confidence < LOW_CONFIDENCE && (!decided || decided === "pending");
  });

  // Group matches — apply GROUP_REMAP so API-returned legacy group IDs
  // land in the correct consolidated accordion.
  const byGroup = {};
  for (const g of GROUPS) byGroup[g.id] = [];
  for (const m of matches) {
    const raw = m.proposed_group || "other";
    const g = GROUP_REMAP[raw] ?? raw;
    if (byGroup[g]) byGroup[g].push(m);
    else byGroup["other"].push(m);
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div>
        <div className="text-[13px] font-semibold text-primary">1b · Dataset & data structure</div>
        <div className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
          Upload the cohort dataset to profile. The agent maps each column to a canonical outcome or proposes its causal role, grouped by type. Confirm or correct — then run profiling.
        </div>
      </div>

      {/* Upload card */}
      <Card className="gap-4 rounded-xl p-5">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <Database size={15} className="text-muted-foreground" /> Cohort dataset
        </div>
        <div className="text-[12.5px] text-muted-foreground">Upload the cohort dataset the agent should profile. Columns are classified below.</div>
        <ExcelUpload onData={handleUploadAndReset} uploadedData={uploadedData} />

        {uploadedData && (
          <div className="flex flex-col gap-2">
            {selectedCohort && (
              <div className="flex items-center gap-2 rounded-md border border-[#5DCAA5] bg-[#E1F5EE] px-3 py-2 text-[12px] text-primary">
                <Check size={14} className="flex-shrink-0" />
                <span>Cohort matched: <strong>{selectedCohort}</strong></span>
              </div>
            )}
            {piiScan?.status === "ok" && (
              <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-3 py-2 text-[12px] text-muted-foreground">
                <Check size={14} className="flex-shrink-0 text-primary" />
                <span>No PII / PHI column names detected.</span>
              </div>
            )}
            {piiScan?.status === "error" && (
              <div className="rounded-md border border-[#F09595] bg-[#FCEBEB] px-3 py-2.5 text-[12.5px] text-[#C0392B]">
                <strong className="flex items-center gap-1.5"><AlertTriangle size={14} className="flex-shrink-0" /> PII / PHI columns detected — remove before running variable check:</strong>
                <ul className="ml-5 mt-1.5 list-disc p-0">
                  {piiScan.flagged.map((f,i) => (
                    <li key={i}><code className="font-mono">{f.column}</code> ({f.reason}) in <em>{f.sheet}</em></li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {uploadedData && (
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" className="text-xs font-medium" onClick={runCheck}
              disabled={loading || (piiScan?.status === "error")}>
              {loading ? "Analysing…" : result ? "Re-run variable check" : "Run variable check"}
            </Button>
            {result && (
              <span className="text-[12px] text-muted-foreground">
                domain: <strong className="font-mono">{result.clinical_domain || "—"}</strong>
                {" · "}<span className="font-mono">{result.total_columns}</span> columns
                {result.batches > 1 && <> · <span className="font-mono">{result.batches}</span> batches</>}
              </span>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-md border border-[#F09595] bg-[#FCEBEB] px-3 py-2 text-[12.5px] text-[#C0392B]">
            {error}
          </div>
        )}
      </Card>

      {/* Loading — horizontal stepper with estimated progress */}
      {loading && (() => {
        const activeIdx = progress < 0.4 ? 0 : progress < 0.8 ? 1 : 2;
        const totalCols = uploadedData?.sheets?.reduce((a,s) => a+(s.headers?.length||0), 0);
        return (
          <Card className="gap-4 rounded-xl p-5">
            <div className="flex flex-col gap-4">
              {/* node + connector row */}
              <div className="flex items-start">
                {STAGES.map((s, i) => {
                  const done = i < activeIdx;
                  const active = i === activeIdx;
                  const tint = done ? "#047857" : active ? "#3172B0" : "#D8D6CE";
                  return (
                    <React.Fragment key={s.key}>
                      <div className="flex min-w-[96px] flex-col items-center gap-2">
                        <div
                          className="flex h-6 w-6 items-center justify-center rounded-full font-mono text-[12px] font-semibold transition-all"
                          style={{
                            background: done ? "#047857" : active ? "#3172B0" : "#F9F8F5",
                            color: (done || active) ? "#fff" : "#888780",
                            border:`1px solid ${tint}`,
                          }}>
                          {done ? <Check size={13} /> : i + 1}
                        </div>
                        <span className={`text-center text-[12px] leading-snug ${active ? "text-foreground" : done ? "text-muted-foreground" : "text-muted-foreground/60"}`}>
                          {s.label}{active ? "…" : ""}
                        </span>
                      </div>
                      {i < STAGES.length - 1 && (
                        <div className="relative mt-[11px] h-0.5 flex-1 rounded-full bg-secondary/60">
                          <div className="absolute inset-0 rounded-full transition-[width] duration-[400ms]"
                            style={{ width: i < activeIdx ? "100%" : "0%", background:"#047857" }} />
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
              {/* overall progress bar */}
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary/60">
                <div className="h-full rounded-full transition-[width] duration-[250ms] ease-linear"
                  style={{ background:"#3172B0", width:`${Math.round(progress*100)}%` }} />
              </div>
              <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                <Sparkles size={13} className="text-[#3172B0]" />
                Agent reviewing <span className="font-mono">{totalCols}</span> columns…
              </div>
            </div>
          </Card>
        );
      })()}

      {/* Results */}
      {result && !loading && (
        <>
          {/* Summary strip */}
          <Card className="rounded-xl p-5">
            <div className="flex flex-wrap items-center gap-4">
              <div>
                <div className="text-[12px] font-medium text-muted-foreground">Decisions</div>
                <div className="mt-0.5 font-mono text-[22px] font-semibold text-foreground">
                  {nDecided}<span className="text-[13px] text-muted-foreground"> / {nTotal}</span>
                </div>
              </div>
              <div className="h-8 w-px bg-border" />
              {GROUPS.map(g => byGroup[g.id]?.length ? (
                <div key={g.id} className="flex items-center gap-1.5">
                  <Tag color={g.tagColor}>{g.label}</Tag>
                  <span className="font-mono text-[13px] font-semibold text-foreground">{byGroup[g.id].length}</span>
                </div>
              ) : null)}
              <div className="flex-1" />
              <Button size="sm" className="text-xs font-medium" onClick={onAgreeAllGlobal} disabled={nDecided === nTotal}>
                {nDecided === nTotal ? <><Check size={13} className="mr-1" />All agreed</> : `Agree all (${nTotal})`}
              </Button>
            </div>
          </Card>

          {/* Dataset structure questions */}
          {result.dataset_questions?.length > 0 && (
            <Card className="gap-4 rounded-xl p-5">
              <div className="text-[13px] font-semibold text-foreground">
                Dataset structure — agent inferences
              </div>
              <div className="flex flex-col gap-3">
                {result.dataset_questions.map((q,i) => (
                  <DatasetQuestionCard key={q.question_code||i} q={q} />
                ))}
              </div>
            </Card>
          )}

          {/* Needs review — always open */}
          {needsReview.length > 0 && (
            <Card className="gap-0 overflow-hidden rounded-xl border-[#EF9F27] p-0">
              <div className="flex items-center gap-3 bg-[#FAEEDA] px-4 py-3">
                <AlertTriangle size={16} className="flex-shrink-0 text-[#B98900]" />
                <div className="flex-1">
                  <div className="text-[13px] font-semibold text-[#633806]">
                    Needs review — {needsReview.length} column{needsReview.length===1?"":"s"} with low confidence
                  </div>
                  <div className="mt-0.5 text-[12px] text-[#854F0B]">
                    Agent confidence below 70% — review these before bulk-confirming groups
                  </div>
                </div>
              </div>
              <div className="border-t border-border bg-card">
                {needsReview.map(m => {
                  const key = `${m.sheet}::${m.column}`;
                  return (
                    <ColumnRow
                      key={key} match={m} stat={statFor(m.sheet, m.column)}
                      decision={variableMappings?.[key]}
                      onDecide={patch => onDecide(m, patch)}
                      roles={ROLES}
                      roleLabel={ROLE_LABEL}
                    />
                  );
                })}
              </div>
            </Card>
          )}

          {/* Groups */}
          {GROUPS.map(g => (
            <GroupAccordion
              key={g.id}
              group={g}
              matches={byGroup[g.id] || []}
              statFor={statFor}
              variableMappings={variableMappings}
              onDecide={onDecide}
              onAgreeAll={onAgreeAll}
              defaultOpen={false}
              roles={ROLES}
              roleLabel={ROLE_LABEL}
            />
          ))}

          {/* Pending count + Back / Run-profiling footer */}
          <div className="mt-1 flex items-center justify-between gap-3 border-t border-border pt-4">
            <div className="flex items-center gap-3">
              {nDecided < nTotal && (
                <span className="text-[12px] italic text-[#854F0B]">
                  {nTotal - nDecided} column{nTotal - nDecided===1?"":"s"} still pending
                </span>
              )}
              <Button className="text-xs font-medium" disabled={nDecided !== nTotal} onClick={() => { persistDataset(); onRunProfiling?.(); }}>
                {nDecided === nTotal ? "Run profiling →" : "Confirm all columns first"}
              </Button>
            </div>
          </div>
        </>
      )}

      {!uploadedData && (
        <Card className="rounded-xl p-5">
          <div className="text-[12.5px] leading-relaxed text-muted-foreground">
            Upload a cohort dataset above to begin. The agent will identify each column's role
            and group — outcomes matched against <strong>cesl_outcome</strong>,
            engagement / demographics / confounders grouped automatically.
            Light data-quality signals (missingness, value type, range) feed the agent's confidence.
          </div>
        </Card>
      )}

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}
