import { useState } from "react";
import { ArrowLeft, ArrowRight, FolderOpen, TrendingUp, Link2, Microscope, ClipboardList, BarChart3, Scale } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoBar, Tag } from "../ui/components";
import InlineChatbot from "../components/InlineChatbot";

// Map study-design data keys → lucide icons (presentational only)
const DESIGN_ICON = {
  retro_cohort: FolderOpen,
  pre_post: TrendingUp,
  external_matched: Link2,
  mediation: Microscope,
};

function getStudyDesigns(partnerLabel) {
  return [
    {
      id: "retro_cohort",
      name: "Retrospective Engagement Cohort",
      icon: "📂",
      desc: "Stratify existing users by engagement level (HIGH vs REST). Measure biomarker change between groups. Fast, no new data required.",
      tags: [["g",`${partnerLabel} data available`], ["b","DiGA / HAS eligible"], ["a","Observational — confounding risk"]],
      color: "#0F6E56",
      estimands: ["ATE", "ATT"],
    },
    {
      id: "pre_post",
      name: "Pre / Post Cohort",
      icon: "📈",
      desc: `Compare each user's biomarkers before and after joining ${partnerLabel}. No separate control group — uses within-person change.`,
      tags: [["g","Simple"], ["b","No external data"], ["a","No control group — regression to mean risk"]],
      color: "#0C447C",
      estimands: ["ATE"],
    },
    {
      id: "external_matched",
      name: "External Matched Cohort",
      icon: "🔗",
      desc: `Match ${partnerLabel} users to external non-users (e.g. Constances cohort). Stronger causal interpretation than internal comparison.`,
      tags: [["b","Stronger causal claim"], ["a","Requires external dataset"], ["a","Matching complexity"]],
      color: "#633806",
      estimands: ["ATE", "ATT"],
    },
    {
      id: "mediation",
      name: "Causal Mediation",
      icon: "🔬",
      desc: "Decompose total effect into direct (platform → HbA1c) and indirect (via behaviour change). Different causal question — cannot be combined with total-effect estimators.",
      tags: [["b","Mechanism analysis"], ["b","Scientific differentiator"], ["a","Stronger assumptions required"]],
      color: "#2E9EAD",
      estimands: ["MEDIATION"],
    },
  ];
}

const ESTIMAND_OPTS = [
  {
    key: "ATE",
    name: "ATE — Average Treatment Effect",
    desc: "What would the effect of the intervention be if applied to the entire eligible population? Population-level causal effect — the default starting point for most causal questions.",
    regulatory: "Conservative, broadly accepted across payer submissions (HAS, NICE DSP, DiGA).",
    recommended: true,
  },
  {
    key: "ATT",
    name: "ATT — Average Treatment effect on the Treated",
    desc: "What is the effect of the intervention specifically for users who actually received or engaged with it? Answers: 'did it work for the people who used it?'",
    regulatory: "Preferred when treated and untreated populations differ structurally — common in real-world evidence.",
    recommended: false,
  },
  {
    key: "CATE",
    name: "CATE — Conditional ATE",
    desc: "The causal effect as a function of individual or subgroup covariates — 'which users benefit most?' Enables personalised evidence claims. Requires larger N and careful regularisation.",
    regulatory: "Heterogeneous effects — supports subgroup and personalised claims; estimated with Causal Forest / GRF, BART, or meta-learners.",
    recommended: false,
    tag: "Heterogeneous effects",
  },
  {
    key: "MEDIATION",
    name: "Mediation Analysis — Direct, Indirect, Total Effects",
    desc: "Decomposes the total effect into the direct effect (intervention → outcome bypassing the mediator) and the indirect effect (intervention → mediator → outcome). Use when the mechanism of action matters, not just the headline effect.",
    regulatory: "Mechanism evidence — supports HTA narratives but typically paired with ATE/ATT as the primary estimand.",
    recommended: false,
  },
];

