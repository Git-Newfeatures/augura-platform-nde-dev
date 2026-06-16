import { useState } from "react";
import { Check, ArrowLeft, ArrowRight, GitFork, Waves, Plus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SubTabs } from "@/cockpit/SubTabs";
import { ESTIMATORS, ESTIMATOR_FILTER } from "../config";

const ESTIMATOR_META = {
  lme: {
    desc: "Best fit for longitudinal biomarker data with repeated measurements per user. Accounts for individual-level variation over time.",
    tags: [["g", "Recommended"], ["b", "Handles missing data"], ["b", "Longitudinal"]],
  },
  ols: {
    desc: "Simpler benchmark model. Adjusted for all measured confounders. Interpretable coefficients. Best used alongside LME to check robustness.",
    tags: [["a", "Benchmark"], ["b", "Interpretable"]],
  },
  ipw: {
    desc: "Reweights users by inverse probability of group assignment. Balances covariate distributions between HIGH and REST groups.",
    tags: [["b", "Covariate balance"], ["a", "Higher variance"]],
  },
  mediation: {
    desc: "Baron-Kenny framework + ACME estimation. Decomposes direct and indirect effects. Cannot be combined with total-effect estimators on the same estimand.",
    tags: [["b", "Mechanism analysis"], ["a", "Requires mediator variables"]],
  },
  tmle: {
    desc: "Doubly robust — valid if either the outcome model or propensity model is correctly specified. Most robust to unmeasured confounding.",
    tags: [["b", "Doubly robust"], ["p", "Advanced"]],
  },
  did: {
    desc: "Compares change over time between groups rather than absolute levels. Controls for stable baseline differences. Requires parallel trends assumption.",
    tags: [["b", "Time-invariant control"], ["a", "Parallel trends required"]],
  },
};

// Demo-only additional analyses (mirror the reference sketch's "Additional analyses" tab).
// Selection is local-only — these do not feed downstream estimator selection.
const ADDITIONAL_ANALYSES = [
  {
    key: "mediation",
    name: "Mediation — NDE & NIE decomposition",
    desc: "Split the total effect into the natural direct effect and the natural indirect effect that flows through the recommendation-adherence mediator.",
    tags: [["p", "Mediated ATE · NDE / NIE"], ["g", "ACME · bootstrapped CI"]],
  },
  {
    key: "shift",
    name: "Stochastic / shift intervention",
    desc: "Modify the engagement distribution (threshold, delta shift, or stochastic policy) rather than a binary HIGH-vs-REST contrast to estimate average potential impact.",
    tags: [["b", "Modified treatment policy"], ["a", "Continuous exposure required"]],
  },
];

// Accent tones for the small meta tags (brand signal palette).
const TONE = {
  g: "border-primary/30 bg-secondary text-primary",
  a: "border-[#B98900]/30 bg-[#FAEEDA] text-[#7a5b00]",
  b: "border-[#3172B0]/30 bg-[#E6F1FB] text-[#1f4f86]",
  p: "border-[#3C3489]/30 bg-[#EEEDFE] text-[#3C3489]",
  r: "border-[#C0392B]/30 bg-[#FCEBEB] text-[#8f2a20]",
};
function Tone({ c = "b", children }) {
  return (
    <Badge variant="outline" className={`rounded-md px-2 py-0.5 text-[11px] font-normal ${TONE[c] || TONE.b}`}>
      {children}
    </Badge>
  );
}

