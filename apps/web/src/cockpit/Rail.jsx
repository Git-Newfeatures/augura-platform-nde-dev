// Rail.jsx — right aside rail (port of Rail in Cockpit.jsx)
import { Ico } from "./icons.jsx";
import { Card } from "./primitives.jsx";
import { INK, ACCENT, SOLEIL, BLUECORN } from "./tokens.js";
import { viewForStepNumber } from "./cockpitData.js";

const TONE = {
  amber:    { c: "#B98900", bg: "rgba(232,184,0,0.16)" },
  bluecorn: { c: "#3172B0", bg: "rgba(49,114,176,0.12)" },
  carmine:  { c: "#C0392B", bg: "rgba(192,57,43,0.10)" },
};

export function Rail({ study, go }) {
  const q = study.question;

  return (
    <div className="sticky top-[78px] flex flex-col gap-[18px]">

      {/* Needs attention — only shown if there are actions */}
      {study.actions.length > 0 && (
        <Card className="px-4 py-[15px]" style={{ borderColor: "rgba(185,137,0,0.28)" }}>
          <div className="mb-2 flex items-center gap-[7px]">
            <Ico name="flag" size={15} color={SOLEIL} />
            <h3 className="m-0 text-[14px] font-semibold text-foreground">
              Needs attention
            </h3>
          </div>
          {study.actions.map((a, i) => {
            const tn = TONE[a.tone] || TONE.bluecorn;
            return (
              <div
                key={a.id}
                onClick={() => go(viewForStepNumber(a.step))}
                className={`flex cursor-pointer gap-[10px] px-1 py-[9px] ${i === 0 ? "" : "border-t border-border"}`}
              >
                <span
                  className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-[7px]"
                  style={{ background: tn.bg, color: tn.c }}
                >
                  <Ico name={a.icon} size={13} color={tn.c} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[12.5px] font-medium leading-[1.32] text-foreground">
                    {a.title}
                  </div>
                  <div className="mt-px text-[11px] text-muted-foreground/70">
                    {a.meta}
                  </div>
                </div>
              </div>
            );
          })}
        </Card>
      )}

      {/* Causal question */}
      <Card className="px-4 py-[15px]">
        <h3 className="mt-0 mb-[11px] text-[14px] font-semibold text-foreground">
          Causal question
        </h3>
        {[["Population", q.population], ["Exposure", q.exposure], ["Outcome", q.outcome]].map(([label, val]) => (
          <div key={label} className="mb-[9px]">
            <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.09em] text-primary">{label}</div>
            <div className="text-[12.5px] leading-[1.4] text-foreground/80">{val}</div>
          </div>
        ))}
      </Card>

      {/* Readiness checklist */}
      <Card className="px-4 py-[15px]">
        <div className="mb-3 flex items-baseline justify-between">
          <h3 className="m-0 text-[14px] font-semibold text-foreground">
            Readiness checklist
          </h3>
          <span className="font-mono text-[12.5px] text-primary">{study.readiness}%</span>
        </div>
        {study.readinessRows.map((r, i) => {
          const iconName =
            r.state === "done"   ? "checkCircle" :
            r.state === "flag"   ? "alert" :
            r.state === "active" ? "dot" :
            "lock";
          const iconColor =
            r.state === "done"   ? ACCENT :
            r.state === "flag"   ? SOLEIL :
            r.state === "active" ? BLUECORN :
            INK[28];
          return (
            <div key={i} className="flex items-center gap-[9px] py-1.5">
              <Ico name={iconName} size={15} color={iconColor} />
              <span className={`flex-1 text-[12.5px] ${r.state === "locked" ? "text-muted-foreground/70" : "text-foreground/80"}`}>{r.label}</span>
              {r.note && (
                <span className="max-w-[110px] text-right text-[10.5px] leading-[1.25] text-[#9A7200]">{r.note}</span>
              )}
            </div>
          );
        })}
      </Card>

    </div>
  );
}
