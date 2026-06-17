import { useState, useEffect, useMemo } from "react";
import { ArrowLeft, ArrowRight, Target, Activity, Users, CornerDownLeft, Check, Edit3 } from "lucide-react";
import { fetchCohort, engagementGroup } from "../workspace/cohortData";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoBar, Tag } from "../ui/components";
import { EmptyState } from "@/components/EmptyState";
import InlineChatbot from "../components/InlineChatbot";
import { useReference, normOutcomeCatalog } from "@/workspace/dataClient";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 2c: OUTCOME SELECTION
// ─────────────────────────────────────────────────────────────────────────────

// Multi-select pill toggle helper
function MultiPill({ options, selected, onToggle }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(o => {
        const active = selected.includes(o);
        return (
          <div key={o} onClick={() => onToggle(o)}
            className={`cursor-pointer rounded-full border px-3 py-1.5 text-[12px] transition-colors ${
              active ? "border-primary bg-secondary font-medium text-primary" : "border-border font-normal text-muted-foreground hover:border-primary/40"
            }`}>
            {o}
          </div>
        );
      })}
    </div>
  );
}

// ── Per-element header: title + icon, agent rationale line, Confirm / Edit toggle ──
// `editing` gates the visibility of the existing selector below (passed as children
// by the caller). When confirmed (not editing), the caller renders a compact summary.
function ElementHeader({ icon: Icon, label, accent, rationale, editing, onEdit, onConfirm }) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-foreground">
          <Icon size={15} style={{ color: accent }} />
          {label}
        </div>
        {rationale && (
          <div className="flex items-start gap-1.5 text-[11px] italic leading-snug text-muted-foreground">
            <span className="not-italic" aria-hidden>🤖</span>
            <span>{rationale}</span>
          </div>
        )}
      </div>
      <div className="flex flex-shrink-0 items-center gap-1.5">
        <button type="button" onClick={onConfirm}
          className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors ${
            editing
              ? "border-border bg-card text-muted-foreground hover:border-primary/40"
              : "border-primary bg-secondary text-primary"
          }`}>
          <Check size={12} /> {editing ? "Confirm" : "Confirmed"}
        </button>
        <button type="button" onClick={onEdit}
          className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition-colors ${
            editing
              ? "border-primary bg-secondary text-primary"
              : "border-border bg-card text-muted-foreground hover:border-primary/40"
          }`}>
          <Edit3 size={12} /> Edit
        </button>
      </div>
    </div>
  );
}

