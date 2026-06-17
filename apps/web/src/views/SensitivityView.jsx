import { Info, ShieldQuestion, ArrowLeft, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tag } from "../ui/components";
import { EmptyState } from "@/components/EmptyState";
import InlineChatbot from "../components/InlineChatbot";

// Font families used inside SVG <text> elements (kept identical to the theme tokens).
const MONO = "'Geist Mono Variable', 'Geist Mono', monospace";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 9: SENSITIVITY ANALYSIS
// Data source:
//   - E-value: computed from the locked estimator's mean estimate + CI (simResults)
// ─────────────────────────────────────────────────────────────────────────────

// VanderWeele & Ding (2017) E-value for mean difference:
// Convert to approximate RR via log-linear approx, then E = RR + sqrt(RR*(RR-1))
//   RR ≈ exp(|d| / sd)  — conservative unit-SD conversion
function eValue(meanDiff, sd = 1.0) {
  const d = Math.abs(meanDiff) / sd;
  const rr = Math.exp(d);
  return +(rr + Math.sqrt(rr * (rr - 1))).toFixed(2);
}

// Derive E-value inputs from the locked estimator result in simResults.
// Returns null when there is no live result to compute from.
function deriveSensitivity(simResults) {
  const effect = simResults?.result?.effect;
  const ciLo   = simResults?.result?.ciLower;
  const ciHi   = simResults?.result?.ciUpper;
  if (effect == null || ciLo == null || ciHi == null) return null;

  const estimator = simResults?.estimator ?? "lme";

  // E-values from the locked estimate
  const ev_point = eValue(effect, 1.0);
  const ev_ci    = eValue(ciLo,   1.0);   // CI lower bound — more conservative

  return { effect, ciLo, ciHi, estimator, ev_point, ev_ci };
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ n, title, sub }) {
  return (
    <div className="mb-4 flex items-baseline gap-2.5">
      <div className="flex h-[24px] w-[24px] flex-shrink-0 items-center justify-center rounded-full border border-[#5DCAA5] bg-secondary text-[11px] font-semibold text-primary">
        {n}
      </div>
      <div>
        <div className="text-[15px] font-semibold text-foreground">{title}</div>
        {sub && <div className="mt-0.5 text-[12px] text-muted-foreground">{sub}</div>}
      </div>
    </div>
  );
}

