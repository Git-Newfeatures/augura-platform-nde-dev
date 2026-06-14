// StepNav.jsx — the single study step navigator. Replaces Timeline + Sidebar.
//   variant="map"  → rich vertical timeline for the Overview. Uses the cockpit
//                    study's curated per-step states + inline StepDetail (D1).
//                    Navigation happens via StepDetail's own CTAs (go).
//   variant="rail" → slim left rail for step pages. Live gating via stepStateFor.
import { useState } from "react";
import { Ico } from "./icons.jsx";
import { Card, Pill } from "./primitives.jsx";
import { ACCENT, BLUECORN, SOLEIL } from "./tokens.js";
import { StepDetail } from "./StepDetail.jsx";
import { WORKFLOW, VIEW_LABEL } from "../lib/nav.js";

function stateColor(st) {
  if (st === "done") return ACCENT;
  if (st === "active") return BLUECORN;
  if (st === "ready" || st === "pending") return SOLEIL;
  return "rgba(0,0,0,0.28)";
}

export function StepNav({ variant = "rail", study, ctx, onNavigate, sticky = true, width = 210, top = 70 }) {
  if (variant === "map") return <MapNav study={study} onNavigate={onNavigate} />;
  return <RailNav study={study} ctx={ctx} onNavigate={onNavigate} sticky={sticky} width={width} top={top} />;
}

// ── MAP (Overview) — port of the cockpit Timeline. Row click expands an inline
//    StepDetail preview; StepDetail's own buttons call go() to open the step. ──
function MapNav({ study, onNavigate }) {
  const steps = study?.steps || [];
  const activeKey = steps[(study?.activeStep || 1) - 1]?.key || steps[0]?.key;
  const [focus, setFocus] = useState(activeKey);

  return (
    <Card className="p-2">
      {steps.map((s, i) => {
        const isFocus = focus === s.key;
        const col = stateColor(s.state);
        const last = i === steps.length - 1;
        const locked = s.state === "locked";
        return (
          <div key={s.key}>
            <div
              onClick={() => setFocus((p) => (p === s.key ? null : s.key))}
              className={`flex cursor-pointer gap-3.5 rounded-lg px-3 py-[11px] transition-colors ${isFocus ? "bg-primary/[0.08]" : "hover:bg-black/[0.02]"}`}
            >
              {/* node + connector */}
              <div className="flex flex-shrink-0 flex-col items-center">
                <span
                  className="flex h-7 w-7 items-center justify-center rounded-full font-mono text-xs font-medium"
                  style={{
                    background: s.state === "done" ? ACCENT : s.state === "active" ? BLUECORN : "#fff",
                    border: `1.4px solid ${locked || s.state === "pending" ? "rgba(0,0,0,0.14)" : "transparent"}`,
                    color: s.state === "done" || s.state === "active" ? "#fff" : col,
                  }}
                >
                  {s.state === "done" ? <Ico name="check" size={14} color="#fff" />
                    : locked ? <Ico name="lock" size={12} color="rgba(0,0,0,0.40)" />
                    : s.n}
                </span>
                {!last && (
                  <span
                    className="w-px flex-1"
                    style={{ minHeight: isFocus ? 8 : 14, background: s.state === "done" ? ACCENT : "rgba(0,0,0,0.10)", marginTop: 3 }}
                  />
                )}
              </div>
              {/* icon badge */}
              <span className={`mt-px flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-lg ${locked ? "bg-transparent" : "bg-primary/[0.08]"}`}>
                <Ico name={s.icon} size={16} color={locked ? "rgba(0,0,0,0.28)" : col} />
              </span>
              {/* label + sub */}
              <div className="flex min-w-0 flex-1 flex-col gap-[3px] pt-px pb-1">
                <div className="flex items-center gap-[9px]">
                  <span className={`whitespace-nowrap text-sm ${s.state === "active" ? "font-semibold" : "font-medium"} ${locked ? "text-muted-foreground/70" : "text-foreground"}`}>{s.label}</span>
                  {s.state === "active" && <Pill kind="active">Active</Pill>}
                  {s.state === "pending" && <Pill kind="flag" />}
                </div>
                <div className="text-xs leading-[1.3] text-muted-foreground/70">{s.sub}</div>
              </div>
              <Ico name={isFocus ? "chevDown" : "chevRight"} size={16} color="rgba(0,0,0,0.28)" style={{ marginTop: 9, flexShrink: 0 }} />
            </div>
            {/* expanded detail (StepDetail owns the navigate CTAs) */}
            {isFocus && (
              <div className="mt-0.5 mr-3 mb-3.5 ml-[54px] rounded-xl border border-border bg-card px-[18px] py-4 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
                <StepDetail study={study} step={s} go={onNavigate} />
              </div>
            )}
          </div>
        );
      })}
    </Card>
  );
}