// Selectable "Additional analyses" card — demo-only local toggle.
function AddlCard({ icon: Icon, name, desc, tags, checked, onToggle }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex gap-3 rounded-xl border p-5 text-left transition-colors ${
        checked ? "border-primary bg-secondary" : "border-border hover:border-primary/40"
      }`}
    >
      <span
        className={`mt-0.5 flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded-[4px] border ${
          checked ? "border-primary bg-primary text-white" : "border-border bg-card"
        }`}
      >
        {checked && <Check size={12} strokeWidth={3} />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Icon size={15} className={checked ? "text-primary" : "text-muted-foreground"} />
          <div className={`text-[13px] font-semibold ${checked ? "text-primary" : "text-foreground"}`}>{name}</div>
        </div>
        <div className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{desc}</div>
        <div className="mt-2 flex flex-wrap gap-1">
          {tags.map(([c, t]) => (
            <Tone key={t} c={c}>{t}</Tone>
          ))}
        </div>
      </div>
    </button>
  );
}

export default function StudyDesign({ studyType, studyDesign = "retro_cohort", studyEstimand = "ATT" }) {
  const isRetro = !studyType || studyType === "retro";
  const isMediation = studyDesign === "mediation";

  const allowedKeys = ESTIMATOR_FILTER[isRetro ? "retro" : "prosp"] ?? ESTIMATOR_FILTER.retro;
  const visibleEstimators = ESTIMATORS.filter((e) => allowedKeys.includes(e.key) && e.key !== "mediation");

  const defaultSelected = isMediation ? ["mediation"] : ["lme", "ols"];
  const [estimators, setEstimators] = useState(defaultSelected);

  // Additional analyses — demo-only local selection, does not feed downstream.
  const [addlAnalyses, setAddlAnalyses] = useState([]);

  // Sub-tab between estimator selection and additional analyses.
  const [tab, setTab] = useState("estimators");

  function toggleEst(key) {
    if (isMediation) return;
    setEstimators((prev) => (prev.includes(key) ? prev.filter((e) => e !== key) : [...prev, key]));
  }

  function toggleAddl(key) {
    setAddlAnalyses((prev) => (prev.includes(key) ? prev.filter((a) => a !== key) : [...prev, key]));
  }


  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="text-[13px] font-semibold text-foreground">
          Select estimators to compare in simulation
        </div>
        <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
          All estimators target the <strong className="font-semibold text-foreground">{studyEstimand}</strong> estimand and are adjusted on the
          DAG confounders. Statistical operating characteristics (bias, variance, MSE, power) are computed in the E2 simulation engine.
        </p>
      </div>

      <SubTabs
        tabs={[
          { id: "estimators", label: "Estimator selection" },
          { id: "additional", label: "Additional analyses", badge: addlAnalyses.length || undefined },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "estimators" ? (
        <>
          {isMediation ? (
            <Card className="gap-0 rounded-xl border-[#A8DDE6] bg-[#EAF7F9] p-5">
              <div className="text-[13px] font-semibold text-[#1A6E7A]">Causal mediation design — estimator is fixed</div>
              <p className="mt-1.5 mb-3 text-[12px] leading-relaxed text-muted-foreground">
                The Baron-Kenny + ACME estimator is automatically selected. It cannot be combined with total-effect estimators (LME, OLS, IPW) on the same estimand.
              </p>
              <div className="grid grid-cols-2 gap-2.5">
                {[
                  ["NDE", "Natural Direct Effect", "Effect of engagement on HbA1c holding adherence fixed"],
                  ["ACME", "Average Causal Mediation Effect", "Indirect effect operating through recommendation adherence"],
                ].map(([abbr, name, def]) => (
                  <div key={abbr} className="rounded-lg border border-[#A8DDE6] bg-card p-3">
                    <div className="font-mono text-[11px] font-semibold text-[#1A6E7A]">{abbr}</div>
                    <div className="mt-1 text-[12px] font-semibold text-foreground">{name}</div>
                    <div className="mt-1 text-[12px] leading-snug text-muted-foreground">{def}</div>
                  </div>
                ))}
              </div>
            </Card>
          ) : (
            <div className="flex flex-col gap-2">
              {visibleEstimators.map((e) => {
                const checked = estimators.includes(e.key);
                const meta = ESTIMATOR_META[e.key] ?? { desc: "", tags: [] };
                return (
                  <button
                    key={e.key}
                    type="button"
                    onClick={() => toggleEst(e.key)}
                    className={`flex gap-3 rounded-xl border p-4 text-left transition-colors ${
                      checked ? "border-primary bg-secondary" : "border-border hover:border-primary/40"
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded-[4px] border ${
                        checked ? "border-primary bg-primary text-white" : "border-border bg-card"
                      }`}
                    >
                      {checked && <Check size={12} strokeWidth={3} />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <div className={`text-[12.5px] font-semibold ${checked ? "text-primary" : "text-foreground"}`}>{e.label}</div>
                        <div className="flex flex-shrink-0 gap-1.5">
                          {e.recommended && <Tone c="g">Recommended</Tone>}
                          {e.bootstrapPending && <Tone c="a">Bootstrap pending</Tone>}
                        </div>
                      </div>
                      <div className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{meta.desc}</div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {meta.tags.map(([c, t]) => (
                          <Tone key={t} c={c}>{t}</Tone>
                        ))}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {!isMediation && (
            <div className="rounded-lg border border-primary/30 bg-secondary px-3.5 py-2.5 text-[12.5px] text-primary">
              <strong className="font-semibold">{estimators.length} estimator{estimators.length !== 1 ? "s" : ""} selected</strong> — bias, variance, MSE and
              power will be computed in E2 simulation and compared across all selected estimators.
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
              <Plus size={15} className="text-primary" /> Additional analyses
            </div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">
              Optional analyses that extend the primary estimand with decomposition or counterfactual projection. Toggle any to include
              alongside the main results.
            </p>
          </div>

          {ADDITIONAL_ANALYSES.map((a) => {
            const Icon = a.key === "mediation" ? GitFork : Waves;
            return (
              <AddlCard
                key={a.key}
                icon={Icon}
                name={a.name}
                desc={a.desc}
                tags={a.tags}
                checked={addlAnalyses.includes(a.key)}
                onToggle={() => toggleAddl(a.key)}
              />
            );
          })}

          <div className="rounded-lg border border-border bg-muted/40 px-3.5 py-2.5 text-[12px] leading-relaxed text-muted-foreground">
            {addlAnalyses.length === 0
              ? "No additional analyses selected — only the primary estimand will be estimated."
              : `${addlAnalyses.length} additional ${addlAnalyses.length === 1 ? "analysis" : "analyses"} will be included alongside the primary estimand in the results.`}
          </div>
        </div>
      )}

    </div>
  );
}
