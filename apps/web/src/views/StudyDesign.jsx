import { useState } from "react";
import { Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

export default function StudyDesign({ studyType, studyDesign = "retro_cohort", studyEstimand = "ATT" }) {
  const isRetro = !studyType || studyType === "retro";
  const isMediation = studyDesign === "mediation";

  const allowedKeys = ESTIMATOR_FILTER[isRetro ? "retro" : "prosp"] ?? ESTIMATOR_FILTER.retro;
  const visibleEstimators = ESTIMATORS.filter((e) => allowedKeys.includes(e.key) && e.key !== "mediation");

  const defaultSelected = isMediation ? ["mediation"] : ["lme", "ols"];
  const [estimators, setEstimators] = useState(defaultSelected);

  function toggleEst(key) {
    if (isMediation) return;
    setEstimators((prev) => (prev.includes(key) ? prev.filter((e) => e !== key) : [...prev, key]));
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

    </div>
  );
}
