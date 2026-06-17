import { useState, useEffect, useMemo } from "react";
import { Check, X, AlertTriangle, Users, Filter, Network, Database, ArrowLeft, ArrowRight } from "lucide-react";
import { fetchCohort } from "../workspace/cohortData";
import { useReference, normOutcomeCatalog } from "@/workspace/dataClient";
import { InfoBar } from "../ui/components";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SubTabs } from "@/cockpit/SubTabs";
import { EmptyState } from "@/components/EmptyState";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 2d: DATA AVAILABILITY / VERIFICATION
// Sub-tabs mirror the navigation sketch (5a Population · 5b Outcomes ·
// 5c Intervention · 5d Missing data). The Outcomes tab renders live
// availability rows derived from the validation cohort (fetchCohort → backend).
// The Population, Intervention and Missing-data tabs have no live data source
// wired yet and render an honest empty state.
// ─────────────────────────────────────────────────────────────────────────────

// Status tones for the variable rows (availability signal palette).
const STATUS_TONE = {
  green: { wrap: "border-[#97C459] bg-secondary", text: "text-[#27500A]" },
  red:   { wrap: "border-[#F09595] bg-[#FCEBEB]",  text: "text-[#791F1F]" },
  amber: { wrap: "border-[#EF9F27] bg-[#FAEEDA]",  text: "text-[#854F0B]" },
};

// Map the data-provided status glyph to a semantic lucide icon.
const STATUS_ICON = { "✓": Check, "✗": X };
function StatusIcon({ icon, className }) {
  const Lucide = STATUS_ICON[icon] ?? AlertTriangle;
  return <Lucide size={14} className={className} strokeWidth={2.5} />;
}

function VarRow({ label, sub, pct, status, icon }) {
  const tone = STATUS_TONE[status] ?? { wrap: "border-border bg-card", text: "text-foreground" };
  return (
    <div className={`mb-2 flex items-start gap-2.5 rounded-lg border px-3 py-2.5 ${tone.wrap}`}>
      <div className={`flex w-4 flex-shrink-0 items-center justify-center pt-px ${tone.text}`}>
        <StatusIcon icon={icon} />
      </div>
      <div className="flex-1">
        <div className="mb-0.5 text-[12.5px] font-semibold text-foreground">{label}</div>
        <div className="text-[12px] leading-[1.45] text-muted-foreground">{sub}</div>
      </div>
      {pct > 0 && (
        <div className={`flex-shrink-0 font-mono text-[12px] font-semibold ${tone.text}`}>{pct}%</div>
      )}
    </div>
  );
}

// Section heading helper — sentence-case, small semibold.
function SectionLabel({ children }) {
  return <div className="mb-2 text-[13px] font-semibold text-foreground">{children}</div>;
}

