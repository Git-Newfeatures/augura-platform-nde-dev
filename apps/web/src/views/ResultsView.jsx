import { Hexagon, BarChart3, ArrowLeft, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/EmptyState";
import { DagRenderer } from "./CausalModel";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 8: RESULTS  (after E2 Simulation)
//
// Real-only: this view surfaces the validated estimate carried in `simResults`
// (effect / CI / power for the locked estimator) plus the live causal DAG from
// `dagCache`. When no analysis has been run yet, it renders an honest empty
// state instead of fabricated study results.
// ─────────────────────────────────────────────────────────────────────────────

export default function ResultsView({ simResults, dagCache, partnerLabel = 'Partner', onNext, onBack }) {
  const simEst    = simResults?.result;
  const simN      = simResults?.n ?? null;
  const simEffect = simEst?.effect ?? null;
  const simCILo   = simEst?.ci?.[0] ?? null;
  const simCIHi   = simEst?.ci?.[1] ?? null;
  const simPower  = simEst?.power ?? null;
  const simLabel  = simResults?.estimatorLabel ?? null;
  const isLive    = simEffect != null;

  const pLabel = simPower != null ? (simPower >= 99.9 ? "<0.001" : "<0.05") : null;

  const KPI = ({ label, value, sub, accent, wide }) => (
    <Card className={`gap-0 rounded-xl p-4 ${wide ? "flex-[1.4_1_0]" : "flex-1"} ${accent ? "border-[#5DCAA5] bg-secondary" : "border-border bg-card"}`}>
      <div className="mb-1.5 text-[12px] font-medium text-muted-foreground">{label}</div>
      <div className={`font-semibold leading-[1.1] ${accent ? "text-[28px] text-primary" : "text-[22px] text-foreground"}`}>{value}</div>
      {sub && <div className="mt-1 text-[12px] text-muted-foreground">{sub}</div>}
    </Card>
  );

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-5">

      {!isLive ? (
        <EmptyState
          icon={BarChart3}
          title="No results yet"
          subtitle="Results will appear here once a real analysis has been run. Complete the Simulation step to generate a validated estimate for this study."
        />
      ) : (
        <>
          {/* KPI strip */}
          <div className="flex gap-4">
            <KPI label="Sample" value={simN != null ? simN.toLocaleString() : "—"} sub="eligible users" />
            <KPI
              label="Effect"
              value={simEffect.toFixed(2)}
              sub={simCILo != null && simCIHi != null ? `[${simCILo.toFixed(2)}, ${simCIHi.toFixed(2)}]` : null}
              accent
            />
            {simPower != null && (
              <KPI label="Power" value={`${simPower}%`} sub={simLabel ? `${simLabel} estimator` : null} />
            )}
          </div>

          {/* Primary result */}
          <Card className="gap-0 rounded-xl border-border bg-card p-5">
            <div className="mb-1 text-[13px] font-semibold text-foreground">Primary result</div>
            <div className="mb-3 text-[12px] text-muted-foreground">
              {simLabel ? `${simLabel} · ` : ""}High vs Low engagement · estimate for the {partnerLabel} cohort
            </div>
            <div className="mb-1 flex items-baseline gap-2">
              <span className="text-[40px] font-bold tracking-[-1px] text-primary">{simEffect.toFixed(2)}</span>
              <span className="text-[13px] text-muted-foreground">effect size</span>
            </div>
            <div className="text-[12.5px] text-muted-foreground">
              {simCILo != null && simCIHi != null ? `95% CI [${simCILo.toFixed(2)}, ${simCIHi.toFixed(2)}]` : "95% CI —"}
              {pLabel ? ` · p ${pLabel}` : ""}
            </div>
          </Card>
        </>
      )}

      {/* Causal DAG — live, derived from dagCache (or empty state) */}
      <Card className="gap-0 rounded-xl border-border bg-card p-5">
        <div className="mb-0.5 text-[13px] font-semibold text-foreground">Causal DAG</div>
        <div className="mb-3 text-[12px] text-muted-foreground">
          {dagCache?.nodes?.length
            ? `${dagCache.nodes.length} nodes · built by Augura DAG agent`
            : "Complete the Causal Model step to generate the diagram from your data"}
        </div>
        {dagCache?.nodes?.length
          ? <DagRenderer nodes={dagCache.nodes} edges={dagCache.edges ?? []} />
          : (
            <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg bg-muted/40 px-4 text-center text-[12px] text-muted-foreground">
              <Hexagon size={22} className="text-muted-foreground/50" />
              No DAG available — complete the Causal Model step to generate the diagram from your data
            </div>
          )
        }
      </Card>

      <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" onClick={() => onBack?.()}>
          <ArrowLeft size={15} /> Back
        </Button>
        <Button onClick={() => onNext?.()}>
          Sensitivity analysis <ArrowRight size={15} />
        </Button>
      </div>

    </div>
  );
}
