import { useState, useEffect, useMemo } from "react";
import { Check, ArrowLeft, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useReference, normEstimators, estimatorFilter } from "@/workspace/dataClient";
import { apiJson } from "@/api";

// Tags-only presentation map (generic signal labels). Estimator DESCRIPTIONS are
// sourced live from the /reference/estimators catalog tooltip, not hardcoded here.
const ESTIMATOR_TAGS = {
  lme: [["g", "Recommended"], ["b", "Handles missing data"], ["b", "Longitudinal"]],
  ols: [["a", "Benchmark"], ["b", "Interpretable"]],
  ipw: [["b", "Covariate balance"], ["a", "Higher variance"]],
  mediation: [["b", "Mechanism analysis"], ["a", "Requires mediator variables"]],
  tmle: [["b", "Doubly robust"], ["p", "Advanced"]],
  did: [["b", "Time-invariant control"], ["a", "Parallel trends required"]],
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

export default function StudyDesign({ studyType, studyDesign = "retro_cohort", studyEstimand = "ATT", onNext, onBack }) {
  const isRetro = !studyType || studyType === "retro";
  const isMediation = studyDesign === "mediation";

  // Estimators — live from /reference/estimators.
  const { data: estimatorRows, loading: estimatorsLoading } = useReference('estimators');
  const ESTIMATORS = useMemo(() => normEstimators(estimatorRows), [estimatorRows]);
  const ESTIMATOR_FILTER = useMemo(() => estimatorFilter(ESTIMATORS), [ESTIMATORS]);

  const allowedKeys = ESTIMATOR_FILTER[isRetro ? "retro" : "prosp"] ?? ESTIMATOR_FILTER.retro;
  const visibleEstimators = ESTIMATORS.filter((e) => allowedKeys.includes(e.key) && e.key !== "mediation");

  const defaultSelected = isMediation ? ["mediation"] : ["lme", "ols"];
  const [estimators, setEstimators] = useState(defaultSelected);

  function toggleEst(key) {
    if (isMediation) return;
    setEstimators((prev) => (prev.includes(key) ? prev.filter((e) => e !== key) : [...prev, key]));
  }

  // Instant analytical power preview (LIVE mode — pure maths, no LLM/DB) via the
  // /simulations/power endpoint, debounced on estimator selection.
  const [preview, setPreview] = useState(null);
  useEffect(() => {
    if (!estimators.length) return;
    let alive = true;
    const t = setTimeout(() => {
      (async () => {
        try {
          const r = await apiJson("/simulations/power", {
            method: "POST",
            body: JSON.stringify({ estimators }),
          });
          if (alive) setPreview(r);
        } catch { if (alive) setPreview(null); }
      })();
    }, 400);
    return () => { alive = false; clearTimeout(t); };
  }, [estimators]);

  // Hold the estimator list until /reference/estimators resolves.
  if (estimatorsLoading && ESTIMATORS.length === 0) return null;

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
            const desc = e.tooltip ?? "";
            const tags = ESTIMATOR_TAGS[e.key] ?? [];
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
                  <div className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{desc}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {tags.map(([c, t]) => (
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

      {estimators.length > 0 && preview?.estimators?.length > 0 && (
        <Card className="gap-0 rounded-xl border p-4">
          <div className="mb-2 text-[12.5px] font-semibold text-foreground">
            Analytical power preview
            <span className="ml-1 font-normal text-muted-foreground">
              · instant estimate (n={preview.n}, threshold {preview.power_threshold}%)
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {preview.estimators.map((e) => (
              <Badge
                key={e.estimator}
                variant="outline"
                className={e.power >= preview.power_threshold ? "text-primary border-primary/30" : "text-[#B98900] border-[#B98900]/30"}
              >
                {e.estimator.toUpperCase()} · {e.power}%
              </Badge>
            ))}
          </div>
          <div className="mt-2 text-[11.5px] text-muted-foreground/70">
            Closed-form estimate. Run the full bootstrap below for validated bias/MSE.
          </div>
        </Card>
      )}

      <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" onClick={() => onBack?.()}>
          <ArrowLeft size={15} /> Back
        </Button>
        <Button
          disabled={!isMediation && estimators.length === 0}
          onClick={() => onNext?.(estimators)}
        >
          Run simulation <ArrowRight size={15} />
        </Button>
      </div>
    </div>
  );
}