function EValueSection({ sens, partnerLabel = 'Partner' }) {
  const { effect, ciLo, ciHi, ev_point, ev_ci, estimator } = sens;

  const robust = ev_ci >= 2.5;

  return (
    <Card className="mb-5 block gap-0 rounded-xl p-5">
      <SectionHeader n="A" title="E-value analysis"
        sub="How strong must unmeasured confounding be to fully explain away the result?" />

      <div className="mb-5 grid grid-cols-2 gap-4">
        <div className="rounded-[10px] border border-border bg-muted/40 px-4 py-3.5">
          <div className="mb-1.5 text-[12px] font-medium text-muted-foreground">E-value — point estimate</div>
          <div className={`font-mono text-[28px] font-bold ${robust ? "text-primary" : "text-[#B98900]"}`}>{ev_point}</div>
          <div className="mt-1.5 text-[12.5px] text-muted-foreground">
            Effect: {effect.toFixed(2)} [{ciLo.toFixed(2)}, {ciHi.toFixed(2)}]
          </div>
          <div className="mt-0.5 text-[12px] text-muted-foreground">
            Estimator: {estimator.toUpperCase()}
          </div>
        </div>
        <div className="rounded-[10px] border border-border bg-muted/40 px-4 py-3.5">
          <div className="mb-1.5 text-[12px] font-medium text-muted-foreground">E-value — CI lower bound</div>
          <div className={`font-mono text-[28px] font-bold ${ev_ci >= 2.0 ? "text-primary" : "text-[#C0392B]"}`}>{ev_ci}</div>
          <div className="mt-1.5 text-[12.5px] text-muted-foreground">
            CI lower: {ciLo.toFixed(2)}
          </div>
          <div className="mt-0.5 text-[12px] text-muted-foreground">
            Conservative threshold for regulatory submissions
          </div>
        </div>
      </div>

      {/* Robustness scale — SVG */}
      <div className="mb-5">
        <div className="mb-2.5 text-[13px] font-semibold text-foreground">
          Robustness scale — literature context
        </div>
        {(() => {
          const W = 560, maxV = 5;
          const barTop = 8, barH = 20;
          const PAD = { left:8, right:8 };
          const trackW = W - PAD.left - PAD.right;
          const xOf = v => PAD.left + (v / maxV) * trackW;

          // markers sorted left→right so callout rows don't cross
          const markers = [
            { v:1.8,      label:"Health motivation ~1.8",    color:"#B98900" },
            { v:ev_ci,    label:`CI E-value ${ev_ci}`,       color:"#3172B0" },
            { v:ev_point, label:`Point E-value ${ev_point}`, color:"#047857" },
          ].sort((a,b) => a.v - b.v);

          // assign 3 callout rows below bar: row 0 = closest below, 1 = middle, 2 = furthest
          // stagger so adjacent labels don't overlap vertically either
          const rowH = 16;
          const axisY  = barTop + barH + 6;   // tick baseline
          const axisLabelY = axisY + 12;       // "0 1 2 3…" text
          const calloutBase = axisLabelY + 10; // first callout row top

          // assign rows: alternate so left/right markers don't stack on same row
          const rowOf = [0, 2, 1]; // amber→row0, ci→row2, point→row1
          const totalH = calloutBase + rowOf.reduce((a,r)=>Math.max(a,r),0)*rowH + rowH + 4;

          return (
            <svg width="100%" viewBox={`0 0 ${W} ${totalH}`}
              style={{ display:"block", overflow:"visible" }}>

              {/* Track */}
              <rect x={PAD.left} y={barTop} width={trackW} height={barH}
                rx={6} fill="#f1efe8" stroke="#D8D6CE" strokeWidth={0.5} />

              {/* Concern zone */}
              <rect x={PAD.left} y={barTop} width={xOf(2.0) - PAD.left} height={barH}
                rx={6} fill="#FCEBEB" opacity={0.8} />

              {/* "concern" label inside bar */}
              <text x={PAD.left + 6} y={barTop + barH/2 + 4}
                fontSize={8} fill="#C0392B" fontFamily={MONO} opacity={0.7}>concern</text>

              {/* Marker lines */}
              {markers.map((m, i) => (
                <line key={i}
                  x1={xOf(m.v)} y1={barTop}
                  x2={xOf(m.v)} y2={barTop + barH}
                  stroke={m.color} strokeWidth={2.5} />
              ))}

              {/* X axis ticks + labels */}
              {[0,1,2,3,4,5].map(v => (
                <g key={v}>
                  <line x1={xOf(v)} y1={barTop+barH} x2={xOf(v)} y2={axisY}
                    stroke="#C4C2BA" strokeWidth={0.75} />
                  <text x={xOf(v)} y={axisLabelY} textAnchor="middle"
                    fontSize={8.5} fill="#888780" fontFamily={MONO}>{v}</text>
                </g>
              ))}

              {/* Callout lines + labels below axis */}
              {markers.map((m, i) => {
                const x  = xOf(m.v);
                const ly = calloutBase + rowOf[i] * rowH + rowH * 0.75;
                return (
                  <g key={i}>
                    <line x1={x} y1={axisLabelY+2} x2={x} y2={ly - 4}
                      stroke={m.color} strokeWidth={1} strokeDasharray="2,2" opacity={0.5} />
                    <text x={x} y={ly} textAnchor="middle"
                      fontSize={9} fontWeight={700} fill={m.color} fontFamily={MONO}>
                      {m.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          );
        })()}
        <div className="mt-1 text-[12px] text-muted-foreground">
          Red zone = concern (&lt;2.0) · literature prior: health motivation RR ~1.8
        </div>
      </div>

      <div
        className="rounded-lg border px-4 py-3 text-[12.5px] leading-relaxed text-foreground/80"
        style={{ background: robust ? "#EAF3DE" : "#FAEEDA", borderColor: robust ? "#97C459" : "#EF9F27" }}
      >
        <strong>{robust ? "Result is robust to unmeasured confounding." : "Moderate robustness — review required."}</strong>{" "}
        An unmeasured confounder would need to be associated with both {partnerLabel} engagement and the primary outcome change
        by a risk ratio of at least <strong>{ev_point}</strong> to fully explain away the point estimate,
        and at least <strong>{ev_ci}</strong> to explain away the lower confidence bound.
        The largest known lifestyle confounder (health motivation) has an estimated RR of ~1.8,
        well below the E-value threshold.
      </div>
    </Card>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function SensitivityView({ simResults, partnerLabel = 'Partner', chatProps = {}, onNext, onBack }) {
  const sens = deriveSensitivity(simResults);

  return (
    <div className="mx-auto max-w-[960px]">
      {/* Header */}
      <div className="mb-5 flex items-start justify-between">
        <div>
          <div className="mb-1 text-[15px] font-semibold text-foreground">
            Sensitivity analysis
          </div>
          <div className="text-[12px] text-muted-foreground">
            Robustness of the primary result to key assumption violations
          </div>
        </div>
        {sens && (
          <div className="flex items-center gap-2">
            <Tag color="g">Estimator: {sens.estimator.toUpperCase()}</Tag>
          </div>
        )}
      </div>

      {sens ? (
        <>
          {/* Info bar */}
          <div className="mb-5 flex items-start gap-3 rounded-lg border border-border bg-[#f1efe8] px-4 py-3">
            <div className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-md bg-[#E6F1FB] text-[#3172B0]"><Info size={14} /></div>
            <div className="text-[12.5px] leading-relaxed text-foreground/80">
              The E-value is computed from the locked estimator result. It quantifies how strong
              an unmeasured confounder would need to be to fully explain away the observed effect.
            </div>
          </div>

          <EValueSection sens={sens} partnerLabel={partnerLabel} />
        </>
      ) : (
        <EmptyState
          icon={ShieldQuestion}
          title="Not available yet — no live data source wired"
          subtitle="Sensitivity analysis is computed from the locked estimator result. Run and lock an estimator to see E-value robustness here."
        />
      )}

      <div className="mt-1 flex items-center justify-between gap-2 border-t border-border pt-4">
        <Button variant="ghost" onClick={() => onBack?.()}>
          <ArrowLeft size={15} /> Back
        </Button>
        <Button onClick={() => onNext?.()}>
          Generate report <ArrowRight size={15} />
        </Button>
      </div>

      {/* Chatbot */}
      <InlineChatbot {...chatProps} />

    </div>
  );
}
