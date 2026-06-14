// StudyShell.jsx — the single persistent per-study layout.
// A compact study bar sticks under the global navbar (identity + study tabs +
// a "Next" forward button); the workflow lives in a sticky LEFT SIDEBAR rail.
// The main panel (children) swaps between the Overview and a workflow step.
import { useState } from "react";
import { Ico } from "./icons.jsx";
import { Tag, Ghost } from "./primitives.jsx";
import { ACCENT } from "./tokens.js";
import { viewForStepNumber } from "./cockpitData.js";
import { StepNav } from "./StepNav.jsx";
import { SubTabs } from "./SubTabs.jsx";
import { useBreakpoint } from "../lib/useBreakpoint.js";
import { nextView } from "../lib/nav.js";

// Heights of the sticky chrome so the sidebar can stick just below it.
const TOPBAR_H = 58;
const STUDYBAR_H = 96;

function ShellInner({ study, go, onExit, ctx, children }) {
  const bp = useBreakpoint();
  const railInline = bp.md;            // sidebar inline ≥768px; below, it's a drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const goAndClose = (id) => { setDrawerOpen(false); go(id); };
  const padX = bp.md ? 24 : 16;
  const studyTab = ["history", "lineage", "settings"].includes(ctx?.currentView) ? ctx.currentView : "workflow";
  const inWorkflow = studyTab === "workflow";

  // "Next" target — advance one view; from the Overview, open the active step.
  const cur = ctx?.currentView;
  const nextTarget = !cur || cur === "cockpit" ? viewForStepNumber(study.activeStep) : nextView(cur);

  return (
    <main className="mx-auto max-w-[1280px] pb-24">
      {/* Sticky study bar — identity + Next + study tabs. */}
      <div
        className="sticky z-30 border-b border-[rgba(0,0,0,0.07)] bg-[rgba(246,244,241,0.92)] backdrop-blur-[10px]"
        style={{ top: TOPBAR_H, paddingLeft: padX, paddingRight: padX }}
      >
        {/* Row 1 — breadcrumb + identity + progress + Next */}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 pt-2.5 pb-2">
          <button
            onClick={() => onExit?.()}
            className="flex flex-shrink-0 cursor-pointer items-center gap-[5px] border-none bg-transparent p-0 text-[12.5px] font-medium text-primary"
          >
            <Ico name="arrowLeft" size={14} color={ACCENT} />
            Studies
          </button>
          <span className="text-muted-foreground/40">/</span>
          <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-secondary text-[11px] font-semibold text-primary">
            {study.initial}
          </span>
          <span className="text-[14px] font-semibold tracking-[-0.01em] text-foreground">{study.name}</span>
          {study.tagline && (
            <span className="hidden max-w-[260px] truncate text-[12.5px] text-muted-foreground md:inline">· {study.tagline}</span>
          )}
          <Tag tone="neutral"><Ico name="dna" size={11} color="rgba(0,0,0,0.55)" /> N = {Number(study.n || 0).toLocaleString()}</Tag>
          {study.framework && study.framework !== "—" && <Tag tone="emerald">{study.framework}</Tag>}
          <div className="ml-auto flex flex-shrink-0 items-center gap-2.5">
            <span className="font-mono text-[11px] text-muted-foreground/80">{study.done}/{study.total} · {study.readiness}%</span>
            {nextTarget && (
              <Ghost primary onClick={() => go(nextTarget)}>
                Next
                <Ico name="arrowRight" size={12} color="#fff" />
              </Ghost>
            )}
            {!railInline && inWorkflow && (
              <button
                onClick={() => setDrawerOpen(true)}
                className="flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1.5 text-[12px] font-semibold text-foreground/80"
              >
                <Ico name="grid" size={13} color="rgba(0,0,0,0.55)" /> Steps
              </button>
            )}
          </div>
        </div>

        {/* Row 2 — study-level tabs */}
        <SubTabs
          tabs={[
            { id: "workflow", label: "Workflow" },
            { id: "history",  label: "History" },
            { id: "lineage",  label: "Lineage" },
            { id: "settings", label: "Settings" },
          ]}
          active={studyTab}
          onChange={(id) => go(id === "workflow" ? "cockpit" : id)}
        />
      </div>

      {/* Body — sticky sidebar rail + content (Workflow tab); full-width otherwise */}
      <div style={{ paddingLeft: padX, paddingRight: padX }}>
        {railInline && inWorkflow ? (
          <div className="grid items-start gap-6 pt-5" style={{ gridTemplateColumns: "212px minmax(0, 1fr)" }}>
            <StepNav variant="rail" study={study} ctx={ctx} onNavigate={go} top={TOPBAR_H + STUDYBAR_H} />
            <div className="min-w-0">{children}</div>
          </div>
        ) : (
          <div className="min-w-0 pt-5">{children}</div>
        )}
      </div>

      {/* Step drawer (mobile / below md) */}
      {!railInline && drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-[70] bg-[rgba(15,14,12,0.34)] backdrop-blur-[2px]"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="absolute top-0 bottom-0 left-0 w-[264px] max-w-[84vw] overflow-y-auto border-r border-border bg-muted/40 px-3.5 py-[18px] shadow-[0_12px_36px_rgba(0,0,0,0.13)]"
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/70">Workflow</span>
              <button onClick={() => setDrawerOpen(false)} aria-label="Close steps" className="cursor-pointer border-none bg-transparent text-lg leading-none text-muted-foreground">✕</button>
            </div>
            <StepNav variant="rail" study={study} ctx={ctx} onNavigate={goAndClose} sticky={false} width="100%" />
          </div>
        </div>
      )}
    </main>
  );
}

// Keyed by study.id so the shell remounts on study change (resets transient state),
// but persists across step navigation within a study (so the agent loop survives).
export function StudyShell({ study, go, onExit, ctx, children }) {
  return (
    <ShellInner key={study.id} study={study} go={go} onExit={onExit} ctx={ctx}>
      {children}
    </ShellInner>
  );
}