// ── RAIL (step pages) — slim navigator with live gating via stepStateFor ────
function RailNav({ study, ctx, onNavigate, sticky = true, width = 210, top = 70 }) {
  const currentView = ctx?.currentView;
  // Rail state mirrors the study's own per-step progress (same source as the
  // Overview), so the rail, header ring and readiness always agree.
  const steps = WORKFLOW.map((s) => {
    const cockpitStep = study?.steps?.find((cs) => cs.key === s.key);
    return { ...s, state: cockpitStep?.state ?? "locked" };
  });

  const overviewActive = currentView === "cockpit" || !currentView;
  return (
    <aside
      className="flex flex-shrink-0 flex-col gap-0.5 self-start"
      style={{ width, ...(sticky ? { position: "sticky", top } : null) }}
    >
      {/* Study Overview (home) */}
      <button
        onClick={() => onNavigate("cockpit")}
        className={`mb-1.5 flex w-full cursor-pointer items-center gap-2.5 rounded-lg border-none px-2.5 py-[9px] text-left text-[13px] text-foreground ${overviewActive ? "bg-primary/[0.08] font-semibold" : "bg-transparent font-medium hover:bg-black/[0.02]"}`}
      >
        <span
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md"
          style={{ background: overviewActive ? BLUECORN : "#fff", border: `1px solid ${overviewActive ? "transparent" : "rgba(0,0,0,0.07)"}`, color: overviewActive ? "#fff" : "rgba(0,0,0,0.55)" }}
        >
          <Ico name="grid" size={13} color={overviewActive ? "#fff" : "rgba(0,0,0,0.55)"} />
        </span>
        <span>Overview</span>
      </button>
      <div className="px-1.5 pb-2.5 text-[10px] font-semibold tracking-[0.12em] text-muted-foreground/70">WORKFLOW</div>
      {steps.map((s) => {
        const isCurrent = s.views.includes(currentView);
        const done = s.state === "done";
        const locked = s.state === "locked";
        const chipBg = done ? ACCENT : isCurrent ? BLUECORN : "#fff";
        const chipFg = done || isCurrent ? "#fff" : locked ? "rgba(0,0,0,0.40)" : "rgba(0,0,0,0.55)";
        return (
          <div key={s.key}>
            <button
              disabled={locked}
              onClick={() => !locked && onNavigate(s.primaryView)}
              className={`flex w-full items-center gap-2.5 rounded-lg border-none px-2.5 py-[9px] text-left text-[13px] ${isCurrent ? "bg-primary/[0.08] font-semibold" : "bg-transparent font-medium"} ${locked ? "cursor-default text-muted-foreground/70 opacity-60" : "cursor-pointer text-foreground"} ${!locked && !isCurrent ? "hover:bg-black/[0.02]" : ""}`}
            >
              <span
                className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md"
                style={{ background: chipBg, border: `1px solid ${done || isCurrent ? "transparent" : "rgba(0,0,0,0.07)"}`, color: chipFg }}
              >
                {done ? <Ico name="check" size={13} color="#fff" />
                  : locked ? <Ico name="lock" size={11} color="rgba(0,0,0,0.40)" />
                  : <Ico name={s.icon} size={13} color={chipFg} />}
              </span>
              <span className="overflow-hidden text-ellipsis whitespace-nowrap">{s.label}</span>
            </button>
            {/* Sub-views of the active step (e.g. 1a/1b, Run/Profile) nested in the rail */}
            {isCurrent && s.views.length > 1 && (
              <div className="mb-1 ml-[30px] mt-0.5 flex flex-col gap-0.5 border-l border-border pl-2">
                {s.views.map((v) => {
                  const subActive = currentView === v;
                  return (
                    <button
                      key={v}
                      onClick={() => onNavigate(v)}
                      className={`rounded-md px-2 py-[5px] text-left text-[12px] ${subActive ? "bg-primary/10 font-semibold text-primary" : "text-muted-foreground hover:bg-black/[0.03]"}`}
                    >
                      {VIEW_LABEL[v] || v}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}
