// StepDetail.jsx — per-step expandable body (port of CockpitDetail.jsx)
import { FONT } from "../theme.js";
import { Ico } from "./icons.jsx";
import { Card, Eyebrow, Tag, Ghost } from "./primitives.jsx";
import {
  INK, ACCENT, ACCENT_SOFT, BLUECORN, SOLEIL,
} from "./tokens.js";
import { viewForStepKey } from "./cockpitData.js";

// ── DAG diagram (port of design's DAG component) ──────────────────────────
function DAG() {
  const nodeEl = (x, y, label, kind) => {
    const fill =
      kind === "exp"  ? ACCENT_SOFT :
      kind === "out"  ? "rgba(49,114,176,0.12)" :
      kind === "miss" ? "rgba(232,184,0,0.16)" :
      "#fff";
    const stroke =
      kind === "exp"  ? ACCENT :
      kind === "out"  ? BLUECORN :
      kind === "miss" ? SOLEIL :
      "rgba(0,0,0,0.20)";
    const tc =
      kind === "exp"  ? ACCENT :
      kind === "out"  ? BLUECORN :
      kind === "miss" ? "#9A7200" :
      INK[75];
    return (
      <g key={`${x}-${y}`}>
        <rect x={x - 46} y={y - 15} width="92" height="30" rx="8"
          fill={fill} stroke={stroke} strokeWidth="1.2"
          strokeDasharray={kind === "miss" ? "3 3" : "0"} />
        <text x={x} y={y + 4} textAnchor="middle"
          fontFamily={FONT} fontSize="11.5" fontWeight="500" fill={tc}>{label}</text>
      </g>
    );
  };

  return (
    <svg viewBox="0 0 460 200" style={{ width: "100%", height: "auto", display: "block" }}>
      <defs>
        <marker id="ck-ah" markerWidth="8" markerHeight="8" refX="6.5" refY="3" orient="auto">
          <path d="M0 0 L7 3 L0 6" fill="none" stroke={INK[40]} strokeWidth="1.2" />
        </marker>
        <marker id="ck-ahm" markerWidth="8" markerHeight="8" refX="6.5" refY="3" orient="auto">
          <path d="M0 0 L7 3 L0 6" fill="none" stroke={SOLEIL} strokeWidth="1.2" />
        </marker>
      </defs>
      {/* edges */}
      <path d="M96 100 L184 100" stroke={INK[40]} strokeWidth="1.3" markerEnd="url(#ck-ah)" />
      <path d="M120 44 C150 60 170 78 210 86" stroke={INK[40]} strokeWidth="1.1" fill="none" markerEnd="url(#ck-ah)" />
      <path d="M120 44 C90 70 78 80 64 86" stroke={INK[40]} strokeWidth="1.1" fill="none" markerEnd="url(#ck-ah)" />
      <path d="M360 44 C330 62 300 78 268 88" stroke={INK[40]} strokeWidth="1.1" fill="none" markerEnd="url(#ck-ah)" />
      <path d="M360 156 C330 140 300 122 268 112" stroke={SOLEIL} strokeWidth="1.1" strokeDasharray="3 3" fill="none" markerEnd="url(#ck-ahm)" />
      <path d="M120 156 C150 140 175 120 210 112" stroke={SOLEIL} strokeWidth="1.1" strokeDasharray="3 3" fill="none" markerEnd="url(#ck-ahm)" />
      {/* nodes */}
      {nodeEl(50,  100, "Engagement",  "exp")}
      {nodeEl(230, 100, "ΔHbA1c",      "out")}
      {nodeEl(120,  32, "Age · BMI",   "conf")}
      {nodeEl(360,  32, "Baseline A1c","conf")}
      {nodeEl(120, 168, "Diet",         "miss")}
      {nodeEl(360, 168, "Income",       "miss")}
    </svg>
  );
}

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
  const showFlags = true;
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
  } else if (step.key === "dag") {
    body = (
      <div>
        <p className="mt-0 mb-3.5 text-[13.5px] leading-[1.55] text-foreground/80">
          Augura assembled a candidate adjustment set from the corpus. Two confounders are not yet measured
          in the cohort — confirm a strategy to unblock the design.
        </p>
        <div className="mb-3.5 rounded-lg border border-border bg-muted/40 px-3 pt-3.5 pb-1.5">
          <DAG />
        </div>
        {showFlags && [
          { v: "Diet quality",      note: "No proxy in cohort — corpus suggests FFQ score" },
          { v: "Household income",  note: "Unmeasured — consider ZIP-level median" },
        ].map((f, i) => (
          <div key={i} className="mb-2 flex items-center gap-[10px] rounded-lg border border-[#B98900]/[0.28] bg-[#B98900]/[0.10] px-[11px] py-[9px]">
            <Ico name="alert" size={15} color={SOLEIL} />
            <div className="flex-1">
              <span className="text-[13px] font-medium text-foreground">{f.v}</span>
              <span className="text-[12.5px] text-muted-foreground"> — {f.note}</span>
            </div>
          </div>
        ))}
        <div className="mt-2 flex flex-wrap gap-2">
          <Ghost primary onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="check" size={13} color="#fff" /> Confirm adjustment set
          </Ghost>
          <Ghost onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="network" size={13} color={INK[75]} /> Open DAG editor
          </Ghost>
        </div>
      </div>
    );
  } else if (step.key === "verify") {
    const rows = [
      { v: "engagement_score",   t: "Exposure",   ok: true },
      { v: "hba1c_baseline",     t: "Covariate",  ok: true },
      { v: "hba1c_12m",          t: "Outcome",    ok: true },
      { v: "diet_quality",       t: "Confounder", ok: false, note: "missing" },
      { v: "household_income",   t: "Confounder", ok: false, note: "missing" },
    ];
    body = (
      <div>
        <p className="mt-0 mb-3 text-[13.5px] leading-[1.55] text-foreground/80">
          Variable availability gate.{" "}
          {showFlags
            ? <b className="text-[#9A7200]">2 soft flags</b>
            : "All variables"
          }{" "}on the Lucis cohort.
        </p>
        <div className="overflow-hidden rounded-lg border border-border">
          {rows.map((r, i) => (
            <div
              key={i}
              className={`flex items-center gap-[10px] px-3 py-[9px] ${i === rows.length - 1 ? "" : "border-b border-border"} ${r.ok ? "bg-card" : "bg-[#B98900]/[0.07]"}`}
            >
              <Ico name={r.ok ? "checkCircle" : "alert"} size={15} color={r.ok ? ACCENT : SOLEIL} />
              <span className="flex-1 font-mono text-[12.5px] text-foreground">{r.v}</span>
              <Tag tone="neutral" style={{ fontSize: 10.5 }}>{r.t}</Tag>
              {!r.ok && showFlags && (
                <span className="text-[11px] font-medium text-[#9A7200]">{r.note}</span>
              )}
            </div>
          ))}
        </div>
        <div className="mt-3.5 flex flex-wrap gap-2">
          <Ghost primary onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="flag" size={13} color="#fff" /> Triage flags
          </Ghost>
          <Ghost onClick={() => go(viewForStepKey(step.key))}>
            <Ico name="eye" size={13} color={INK[75]} /> View columns
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
