import { useState, useEffect } from "react";
import { Check } from "lucide-react";

// ── Simulation loading screen (shadcn/Tailwind) ───────────────────────────────
export default function SimulationLoadingScreen({ estimators, studyType }) {
  const [step, setStep] = useState(0);
  const steps = [
    "Applying DAG adjustment set (Age, Sex, BMI, HbA1c₀)",
    `Loading ${estimators?.length ?? 4} estimator${estimators?.length !== 1 ? "s" : ""} for ${studyType === "retro" ? "retrospective" : "prospective"} study`,
    "Calibrating bootstrap scenarios (N=1,000 iterations)",
    "Initialising analytical engine · ready",
  ];
  useEffect(() => {
    const timers = steps.map((_, i) => setTimeout(() => setStep(i + 1), 700 + i * 950));
    return () => timers.forEach(clearTimeout);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center gap-7">
      {/* Spinner */}
      <div className="h-[52px] w-[52px] animate-spin rounded-full border-[3px] border-border border-t-primary [animation-duration:0.9s]" />
      <div className="text-center">
        <div className="mb-1.5 text-[17px] font-bold text-foreground">Setting up your simulation</div>
        <div className="text-[12px] text-muted-foreground">
          Preparing the E2 analytical engine with your study configuration
        </div>
      </div>
      {/* Progress steps */}
      <div className="flex min-w-[360px] flex-col gap-2">
        {steps.map((s, i) => {
          const done = i < step;
          const active = i === step - 1;
          return (
            <div
              key={i}
              className={`flex items-center gap-2.5 rounded-lg border-[0.5px] px-3 py-2 transition-all ${
                done
                  ? "border-[#5DCAA5] bg-secondary"
                  : active
                    ? "border-border bg-card"
                    : "border-transparent"
              } ${i > step ? "opacity-30" : "opacity-100"}`}
            >
              <div
                className={`flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded-full border-[1.5px] transition-all ${
                  done ? "border-primary bg-primary text-white" : "border-border bg-transparent"
                }`}
              >
                {done && <Check size={11} strokeWidth={3} />}
              </div>
              <span className={`text-[11.5px] ${done ? "text-primary" : active ? "text-foreground" : "text-muted-foreground/60"}`}>
                {s}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