export default function OutcomeSelection({ selectedOutcome, setSelectedOutcome, selectedCohort = '', cqExposure, setCqExposure, cqPopulation, setCqPopulation, partnerLabel = 'Partner', hasEngagementCol = true, chatProps = {}, onNext, onBack }) {
  const [sel, setSel]         = useState(selectedOutcome ?? "hba1c");
  const [cohort, setCohort]   = useState(null); // { name, members[], biomarkers[] } | null

  // ── Outcomes catalog (real-only) ────────────────────────────────────────────
  // Display metadata comes from /reference/outcomes, keyed by Supabase column code.
  const { data: outcomeRows, loading: outcomesLoading } = useReference('outcomes');
  const OUTCOME_CATALOG = useMemo(() => normOutcomeCatalog(outcomeRows), [outcomeRows]);

  // ── Per-element agent-proposes → Confirm / Edit affordance ──────────────────
  // Each element starts CONFIRMED (agent proposal accepted). Clicking Edit reveals
  // the existing selector/inputs for that element; Confirm collapses back to the
  // read-only summary. Visibility-only — the underlying handlers are untouched.
  const [editing, setEditing] = useState({
    exposure: false, outcome: false, population: false,
  });
  const startEdit  = (k) => setEditing(prev => ({ ...prev, [k]: true }));
  const confirmEl  = (k) => setEditing(prev => ({ ...prev, [k]: false }));

  function togglePop(item) {
    setCqPopulation(prev => prev.includes(item) ? prev.filter(p => p !== item) : [...prev, item]);
  }

  // Fetch the live cohort once (members + biomarkers) for availability + facets.
  useEffect(() => {
    let alive = true;
    fetchCohort(selectedCohort).then((c) => { if (alive) setCohort(c); });
    return () => { alive = false; };
  }, [selectedCohort]);

  // outcomes = catalog entries whose column is present in the cohort's biomarkers.
  // Biomarker rows are wide (one row per member × timepoint): the biomarker columns
  // are object keys (e.g. `hba1c_pct`), not a `name`/`column`/`code` field — so a
  // catalog code is "present" when any biomarker row carries it with a non-null value.
  const availableOutcomes = useMemo(() => {
    const present = new Set();
    for (const b of cohort?.biomarkers ?? []) {
      for (const col of Object.keys(OUTCOME_CATALOG)) {
        if (b?.[col] != null) present.add(col);
      }
    }
    return Object.entries(OUTCOME_CATALOG)
      .filter(([col]) => present.has(col))
      .map(([, meta]) => ({
        ...meta,
        tags: [['g', 'In dataset ✓'], ...(meta.tags ?? [])],
        available: true,
      }));
  }, [OUTCOME_CATALOG, cohort]);

  const OUTCOMES = availableOutcomes;

  // If current sel is not in the loaded outcome list, fall back to first available
  const selected = OUTCOMES.find(o=>o.key===sel) ?? OUTCOMES[0];
  // Keep sel in sync if it fell back
  useEffect(() => {
    if (selected && selected.key !== sel) setSel(selected.key);
  }, [selected?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync lifted state whenever local selection changes
  useEffect(() => { setSelectedOutcome?.(sel); }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Exposure facets — derived from the cohort's engagement groups ───────────
  const EXPOSURE_OPTIONS = useMemo(() => {
    const groups = new Set((cohort?.members ?? []).map(engagementGroup).filter(Boolean));
    const labelFor = { high: 'High engagement', medium: 'Medium engagement', low: 'Low engagement' };
    return [...groups].sort().map((g) => labelFor[g] ?? g);
  }, [cohort]);

  // ── Population facets — derived from whatever member fields exist ────────────
  const POPULATION_OPTIONS = useMemo(() => {
    const members = cohort?.members ?? [];
    const distinct = (field) =>
      [...new Set(members.map((m) => m?.[field]).filter((v) => v != null && v !== ''))];
    const out = [];
    const countries = distinct('country');
    if (countries.length) out.push({ group: 'Country', items: countries.sort() });
    const ages = distinct('age');
    if (ages.length) out.push({ group: 'Age', items: ['Adults (18–65)', 'Older adults (≥65)']
      .filter((bucket) => ages.some((a) => (bucket.startsWith('Older') ? a >= 65 : a < 65))) });
    return out;
  }, [cohort]);

  // ── D1 outcome label — catalog label + follow-up window ─────────────────────
  const followupLabel = (m) => `${m.label} at 12 months`;
  const d1Label = (shortKey) => {
    const meta = Object.values(OUTCOME_CATALOG).find((o) => o.key === shortKey);
    return meta ? followupLabel(meta) : shortKey;
  };

  // Per-element agent rationale, surfaced from real agent output if provided.
  const rationale = chatProps?.rationale ?? {};

  const cqOutcome  = selected ? d1Label(selected.key) : d1Label(sel);
  const cqPopStr   = cqPopulation.length ? cqPopulation.join(" · ") : "—";

  // Loading affordance while the outcomes catalog resolves.
  if (outcomesLoading && OUTCOMES.length === 0) {
    return (
      <EmptyState
        icon={Target}
        title="Loading outcomes…"
        subtitle="Fetching the candidate outcome catalog from the Augura reference catalog."
      />
    );
  }

  // No catalog entry is present in this cohort's biomarkers — nothing to select.
  if (!outcomesLoading && OUTCOMES.length === 0) {
    return (
      <EmptyState
        icon={Target}
        title="No outcomes available for this cohort"
        subtitle="None of the reference outcome catalog's biomarkers are present in this cohort's data."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <InfoBar sources={[`${partnerLabel} dataset`,"DiGA · NICE · HAS criteria"]}>
        <strong>Definition of the causal question.</strong> Define your exposure, primary outcome, and target population. The causal question regenerates dynamically. Regulatory acceptability is mapped to DiGA, NICE, and HAS frameworks and is <strong>indicative only</strong> — validate with your regulatory affairs team.
      </InfoBar>

      {/* ── Causal question banner (live, larger) ─────────────────────────── */}
      <Card className="gap-0 rounded-xl bg-secondary/40 p-5">
        <div className="mb-3 text-[13px] font-semibold text-foreground">
          Causal question → sent to DAG agent
        </div>
        <div className="text-[17px] font-medium italic leading-[1.65] text-foreground">
          "Does <strong className="not-italic text-primary">{cqExposure}</strong> cause
          {" "}a reduction in <strong className="not-italic text-primary">{cqOutcome}</strong> in
          {" "}<strong className="not-italic text-muted-foreground">{cqPopStr}</strong>?"
        </div>
      </Card>

      {/* ── Exposure (A) | Outcome (Y) — two columns ──────────────────────── */}
      <div className="grid grid-cols-2 gap-3.5">
        {/* Exposure column */}
        <Card className="gap-0 p-5">
          <ElementHeader
            icon={Activity} label="Exposure (A)" accent="#0F6E56"
            rationale={rationale.exposure}
            editing={editing.exposure}
            onEdit={() => startEdit("exposure")}
            onConfirm={() => confirmEl("exposure")}
          />

          {/* Confirmed summary (read-only) — shown when NOT editing */}
          {!editing.exposure && (
            <div className="flex items-start gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5">
              <Check size={14} className="mt-0.5 flex-shrink-0 text-primary" />
              <div className="flex-1">
                <div className="text-[12.5px] font-medium text-foreground">{cqExposure || "—"}</div>
                <div className="mt-0.5 text-[11px] font-medium text-primary">Confirmed</div>
              </div>
            </div>
          )}

          {/* Existing selector — visibility gated behind Edit. Handlers untouched. */}
          {editing.exposure && (
          <div className="flex flex-col gap-2">
            {hasEngagementCol
              ? EXPOSURE_OPTIONS.map((o, i) => {
                  const active = cqExposure === o;
                  return (
                    <div key={o} onClick={() => setCqExposure(o)}
                      className={`flex cursor-pointer items-center justify-between rounded-lg border px-3.5 py-2.5 text-[12.5px] transition-colors ${
                        active ? "border-primary bg-secondary font-medium text-primary" : "border-border font-normal text-foreground hover:border-primary/40"
                      }`}>
                      <span>{o}</span>
                      {i === 0 && <Tag color="g">Reco</Tag>}
                    </div>
                  );
                })
              : (
                <div className="rounded-lg border border-[#EF9F27] bg-[#FAEEDA] px-3.5 py-2.5 text-[12px] leading-relaxed text-muted-foreground">
                  No engagement column detected in the uploaded dataset — define your exposure below.
                </div>
              )}
            {/* Custom exposure input — always available */}
            <div className="mt-1.5">
              <div className="mb-1.5 text-[12px] text-muted-foreground">Or enter your own</div>
              <input type="text" value={EXPOSURE_OPTIONS.includes(cqExposure) ? "" : (cqExposure || "")}
                onChange={(e) => setCqExposure(e.target.value)}
                placeholder="e.g. Top quartile platform usage"
                className="w-full rounded-lg border border-border bg-card px-3 py-2.5 text-[12.5px] text-foreground outline-none focus:border-primary/40" />
            </div>
          </div>
          )}
        </Card>

        {/* Outcome column */}
        <Card className="gap-0 p-5">
          <ElementHeader
            icon={Target} label="Outcome (Y) — Primary" accent="#0C447C"
            rationale={rationale.outcome}
            editing={editing.outcome}
            onEdit={() => startEdit("outcome")}
            onConfirm={() => confirmEl("outcome")}
          />

          {/* Confirmed summary (read-only) — shown when NOT editing */}
          {!editing.outcome && (
            <div className="flex items-start gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5">
              <Check size={14} className="mt-0.5 flex-shrink-0 text-primary" />
              <div className="flex-1">
                <div className="text-[12.5px] font-medium text-foreground">
                  {selected ? `${selected.label}${selected.unit ? ` (${selected.unit})` : ""}` : "—"}
                </div>
                <div className="mt-0.5 text-[11px] font-medium text-primary">Confirmed as primary outcome</div>
              </div>
            </div>
          )}

          {/* Existing selector — visibility gated behind Edit. Handlers untouched. */}
          {editing.outcome && (
          <>
          <div className="mb-2 text-[12px] text-muted-foreground">Click to set as primary</div>
          {/* Primary outcomes */}
          <div className="flex flex-col gap-2">
            {OUTCOMES.filter(o => o.primary).map(o => {
              const active = sel === o.key;
              return (
                <div key={o.key} onClick={()=>setSel(o.key)}
                  className={`cursor-pointer rounded-lg border px-3.5 py-3 transition-colors ${
                    active ? "border-primary bg-secondary" : "border-border hover:border-primary/40"
                  }`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className={`mb-1 text-[12.5px] font-semibold ${active ? "text-primary" : "text-foreground"}`}>
                        {o.label}{o.unit ? ` (${o.unit})` : ""}
                      </div>
                      <div className="text-[12px] leading-snug text-muted-foreground">{o.desc}</div>
                    </div>
                    {o.verdict === "g" && <Tag color="g">★ Reco</Tag>}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Secondary outcomes — promotable to primary */}
          {OUTCOMES.filter(o => !o.primary).length > 0 && (
            <>
              <div className="mb-2 mt-4 text-[12px] text-muted-foreground">
                Secondary &amp; exploratory · click to promote to primary
              </div>
              <div className="flex flex-col gap-1.5">
                {OUTCOMES.filter(o => !o.primary).map(o=>(
                  <div key={o.key} onClick={()=>setSel(o.key)}
                    className="flex cursor-pointer items-center justify-between gap-2 rounded-lg border border-border px-3.5 py-2.5 transition-colors hover:border-primary/40">
                    <div className="text-[12px] font-medium text-foreground/80">
                      {o.label}{o.unit ? ` (${o.unit})` : ""}
                    </div>
                    <Tag color="b">Promotable to primary</Tag>
                  </div>
                ))}
              </div>
            </>
          )}
          </>
          )}
        </Card>
      </div>

      {/* ── Population (P) — full width, grouped ──────────────────────────── */}
      <Card className="gap-0 p-5">
        <ElementHeader
          icon={Users} label="Population (P)" accent="#854F0B"
          rationale={rationale.population}
          editing={editing.population}
          onEdit={() => startEdit("population")}
          onConfirm={() => confirmEl("population")}
        />

        {/* Confirmed summary (read-only) — shown when NOT editing */}
        {!editing.population && (
          <div className="flex items-start gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5">
            <Check size={14} className="mt-0.5 flex-shrink-0 text-primary" />
            <div className="flex-1">
              <div className="text-[12.5px] font-medium text-foreground">{cqPopStr}</div>
              <div className="mt-0.5 text-[11px] font-medium text-primary">
                {cqPopulation.length ? "Confirmed" : "No criteria selected yet"}
              </div>
            </div>
          </div>
        )}

        {/* Existing selector — visibility gated behind Edit. Handlers untouched. */}
        {editing.population && (
        <>
        {POPULATION_OPTIONS.map(g => (
          <div key={g.group} className="mb-3">
            <div className="mb-2 text-[12px] font-medium text-foreground/80">{g.group}</div>
            <MultiPill options={g.items} selected={cqPopulation} onToggle={togglePop} />
          </div>
        ))}
        {/* Custom population criterion input */}
        <div className="mt-3">
          <div className="mb-2 text-[12px] font-medium text-foreground/80">Custom criterion</div>
          <div className="flex items-center gap-2">
            <input type="text"
              placeholder="e.g. Adults aged 50–70 with chronic kidney disease"
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.currentTarget.value.trim()) {
                  const v = e.currentTarget.value.trim();
                  if (!cqPopulation.includes(v)) togglePop(v);
                  e.currentTarget.value = "";
                }
              }}
              className="flex-1 rounded-lg border border-border bg-card px-3 py-2.5 text-[12.5px] text-foreground outline-none focus:border-primary/40" />
            <span className="flex items-center gap-1 text-[12px] text-muted-foreground"><CornerDownLeft size={13} /> to add</span>
          </div>
        </div>
        {cqPopulation.length === 0 && (
          <div className="mt-2 text-[12px] text-muted-foreground">Select one or more population criteria above</div>
        )}
        </>
        )}
      </Card>

      <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" onClick={() => onBack?.()}>
          <ArrowLeft size={15} /> Back
        </Button>
        <Button onClick={() => onNext?.()}>
          Continue <ArrowRight size={15} />
        </Button>
      </div>

      {/* ── Augura assistant — BOTTOM ─────────────────────────────────────── */}
      <InlineChatbot {...chatProps} />

    </div>
  );
}
