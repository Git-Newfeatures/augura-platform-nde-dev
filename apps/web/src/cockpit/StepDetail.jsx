// StepDetail.jsx — per-step expandable body (port of CockpitDetail.jsx)
import { Ico } from "./icons.jsx";
import { Eyebrow, Ghost } from "./primitives.jsx";
import {
  INK, ACCENT, ACCENT_SOFT, BLUECORN, SOLEIL,
} from "./tokens.js";
import { viewForStepKey } from "./cockpitData.js";

// ── Field helper ──────────────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <div className="mb-3">
      <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/70">{label}</div>
      <div className="text-[13.5px] leading-[1.45] text-foreground">{children}</div>
    </div>
  );
}

// ── State pill definitions ────────────────────────────────────────────────
const STATEPILL = {
  done:    { c: ACCENT,    t: "Confirmed" },
  active:  { c: BLUECORN,  t: "In progress" },
  pending: { c: SOLEIL,    t: "Needs attention" },
  locked:  { c: INK[40],   t: "Locked" },
};

// ── Main component ────────────────────────────────────────────────────────
export function StepDetail({ study, step, go }) {
  const q = study.question;
  const sp = STATEPILL[step.state] || STATEPILL.locked;

  let body;

  if (step.key === "question") {
    body = (
      <div>
        <Field label="Population">
          {q.population}
          <span className="text-muted-foreground/70"> · {q.nNote}</span>
        </Field>
        <Field label="Exposure">{q.exposure}</Field>
        <Field label="Outcome">{q.outcome}</Field>
        <div className="mt-3.5 flex flex-wrap gap-2">
          <Ghost primary onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="check" size={13} color="#fff" /> Confirmed
          </Ghost>
          <Ghost onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="pencil" size={13} color={INK[75]} /> Refine
          </Ghost>
        </div>
      </div>
    );
  } else {
    // Generic body for all other steps
    body = (
      <div>
        <p className="mt-0 mb-3.5 text-[13.5px] leading-[1.55] text-foreground/80">
          {step.sub}.
        </p>
        {step.state === "locked" ? (
          <div className="flex items-center gap-[10px] rounded-lg border border-border bg-muted/40 px-3.5 py-3 text-[13px] text-muted-foreground">
            <Ico name="lock" size={15} color={INK[40]} />
            Unlocks once the preceding gate is cleared.
          </div>
        ) : step.state === "done" ? (
          <Ghost onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="eye" size={13} color={INK[75]} /> Review output
          </Ghost>
        ) : (
          <Ghost primary onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="arrowRight" size={13} color="#fff" /> Open step
          </Ghost>
        )}
      </div>
    );
  }

  return (
    <div>
      {/* header */}
      <div className="mb-3.5 flex items-center gap-[11px]">
        <span
          className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[10px] text-primary"
          style={{ background: ACCENT_SOFT }}
        >
          <Ico name={step.icon} size={19} color={ACCENT} />
        </span>
        <div className="flex-1">
          <Eyebrow color={INK[40]}>Step {step.n}</Eyebrow>
          <div className="mt-px text-[17px] font-semibold tracking-[-0.01em] text-foreground">{step.label}</div>
        </div>
        <span
          className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold"
          style={{ color: sp.c }}
        >
          <span className="h-[7px] w-[7px] rounded-full" style={{ background: sp.c }} />
          {sp.t}
        </span>
      </div>
      {body}
    </div>
  );
}