export default function DataAvailability({ selectedOutcome = "hba1c", selectedCohort = "", partnerLabel = 'Partner', hasEngagementCol: _hasEngagementCol = true, chatProps = {}, onNext, onBack }) {
  const [cohort, setCohort] = useState(null);
  const [sub, setSub] = useState("population");

  useEffect(() => {
    let alive = true;
    fetchCohort(selectedCohort).then(({ members, biomarkers }) => {
      if (!alive || !members.length) return;
      const t0  = biomarkers.filter(b => b.timepoint_months === 0);
      const t12 = biomarkers.filter(b => b.timepoint_months === 12);
      const N = members.length;
      const pct = (n) => Math.round(n / N * 100);

      const ageSexN      = members.filter(m => m.age != null && m.sex != null).length;
      const bmiN         = members.filter(m => m.bmi != null).length;
      const adherenceN   = t0?.filter(b => b.adherence_pct != null).length ?? 0;
      const hba1cT0N     = t0?.filter(b => b.hba1c_pct != null).length ?? 0;
      const hba1cT12N    = t12?.filter(b => b.hba1c_pct != null).length ?? 0;
      const ldlT12N      = t12?.filter(b => b.ldl_mgdl != null).length ?? 0;
      const crpT12N      = t12?.filter(b => b.hs_crp_mgl != null).length ?? 0;

      setCohort({
        total: N,
        ageSexPct:    pct(ageSexN),
        bmiPct:       pct(bmiN),
        adherencePct: adherenceN > 0 ? pct(adherenceN) : null,
        hba1cT0Pct:   pct(hba1cT0N),
        hba1cT12Pct:  pct(hba1cT12N),
        ldlT12Pct:    pct(ldlT12N),
        crpT12Pct:    pct(crpT12N),
        hba1cT12N,
        ldlT12N,
        crpT12N,
      });
    });
    return () => { alive = false; };
  }, [selectedCohort]);

  // Outcome catalog from /reference/outcomes, re-keyed by short_key (e.g. hba1c)
  // so labels / clinical prose are sourced from the reference, never hardcoded.
  const { data: outcomeRows } = useReference('outcomes');
  const outcomeByShort = useMemo(() => {
    const cat = normOutcomeCatalog(outcomeRows);                 // keyed by column code e.g. hba1c_pct
    return Object.fromEntries(Object.values(cat).map((o) => [o.key, o]));  // re-key by short_key e.g. hba1c
  }, [outcomeRows]);

  // Catalog-derived caveat for an outcome short_key (first regulatory tag → description → none).
  const caveatFor = (k) => outcomeByShort[k]?.tags?.[0]?.[1] ?? outcomeByShort[k]?.desc ?? "";

  // ── Live availability rows driven by the selected outcome + cohort ─────────
  const PRIMARY_OUTCOME_ROW = {
    hba1c: { label:`${outcomeByShort.hba1c?.label ?? "hba1c"} at 12 months (primary outcome)`, icon:"✓", status:"green",
      pct: cohort?.hba1cT12Pct ?? 0,
      sub: `hba1c_t12 · N=${cohort?.hba1cT12N ?? "…"} eligible · ${caveatFor("hba1c")}` },
    ldl:   { label:`${outcomeByShort.ldl?.label ?? "ldl"} at 12 months (primary outcome)`, icon:"✓", status:"green",
      pct: cohort?.ldlT12Pct ?? 0,
      sub: `ldl_t12 · N=${cohort?.ldlT12N ?? "…"} eligible · ${caveatFor("ldl")}` },
    crp:   { label:`${outcomeByShort.crp?.label ?? "crp"} at 12 months (primary outcome)`, icon:"✓", status:"green",
      pct: cohort?.crpT12Pct ?? 0,
      sub: `hs_crp_t12 · N=${cohort?.crpT12N ?? "…"} eligible · ${caveatFor("crp")}` },
  };

  const DYNAMIC_SECONDARIES = {
    hba1c: [
      { label:`${outcomeByShort.ldl?.label ?? "ldl"} at 12M`,   icon:"✓", status:"green", pct: cohort?.ldlT12Pct   ?? 0, sub:`ldl_t12 · N=${cohort?.ldlT12N ?? "…"} · ${caveatFor("ldl")}` },
      { label:`${outcomeByShort.crp?.label ?? "crp"} at 12M`,   icon:"✓", status:"green", pct: cohort?.crpT12Pct   ?? 0, sub:`hs_crp_t12 · N=${cohort?.crpT12N ?? "…"} · ${caveatFor("crp")}` },
    ],
    ldl: [
      { label:`${outcomeByShort.hba1c?.label ?? "hba1c"} at 12M`, icon:"✓", status:"green", pct: cohort?.hba1cT12Pct ?? 0, sub:`hba1c_t12 · N=${cohort?.hba1cT12N ?? "…"} · ${caveatFor("hba1c")}` },
      { label:`${outcomeByShort.crp?.label ?? "crp"} at 12M`,   icon:"✓", status:"green", pct: cohort?.crpT12Pct   ?? 0, sub:`hs_crp_t12 · N=${cohort?.crpT12N ?? "…"} · ${caveatFor("crp")}` },
    ],
    crp: [
      { label:`${outcomeByShort.hba1c?.label ?? "hba1c"} at 12M`, icon:"✓", status:"green", pct: cohort?.hba1cT12Pct ?? 0, sub:`hba1c_t12 · N=${cohort?.hba1cT12N ?? "…"} · ${caveatFor("hba1c")}` },
      { label:`${outcomeByShort.ldl?.label ?? "ldl"} at 12M`,   icon:"✓", status:"green", pct: cohort?.ldlT12Pct   ?? 0, sub:`ldl_t12 · N=${cohort?.ldlT12N ?? "…"} · ${caveatFor("ldl")}` },
    ],
  };

  const primaryRow     = PRIMARY_OUTCOME_ROW[selectedOutcome] ?? PRIMARY_OUTCOME_ROW.hba1c;
  const secondaryRows  = DYNAMIC_SECONDARIES[selectedOutcome]  ?? DYNAMIC_SECONDARIES.hba1c;
  const eligibleN      = selectedOutcome === "ldl" ? cohort?.ldlT12N : selectedOutcome === "crp" ? cohort?.crpT12N : cohort?.hba1cT12N;

  return (
    <div className="flex flex-col gap-4">
      <InfoBar sources={[`${partnerLabel} dataset`, cohort ? `N=${cohort.total} validation cohort` : "N=… validation cohort"]}>
        <strong>Verification.</strong> Augura cross-references every element of the study design against the {partnerLabel} dataset ({cohort ? `N=${cohort.total} validation cohort` : "validation cohort"}) — population eligibility, outcome and intervention variables, and the missing-data strategy — before any outcome data are examined.
      </InfoBar>

      <SubTabs
        tabs={[
          { id: "population",   label: "Population",   icon: <Users size={14} /> },
          { id: "outcomes",     label: "Outcomes" },
          { id: "intervention", label: "Intervention" },
          { id: "missing",      label: "Missing data" },
        ]}
        active={sub}
        onChange={setSub}
      />

      {/* ════════════════════════ 5a — POPULATION ════════════════════════ */}
      {sub === "population" && (
        <Card className="rounded-xl border p-0">
          <EmptyState
            icon={Filter}
            title="Population eligibility not available yet"
            subtitle="No live data source wired for the eligibility cascade and DAG-to-dataset alignment. This view will populate once the population verification pipeline is connected."
          />
        </Card>
      )}

      {/* ════════════════════════ 5b — OUTCOMES (live availability) ════════════════════════ */}
      {sub === "outcomes" && (
        <div className="flex flex-col gap-4">
          {/* KPI summary — cohort-derived */}
          <div className="grid grid-cols-2 gap-4">
            <Card className="gap-0 rounded-xl p-4">
              <div className="font-mono text-[22px] font-semibold text-primary">
                {eligibleN ? `${eligibleN}` : cohort ? `${cohort.total}` : "…"}
              </div>
              <div className="mt-1 text-[12px] text-muted-foreground">With primary outcome at T12</div>
            </Card>
            <Card className="gap-0 rounded-xl p-4">
              <div className="font-mono text-[22px] font-semibold text-primary">
                {cohort ? `${cohort.total}` : "…"}
              </div>
              <div className="mt-1 text-[12px] text-muted-foreground">Validation cohort size</div>
            </Card>
          </div>

          {/* Variable rows — primary + secondary outcomes (cohort-derived) */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <SectionLabel>Primary outcome</SectionLabel>
              <VarRow {...primaryRow} />
            </div>
            <div>
              <SectionLabel>Secondary outcomes</SectionLabel>
              {secondaryRows.map(v=><VarRow key={v.label} {...v} />)}
            </div>
          </div>
        </div>
      )}

      {/* ════════════════════════ 5c — INTERVENTION ════════════════════════ */}
      {sub === "intervention" && (
        <Card className="rounded-xl border p-0">
          <EmptyState
            icon={Database}
            title="Intervention variables not available yet"
            subtitle="No live data source wired for the engagement-score component verification. This view will populate once the intervention verification pipeline is connected."
          />
        </Card>
      )}

      {/* ════════════════════════ 5d — MISSING DATA ════════════════════════ */}
      {sub === "missing" && (
        <Card className="rounded-xl border p-0">
          <EmptyState
            icon={Network}
            title="Missing-data analysis not available yet"
            subtitle="No live data source wired for per-variable missingness and the imputation strategy. This view will populate once the missing-data pipeline is connected."
          />
        </Card>
      )}

      <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" onClick={() => onBack?.()}>
          <ArrowLeft size={15} /> Back
        </Button>
        <Button onClick={() => onNext?.()}>
          Continue <ArrowRight size={15} />
        </Button>
      </div>

      <InlineChatbot {...chatProps} />

    </div>
  );
}
