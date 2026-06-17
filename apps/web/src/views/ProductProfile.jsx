import { useState } from "react";
import { ChevronRight, LineChart, Hexagon, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SubTabs } from "@/cockpit/SubTabs";
import { InfoBar, Radar, IntelRow, IntelBlock } from "../ui/components";
import { EmptyState } from "@/components/EmptyState";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 1: PRODUCT PROFILE
// ─────────────────────────────────────────────────────────────────────────────
export default function ProductProfile({ e1Profile, partnerLabel = 'Partner', benchmarkMeta = null, chatProps = {}, onNext }) {
  const [sub, setSub] = useState("product");
  // Scores are 0–5 natively from the agent; legacy/dev fixtures may still be 0–100,
  // so auto-detect: anything >5 is treated as a 0–100 value and scaled down.
  const to5 = (s) => {
    const v = typeof s === "number" ? (s > 5 ? s / 20 : s) : 0;
    return Math.min(5, Math.max(0, Math.round(v * 10) / 10));
  };

  const highRisks    = e1Profile?.risk_dimensions?.filter(d=>d.score>=4).length ?? 0;
  const medRisks     = e1Profile?.risk_dimensions?.filter(d=>d.score>=2&&d.score<4).length ?? 0;
  const opps         = e1Profile?.opportunity_dimensions?.filter(d=>d.score>=4).length ?? 0;

  const riskScores = e1Profile?.risk_dimensions?.slice(0,6).map(d=>to5(d.score)) || [];
  const oppScores  = e1Profile?.opportunity_dimensions?.slice(0,6).map(d=>to5(d.score)) || [];

  // Risk/opportunity benchmark renders only from live agent output (e1Profile).
  const hasProfile = riskScores.length > 0 || oppScores.length > 0;

  const agentSummary = e1Profile?.agent_reasoning || null;

  // Top-N dimension names for the executive summaries — driven by agent output
  const topRisks = (e1Profile?.risk_dimensions || [])
    .slice().sort((a,b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0,2).map(d => d.name).filter(Boolean);
  const topOpps  = (e1Profile?.opportunity_dimensions || [])
    .slice().sort((a,b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0,2).map(d => d.name).filter(Boolean);
  return (
    <div className="flex flex-col gap-4">
      <SubTabs
        tabs={[
          { id: "product", label: "Product profile" },
          { id: "engagement", label: "Engagement profile" },
        ]}
        active={sub}
        onChange={setSub}
      />

      {sub === "product" && (
      <>
      <InfoBar sources={["MAUDE","PubMed","ClinicalTrials.gov","FDA Guidance"]}>
        <strong>Product-level profile.</strong> Benchmarked against comparable preventive health products in the Augura corpus. Scores reflect existing evidence, regulatory standing, and safety signals — independent of any planned study.
      </InfoBar>

      {/* Agent reasoning — surfaced from e1Profile.agent_reasoning */}
      {agentSummary && (
        <Card className="gap-0 rounded-xl p-5">
          <div className="mb-2.5 text-[13px] font-semibold text-foreground">
            Agent reasoning
          </div>
          <div className="text-[12.5px] leading-relaxed text-foreground/80">
            {agentSummary}
          </div>
        </Card>
      )}

      {/* How the benchmark is defined — proximity & exclusion criteria */}
      <Card className="gap-0 rounded-xl p-5">
        <div className="mb-2.5 text-[13px] font-semibold text-foreground">
          About the benchmark
        </div>
        <div className="mb-4 text-[12.5px] leading-relaxed text-foreground/80">
          The comparator set is built from products in the Augura corpus that match {partnerLabel} on
          three proximity dimensions: <strong>indication</strong> ({benchmarkMeta?.indication ?? 'same clinical domain'}),
          <strong> modality</strong> (digital therapeutic, SaMD, or consumer wellness software), and
          <strong> regulatory class</strong> (CE Class I / FDA general wellness or equivalent).
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="mb-1.5 text-[12px] font-semibold text-primary">
              Included
            </div>
            <div className="text-[12px] leading-relaxed text-muted-foreground">
              {benchmarkMeta?.included ?? 'Products matching the clinical indication, modality, and regulatory class of this product.'}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[12px] font-semibold text-[#B98900]">
              Excluded
            </div>
            <div className="text-[12px] leading-relaxed text-muted-foreground">
              {benchmarkMeta?.excluded ?? 'Products outside the clinical domain, modality, or regulatory class.'}
            </div>
          </div>
        </div>
      </Card>

      {/* Benchmarking — risk + opportunity radars, only when the profiling agent has run */}
      {hasProfile ? (
      <div>
        <div className="mb-3.5 text-[13px] font-semibold text-foreground">
          Benchmarking
        </div>
        <div className="grid grid-cols-2 items-stretch gap-4">
          <Card className="gap-0 rounded-xl p-5">
            <div className="mb-1 text-[15px] font-semibold text-foreground">Risk profile</div>
            <div className="mb-3 text-[12px] text-muted-foreground">{`Risks inherent to ${partnerLabel}.`} Higher = higher risk. /5.</div>
            <div className="flex justify-center">
              <Radar size={220}
                labels={["Safety\nsignals","Generalizability\n& equity","Implementation\nrisk","Actionability\nlinkage","Scalability\n& market","Reproducibility\n& evidence"]}
                maxVal={5}
                datasets={[
                  { data:riskScores, stroke:"#E24B4A" },
                ]}
              />
            </div>
            <div className="mb-3 rounded-lg border border-border bg-[#FBF4F4] px-3 py-2.5 text-[12px] leading-relaxed text-foreground/80">
              <strong className="text-[#A03A39]">Summary —</strong> {highRisks} high-risk and {medRisks} medium-risk
              dimensions identified by the agent.
              {topRisks.length > 0 && <> Largest exposures: <em>{topRisks.join(", ")}</em>.</>}
            </div>
            <div className="mb-2 flex items-center gap-1 text-[11px] text-muted-foreground">
              <ChevronRight size={12} /> Click any row for engine intelligence
            </div>
            <table className="w-full border-collapse">
              <thead><tr>
                {["Dimension","Score"].map(h=>(
                  <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-semibold text-muted-foreground">{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {(e1Profile?.risk_dimensions || []).slice(0,6).map((d,i) => {
                  const score = to5(typeof d.score === "number" ? d.score : 60);
                  return (
                    <IntelRow key={i} label={d.name} score={score} scoreColor="#E24B4A" max={5}>
                      <IntelBlock label="Agent finding">{d.rationale}</IntelBlock>
                    </IntelRow>
                  );
                })}
              </tbody>
            </table>
          </Card>

          <Card className="gap-0 rounded-xl p-5">
            <div className="mb-1 text-[15px] font-semibold text-foreground">Opportunity profile</div>
            <div className="mb-3 text-[12px] text-muted-foreground">Independently scored opportunities. Higher = stronger. /5.</div>
            <div className="flex justify-center">
              <Radar size={220}
                labels={["Clinical\nneed","Evidence\nstrength","Effect\nsize","Actionability\nlinkage","Reproducibility","Regulatory\npathway"]}
                maxVal={5}
                datasets={[
                  { data:oppScores, stroke:"#1D9E75" },
                ]}
              />
            </div>
            <div className="mb-3 rounded-lg border border-border bg-[#F2F8F4] px-3 py-2.5 text-[12px] leading-relaxed text-foreground/80">
              <strong className="text-[#1D6E55]">Summary —</strong> {opps} dimensions score in the upper range.
              {topOpps.length > 0 && <> Strongest pillars: <em>{topOpps.join(", ")}</em>.</>}
            </div>
            <div className="mb-2 flex items-center gap-1 text-[11px] text-muted-foreground">
              <ChevronRight size={12} /> Click any row for engine intelligence
            </div>
            <table className="w-full border-collapse">
              <thead><tr>
                {["Dimension","Score"].map(h=>(
                  <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-semibold text-muted-foreground">{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {(e1Profile?.opportunity_dimensions || []).slice(0,6).map((d,i) => {
                  const score = to5(typeof d.score === "number" ? d.score : 60);
                  return (
                    <IntelRow key={i} label={d.name} score={score} scoreColor="#1D9E75" max={5}>
                      <IntelBlock label="Agent finding">{d.rationale}</IntelBlock>
                    </IntelRow>
                  );
                })}
              </tbody>
            </table>
          </Card>

        </div>
      </div>
      ) : (
        <EmptyState
          icon={Hexagon}
          title="Product benchmark not available yet"
          subtitle="Run the profiling agent to generate the risk and opportunity benchmark for this product."
        />
      )}
      </>
      )}

      {sub === "engagement" && (
        <EmptyState
          icon={LineChart}
          title="Engagement profile not available yet"
          subtitle="No live data source wired. Engagement variable mappings, temporal trends, and baseline distribution will appear here once a dataset is connected."
        />
      )}

      <div className="mt-1 flex items-center justify-end gap-2 border-t border-border pt-4">
        <Button onClick={() => onNext?.()}>
          Continue <ArrowRight size={15} />
        </Button>
      </div>

      {/* Inline chatbot */}
      <InlineChatbot {...chatProps} />
    </div>
  );
}
