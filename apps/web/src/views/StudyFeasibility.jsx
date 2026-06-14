import { useState, useEffect } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { supabase } from "../supabase";
import { TENANT_ID } from "../config";
import { Card, InfoBar, Pill, Radar, IntelRow, IntelBlock, Tag, Btn } from "../ui/components";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 2: STUDY FEASIBILITY
// ─────────────────────────────────────────────────────────────────────────────
export default function StudyFeasibility({ onNext, onBack, product, users, outcome, selectedCohort = "", partnerLabel = 'Partner' }) {
  const [cohort, setCohort] = useState(null); // live stats from validation tables

  useEffect(() => {
    const url = import.meta.env.VITE_SUPABASE_URL;
    const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
    if (!url || !key) return;
    const client = supabase;

    console.log("[Feasibility] TENANT_ID:", TENANT_ID);
    console.log("[Feasibility] VITE_SUPABASE_URL:", url);

    Promise.all([
      client.from("validation_members")
        .select("engagement_group, country")
        .eq("tenant_id", TENANT_ID)
        .eq("cohort_name", selectedCohort),
      client.from("validation_biomarkers")
        .select("member_id, timepoint_months")
        .eq("tenant_id", TENANT_ID)
        .eq("cohort_name", selectedCohort),
    ]).then(([{ data: members, error: e1 }, { data: bio, error: e2 }]) => {
      console.log("[Feasibility] members:", members?.length, "| error:", e1);
      console.log("[Feasibility] bio:", bio?.length, "| error:", e2);
      if (!members?.length) return;

      const total     = members.length;
      const highN     = members.filter(m => m.engagement_group === "High").length;
      const countries = [...new Set(members.map(m => m.country))].sort();
      const t12count  = new Set(bio?.filter(b => b.timepoint_months === 12).map(b => b.member_id)).size;
      const dropout12 = Math.round((1 - t12count / total) * 100);

      setCohort({ total, highN, highPct: Math.round(highN / total * 100), countries, dropout12, source: selectedCohort });
    });
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <InfoBar sources={["ClinicalTrials.gov","PubMed","FDA Guidance"]}>
        <strong>Study feasibility profile.</strong> Scores reflect the practical and methodological
        feasibility of running an impact study — independent of {partnerLabel}'s product merits. Benchmark: comparable trials in corpus.
      </InfoBar>

      <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border bg-[#f1efe8] px-4 py-2.5">
        <span className="text-[12px] font-semibold text-foreground">Score from</span>
        {[["KB","Knowledge base"],["L",`${partnerLabel} data`],["KB+L","Both combined"]].map(([t,l])=>(
          <div key={t} className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
            <Pill type={t}>{t}</Pill> {l}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <div className="mb-1 text-[15px] font-semibold text-foreground">Study feasibility risk</div>
          <div className="mb-4 text-[12.5px] text-muted-foreground">Scored from ClinicalTrials.gov and PubMed benchmarks. Higher = higher risk. /5.</div>
          <div className="flex justify-center">
            <Radar size={220}
              labels={["Feasibility","Dropout /\nretention","Confounding\ncontrol","Internal\nvalidity","Timeline","External\nvalidity"]}
              maxVal={5}
              datasets={[
                { data:[2,3,2,3,3,3], stroke:"#378ADD" },
                { data:[3,3,3,3,3,3], stroke:"#AAA89E", dash:true },
              ]}
            />
          </div>
          <div className="mt-3 mb-4 flex justify-center gap-4">
            {[["#378ADD","Study risk"],["#AAA89E","Benchmark"]].map(([c,l])=>(
              <div key={l} className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                <div className="h-[3px] w-[18px] rounded-sm" style={{ background:c }} />{l}
              </div>
            ))}
          </div>
          <table className="w-full border-collapse">
            <thead><tr>{["Dimension","Score","Δ benchmark","Source"].map(h=>(
              <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-semibold text-muted-foreground">{h}</th>
            ))}</tr></thead>
            <tbody>
              <IntelRow label="Feasibility" score={2} scoreColor="#378ADD" delta="-1↓" deltaDir="better" source="KB+L">
                <IntelBlock label="Context">Retrospective observational design — no new recruitment required. Full cohort already available with 12-month follow-up. Feasibility risk relates to data completeness.</IntelBlock>
                <IntelBlock label="Completeness"><Tag color="g">T12 complete: {cohort ? `${100 - cohort.dropout12}%` : "loading…"}</Tag> — PubMed benchmark for comparable digital health retrospective studies: 75–85% completeness.</IntelBlock>
              </IntelRow>
              <IntelRow label="Dropout / retention risk" score={3} scoreColor="#378ADD" delta="On par" deltaDir="same" source="KB+L">
                <IntelBlock label="ClinicalTrials.gov benchmark">Median dropout at 12 months across comparable digital health trials: 22% (interquartile range 15–30%). Source: 8 comparable CT.gov trials in Augura corpus.</IntelBlock>
                <IntelBlock label="Cohort observed">
                  {cohort
                    ? <><Tag color="b">Observed dropout at T12: {cohort.dropout12}%</Tag> — on par with benchmark. MCAR/MAR sensitivity analysis required per HAS RWE guidelines.</>
                    : "Loading cohort data…"}
                </IntelBlock>
              </IntelRow>
              <IntelRow label="Confounding control" score={2} scoreColor="#378ADD" delta="-1↓" deltaDir="better" source="KB+L">
                <IntelBlock label="PubMed evidence">LME + IPW adjustment set controls for measured confounders (age, sex, country, baseline HbA1c). PubMed review of comparable observational studies: residual confounding from concurrent employer wellness initiatives is the primary uncontrolled threat.</IntelBlock>
                <IntelBlock label="Note">Adjustment set formally defined in the Causal Model (DAG) step — score will update once D3 is confirmed.</IntelBlock>
              </IntelRow>
              <IntelRow label="Internal validity" score={3} scoreColor="#378ADD" delta="On par" deltaDir="same" source="KB">
                <IntelBlock label="PubMed benchmark">Retrospective cohort designs in comparable digital health studies have moderate internal validity risk — selection bias (self-selected engagers) and temporal confounding are the main threats. PubMed meta-analyses show retrospective digital health studies have 30–40% higher bias risk vs prospective designs.</IntelBlock>
                <IntelBlock label="Mitigation">DiD estimator controls for time-stable confounding. Sensitivity analysis across estimators (LME, IPW, TMLE) in E2 simulation.</IntelBlock>
              </IntelRow>
              <IntelRow label="Timeline" score={3} scoreColor="#378ADD" delta="On par" deltaDir="same" source="KB">
                <IntelBlock label="ClinicalTrials.gov data">Based on start/completion dates of 8 comparable retrospective digital health studies in CT.gov corpus: median analysis timeline 3–5 months. Note: CT.gov completion dates not always available for retrospective studies — estimate based on available records only.</IntelBlock>
                <IntelBlock label="Estimate">Retrospective analysis: 3–4 months. Budget: €80k–150k. Prospective extension: +12 months, +€300k–500k.</IntelBlock>
              </IntelRow>
              <IntelRow label="External validity" score={3} scoreColor="#378ADD" delta="On par" deltaDir="same" source="KB+L">
                <IntelBlock label="PubMed benchmark">External validity risk in digital health cohorts is moderate — populations are typically urban, high-SES, and self-selected. PubMed review: 15–25% effect size heterogeneity across European sites in comparable studies.</IntelBlock>
                <IntelBlock label="Cohort coverage">{cohort ? <><Tag color="b">{cohort.countries.join(" · ")}</Tag> — multi-country coverage strengthens generalisability vs single-site studies.</> : "Loading cohort data…"}</IntelBlock>
              </IntelRow>
            </tbody>
          </table>
        </Card>

        <Card>
          <div className="mb-1 text-[15px] font-semibold text-foreground">Study opportunity profile</div>
          <div className="mb-4 text-[12.5px] text-muted-foreground">What makes this study feasible and valuable. Higher = stronger.</div>
          <div className="flex justify-center">
            <Radar size={220}
              labels={["Design\noptionality","Data\ninfrastructure","Endpoint\nmeasure","Causal\ndecomp","Regulatory\nalignment","Multi-site\ngeneralise"]}
              datasets={[
                { data:[4,5,4,4,3,3], stroke:"#1D9E75" },
                { data:[3,5,5,3,3,2], stroke:"#9FE1CB" },
                { data:[3,3,2.5,2,3,3.5], stroke:"#AAA89E", dash:true },
              ]}
            />
          </div>
          <div className="mt-3 mb-4 flex justify-center gap-4">
            {[["#1D9E75","Strength"],["#9FE1CB","Feasibility"],["#AAA89E","Benchmark"]].map(([c,l])=>(
              <div key={l} className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                <div className="h-[3px] w-[18px] rounded-sm" style={{ background:c }} />{l}
              </div>
            ))}
          </div>
          <table className="w-full border-collapse">
            <thead><tr>{["Dimension","Score","Δ benchmark","Source"].map(h=>(
              <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-semibold text-muted-foreground">{h}</th>
            ))}</tr></thead>
            <tbody>
              <IntelRow label="Design optionality" score={4} scoreColor="#1D9E75" delta="+1↑" deltaDir="better" source="KB+L">
                <IntelBlock label="Viable designs"><Tag color="g">Retrospective engagement cohort — 91%</Tag><Tag color="g">Pre/Post cohort — 85%</Tag><Tag color="a">External matched — 62%</Tag></IntelBlock>
              </IntelRow>
              <IntelRow label="Data infrastructure" score={5} scoreColor="#1D9E75" delta="+2↑" deltaDir="better" source="L">
                <IntelBlock label="Ready now"><Tag color="g">Longitudinal biomarkers</Tag><Tag color="g">Engagement logs</Tag><Tag color="g">Wearable data</Tag> — Exceeds most comparable products in the 701-study evidence base at equivalent stage.</IntelBlock>
                {cohort && (
                  <IntelBlock label="Cohort">
                    <Tag color="g">N={cohort.total} members</Tag>
                    <Tag color="g">High engagement: {cohort.highPct}% (n={cohort.highN})</Tag>
                    <Tag color="b">{cohort.countries.join(" · ")}</Tag>
                    <span className="ml-1 text-[11px] text-muted-foreground"><span className="text-muted-foreground/80">Source:</span> <span className="font-mono">{cohort.source}</span></span>
                  </IntelBlock>
                )}
              </IntelRow>
              <IntelRow label="Endpoint measurability" score={4} scoreColor="#1D9E75" delta="+1.5↑" deltaDir="better" source="KB+L" preliminary>
                <IntelBlock label="Note">Score is provisional — primary endpoint not yet confirmed. Will update after Outcome Selection.</IntelBlock>
                <IntelBlock label="Ranked"><Tag color="g">1. Metabolic composite — 21 trials</Tag><Tag color="a">2. Absenteeism — payer ROI, 4 HTA submissions</Tag></IntelBlock>
              </IntelRow>
              <IntelRow label="Causal decomposition" score={4} scoreColor="#1D9E75" delta="+1↑" deltaDir="better" source="KB+L" preliminary>
                <IntelBlock label="Note">Causal decomposition capacity will be assessed in the Causal Model (DAG). Score shown is a structural estimate based on data availability.</IntelBlock>
                <IntelBlock label="Precedent">In 4 of 6 comparable mediation analyses, indirect effect via behaviour change was 60–75% of total biomarker improvement.</IntelBlock>
              </IntelRow>
              <IntelRow label="Regulatory alignment" score={3} scoreColor="#1D9E75" delta="On par" deltaDir="same" source="KB" preliminary>
                <IntelBlock label="Note">Regulatory alignment score will be refined after Study Design is confirmed. Current score assumes retrospective cohort design.</IntelBlock>
                <IntelBlock label="Alignment">Retrospective design with metabolic composite primary endpoint aligns with HAS real-world evidence methodology.</IntelBlock>
              </IntelRow>
              <IntelRow label="Multi-site generalisability" score={3} scoreColor="#1D9E75" delta="On par" deltaDir="same" source="KB+L">
                <IntelBlock label="Heterogeneity">15–25% effect size heterogeneity across European sites in comparable studies. Pre-specify country as stratification variable.</IntelBlock>
              </IntelRow>
            </tbody>
          </table>
        </Card>
      </div>

      {/* Inline chatbot */}
      <InlineChatbot
        context={`You are the Augura evidence generation assistant for ${partnerLabel} (preventive health AI, France/UK/Ireland/Portugal, biomarker testing + lifestyle coaching targeting HAS and Assurance Maladie).

CURRENT USER CHARACTERISTICS:
${users}

CURRENT PRODUCT CHARACTERISTICS:
${product}

CURRENT OUTCOMES OF INTEREST:
${outcome}

STUDY FEASIBILITY CONTEXT:
- Study feasibility risk: Feasibility 2/5, Dropout/retention 3/5, Confounding control 2/5, Internal validity 3/5, Timeline 3/5, External validity 3/5
- Study opportunity profile: Design optionality 4/5, Data infrastructure 5/5, Endpoint measurability 4/5, Causal decomposition 4/5, Regulatory alignment 3/5, Multi-site generalisability 3/5
- Viable designs: Retrospective engagement cohort (91%), Pre/Post cohort (85%), External matched cohort (62%)
- N=${cohort ? cohort.total : 824} eligible users in prediabetes cohort (HbA1c 5.7-6.4)${cohort ? ` · ${cohort.highPct}% high engagers · countries: ${cohort.countries.join(", ")}` : ""}
- Timeline for retrospective analysis: 3-4 months, budget €80k-150k
- Data sources: PubMed + ClinicalTrials.gov (701 studies in comparable evidence base, 286 with prospective/RCT design), MAUDE, FDA Guidance
- All required mediators available in ${partnerLabel} data: recommendation adherence, repeat test completion, wearable activity

IMPORTANT: Always base your answers on the current user characteristics above — do not refer to outdated default values.
Answer concisely under 130 words. Reference ${partnerLabel} data and corpus. Be direct and practical.`}
        suggestions={[
          "What's the main recruitment risk?",
          "How do we control for confounding?",
          "Can we run this in 3 months?",
          "Why is data infrastructure scored 5/5?",
        ]}
      />

      <div className="flex gap-2">
        <Btn onClick={onBack}><ArrowLeft size={14} /> Back to product profile</Btn>
        <Btn primary onClick={onNext}>Proceed to study type <ArrowRight size={14} /></Btn>
      </div>
    </div>
  );
}