export default function StudyType({ partnerLabel = 'Partner', chatProps = {}, onNext, onBack }) {
  const [approach, setApproach] = useState("retro");
  const [design, setDesign] = useState("retro_cohort");
  const [estimand, setEstimand] = useState("ATE");

  const retro = approach === "retro";
  const isMediation = design === "mediation";
  const STUDY_DESIGNS = getStudyDesigns(partnerLabel);

  function selectDesign(id) {
    setDesign(id);
    if (id === "mediation") {
      setEstimand("MEDIATION");
    } else {
      setEstimand("ATE");
    }
  }

  const designLabel  = STUDY_DESIGNS.find(d => d.id === design)?.name ?? "—";

  return (
    <div className="flex flex-col gap-5">
      <InfoBar sources={[`${partnerLabel} dataset`,"Augura corpus"]}>
        <strong>Study design.</strong> Configure your study in three steps — study type, design family, and estimand. Your configuration summary updates on the right.
      </InfoBar>

      {/* Two-column shell: main content (steps) | sticky feasibility sidebar */}
      <div className="grid grid-cols-[1fr_320px] items-start gap-5">
        <div className="flex flex-col gap-5">

          {/* ── Study approach ─────────────────────────────────────────────── */}
          <div>
            <div className="mb-3 text-[13px] font-semibold text-foreground">
              Step 1 — Choose your study approach
            </div>
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setApproach("retro")}
                className={`rounded-xl border p-5 text-left transition-colors ${
                  retro ? "border-primary bg-secondary" : "border-border hover:border-primary/40"
                }`}
              >
                <FolderOpen size={20} className={`mb-2 ${retro ? "text-primary" : "text-muted-foreground"}`} />
                <div className={`mb-1.5 text-[14px] font-semibold ${retro ? "text-primary" : "text-foreground"}`}>Retrospective study</div>
                <div className="mb-3 text-[12px] leading-relaxed text-muted-foreground">
                  Use existing {partnerLabel} data already collected. Fast, low-cost, and immediately actionable. Best starting point for generating first-in-class impact evidence and regulatory submissions.
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Tag color="g">✓ {partnerLabel} data available</Tag>
                  <Tag color="b">DiGA-eligible</Tag>
                  <Tag color="a">Observational · confounding risk</Tag>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setApproach("prosp")}
                className={`rounded-xl border p-5 text-left transition-colors ${
                  !retro ? "border-[#85B7EB] bg-[#E6F1FB]" : "border-border hover:border-primary/40"
                }`}
              >
                <Microscope size={20} className={`mb-2 ${!retro ? "text-[#3172B0]" : "text-muted-foreground"}`} />
                <div className={`mb-1.5 text-[14px] font-semibold ${!retro ? "text-[#3172B0]" : "text-foreground"}`}>Prospective study</div>
                <div className="mb-3 text-[12px] leading-relaxed text-muted-foreground">
                  Design and run a new study collecting data going forward. Stronger causal inference, required for NICE DSP full listing and some payer submissions. Requires expert study design support.
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Tag color="b">Stronger causal claim</Tag>
                  <Tag color="b">NICE DSP · RCT-grade</Tag>
                  <Tag color="r">Expert team required</Tag>
                </div>
              </button>
            </div>

            {!retro && (
              <div className="mt-4 rounded-xl border border-[#85B7EB] bg-[#E6F1FB] p-4">
                <div className="mb-1.5 text-[13px] font-semibold text-[#3172B0]">
                  Prospective study — Expert consultation required
                </div>
                <div className="mb-3 text-[12px] leading-relaxed text-foreground/80">
                  A prospective study requires a full protocol design, ethics submission, and site coordination.
                </div>
                <div className="grid grid-cols-3 gap-2.5">
                  {[
                    [ClipboardList, "Protocol design","Randomisation, blinding, arm definition, endpoints"],
                    [BarChart3, "Power & sample size","Monte Carlo simulation, ICC estimation, dropout modelling"],
                    [Scale, "Regulatory strategy","NICE DSP, DiGA, FDA — aligned submission plan"],
                  ].map(([Icon,t,d])=>(
                    <div key={t} className="rounded-lg bg-card p-3 text-[12px]">
                      <div className="mb-1 flex items-center gap-1.5 font-semibold text-[#3172B0]"><Icon size={14} /> {t}</div>
                      <div className="leading-snug text-muted-foreground">{d}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Step 2 — Study design ──────────────────────────────────────── */}
          {retro && (
            <div>
              <div className="mb-3 text-[13px] font-semibold text-foreground">
                Step 2 — Select study design
              </div>
              <div className="grid grid-cols-4 gap-3">
                {STUDY_DESIGNS.map(d => {
                  const active = design === d.id;
                  const DesignIcon = DESIGN_ICON[d.id];
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => selectDesign(d.id)}
                      className={`rounded-xl border p-4 text-left transition-colors ${
                        active ? "" : "border-border hover:border-primary/40"
                      }`}
                      style={active ? { borderColor: d.color, background: `${d.color}0D` } : undefined}
                    >
                      {DesignIcon && (
                        <DesignIcon size={18} className={active ? "" : "text-muted-foreground"} style={active ? { color: d.color } : undefined} />
                      )}
                      <div
                        className={`mb-1.5 mt-2 text-[12.5px] font-semibold ${active ? "" : "text-foreground"}`}
                        style={active ? { color: d.color } : undefined}
                      >
                        {d.name}
                      </div>
                      <div className="mb-2.5 text-[12px] leading-relaxed text-muted-foreground">
                        {d.desc}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {d.tags.map(([c,t]) => <Tag key={t} color={c}>{t}</Tag>)}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Step 3 — Estimand ─────────────────────────────────────────── */}
          {retro && (
            <div>
              <div className="mb-3 text-[13px] font-semibold text-foreground">
                Step 3 — Select estimand
              </div>
              <div className="grid grid-cols-3 gap-3">
                {ESTIMAND_OPTS
                  .filter(e => isMediation ? e.key === "MEDIATION" : e.key !== "MEDIATION")
                  .map(e => {
                    const active = estimand === e.key;
                    return (
                      <button
                        key={e.key}
                        type="button"
                        onClick={() => !isMediation && setEstimand(e.key)}
                        className={`rounded-xl border p-4 text-left transition-colors ${
                          active ? "border-[#85B7EB] bg-[#E6F1FB]" : "border-border hover:border-primary/40"
                        } ${isMediation ? "cursor-default" : "cursor-pointer"}`}
                      >
                        <div className="mb-2 flex items-start justify-between gap-2">
                          <div className={`text-[12.5px] font-semibold ${active ? "text-[#3172B0]" : "text-foreground"}`}>
                            {e.name}
                          </div>
                          {e.recommended ? <Tag color="g">Recommended</Tag> : e.tag ? <Tag color="p">{e.tag}</Tag> : null}
                        </div>
                        <div className="mb-2.5 text-[12px] leading-relaxed text-muted-foreground">
                          {e.desc}
                        </div>
                        <div
                          className={`rounded-md px-2.5 py-1.5 text-[11.5px] leading-snug ${
                            active ? "bg-[#D6E8F7] text-[#3172B0]" : "bg-muted/40 text-muted-foreground"
                          }`}
                        >
                          <strong>Regulatory: </strong>{e.regulatory}
                        </div>
                      </button>
                    );
                  })}
              </div>

              {/* Estimand summary */}
              {(() => {
                const selected = ESTIMAND_OPTS.find(e => e.key === estimand);
                if (!selected) return null;
                const WHY = {
                  ATT: "The commercial question is whether HIGH engagers benefit — not the average user. ATT focuses exactly on that treated group, matching the investor and HAS framing.",
                  ATE: "ATE answers a population-level question: what would happen if all users were assigned to high engagement? More conservative — required for some NICE DSP submissions.",
                  CATE: "CATE estimates how the effect varies across subgroups and individual covariates — surfacing which users benefit most. Estimated with Causal Forest / GRF, BART, or meta-learners and powers personalised evidence claims.",
                  "MEDIATION": "Mediation estimands decompose the total effect into direct and indirect pathways, providing mechanism evidence alongside the main result.",
                };
                return (
                  <div className="mt-3 rounded-xl border border-[#C4B4DC] bg-[#F3EFF8] p-4">
                    <div className="mb-1.5 text-[13px] font-semibold text-[#4B3070]">
                      Selected estimand — {selected.key}
                    </div>
                    <div className="text-[12px] leading-relaxed text-[#4B3070]">
                      {WHY[estimand]}
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

        </div>

        {/* ── RIGHT SIDEBAR — Study Feasibility Risk (sticky) ───────────────── */}
        <div className="sticky top-4 self-start">
          {retro ? (
            <Card className="gap-0 p-5">
              <div className="mb-1.5 text-[13px] font-semibold text-foreground">
                Your study configuration
              </div>
              <div className="mb-4 text-[12px] leading-relaxed text-muted-foreground">
                Summary of the design choices for this study.
              </div>

              <div className="flex flex-col gap-2 border-t border-border pt-3.5">
                {[
                  ["Type",     "Retrospective"],
                  ["Design",   designLabel],
                  ["Estimand", estimand],
                ].map(([k,v]) => (
                  <div key={k} className="flex items-baseline justify-between">
                    <span className="text-[12px] text-muted-foreground">{k}</span>
                    <span className={`text-[12px] font-semibold ${k === "Estimand" ? "text-[#3172B0]" : "text-foreground"}`}>
                      {v}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          ) : (
            <Card className="gap-0 p-5 text-[12px] leading-relaxed text-muted-foreground">
              Your study configuration summary is shown for retrospective designs. Switch to retrospective in Step 1 to configure the design family and estimand.
            </Card>
          )}
        </div>

      </div>
      {/* ── /two-column shell ─────────────────────────────────────────────── */}

      <div className="flex items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" onClick={() => onBack?.()}>
          <ArrowLeft size={15} /> Back
        </Button>
        <Button onClick={() => onNext?.({ approach, design, estimand })}>
          Continue <ArrowRight size={15} />
        </Button>
      </div>

      <InlineChatbot {...chatProps} />

    </div>
  );
}
