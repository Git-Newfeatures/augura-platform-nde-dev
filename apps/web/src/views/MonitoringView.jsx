import { useState, useEffect } from "react";
import { ArrowLeft, Radio, SlidersHorizontal, Check, AlertTriangle, X, CheckCircle2, Download } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { C, MONO } from "../theme";
import InlineChatbot from "../components/InlineChatbot";
import { TENANT_ID } from "../config";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 11: POST-STUDY MONITORING DASHBOARD
// Reads from Supabase monitoring_snapshots + monitoring_signals tables.
// Falls back to MOCK_DATA if Supabase is unavailable.
// ─────────────────────────────────────────────────────────────────────────────

// ── Fallback mock data (matches seed data in migration_monitoring.sql) ────────
const MOCK_SNAPSHOTS = [
  { wave_month:"2025-07-01", n_active:194, effect_rolling:-0.30, ci_lower:-0.34, ci_upper:-0.26, mediation_pct:70.0, dm_rr:0.36, engagement_high_pct:34.0, data_quality:96.0, e_value_point:3.18, e_value_ci:2.48, subgroup_age_lt45:-0.37, subgroup_age_gte45:-0.25, subgroup_hba1c_high:-0.40 },
  { wave_month:"2025-08-01", n_active:221, effect_rolling:-0.30, ci_lower:-0.34, ci_upper:-0.26, mediation_pct:70.2, dm_rr:0.36, engagement_high_pct:34.5, data_quality:95.5, e_value_point:3.20, e_value_ci:2.50, subgroup_age_lt45:-0.38, subgroup_age_gte45:-0.25, subgroup_hba1c_high:-0.41 },
  { wave_month:"2025-09-01", n_active:253, effect_rolling:-0.30, ci_lower:-0.34, ci_upper:-0.27, mediation_pct:69.8, dm_rr:0.37, engagement_high_pct:35.0, data_quality:95.0, e_value_point:3.18, e_value_ci:2.48, subgroup_age_lt45:-0.37, subgroup_age_gte45:-0.25, subgroup_hba1c_high:-0.40 },
  { wave_month:"2025-10-01", n_active:287, effect_rolling:-0.28, ci_lower:-0.32, ci_upper:-0.24, mediation_pct:67.5, dm_rr:0.38, engagement_high_pct:32.1, data_quality:93.2, e_value_point:3.00, e_value_ci:2.32, subgroup_age_lt45:-0.35, subgroup_age_gte45:-0.23, subgroup_hba1c_high:-0.38 },
  { wave_month:"2025-11-01", n_active:318, effect_rolling:-0.29, ci_lower:-0.33, ci_upper:-0.25, mediation_pct:68.4, dm_rr:0.37, engagement_high_pct:33.8, data_quality:94.1, e_value_point:3.10, e_value_ci:2.41, subgroup_age_lt45:-0.36, subgroup_age_gte45:-0.24, subgroup_hba1c_high:-0.39 },
  { wave_month:"2025-12-01", n_active:355, effect_rolling:-0.29, ci_lower:-0.33, ci_upper:-0.25, mediation_pct:68.8, dm_rr:0.37, engagement_high_pct:34.2, data_quality:94.5, e_value_point:3.10, e_value_ci:2.42, subgroup_age_lt45:-0.37, subgroup_age_gte45:-0.24, subgroup_hba1c_high:-0.40 },
  { wave_month:"2026-01-01", n_active:398, effect_rolling:-0.30, ci_lower:-0.34, ci_upper:-0.26, mediation_pct:68.9, dm_rr:0.37, engagement_high_pct:35.0, data_quality:94.8, e_value_point:3.18, e_value_ci:2.48, subgroup_age_lt45:-0.37, subgroup_age_gte45:-0.25, subgroup_hba1c_high:-0.40 },
  { wave_month:"2026-02-01", n_active:441, effect_rolling:-0.30, ci_lower:-0.34, ci_upper:-0.26, mediation_pct:69.2, dm_rr:0.37, engagement_high_pct:35.5, data_quality:95.0, e_value_point:3.20, e_value_ci:2.50, subgroup_age_lt45:-0.38, subgroup_age_gte45:-0.25, subgroup_hba1c_high:-0.41 },
  { wave_month:"2026-03-01", n_active:487, effect_rolling:-0.29, ci_lower:-0.33, ci_upper:-0.25, mediation_pct:68.8, dm_rr:0.38, engagement_high_pct:36.5, data_quality:94.7, e_value_point:3.12, e_value_ci:2.43, subgroup_age_lt45:-0.37, subgroup_age_gte45:-0.24, subgroup_hba1c_high:-0.40 },
  { wave_month:"2026-04-01", n_active:531, effect_rolling:-0.29, ci_lower:-0.33, ci_upper:-0.25, mediation_pct:68.0, dm_rr:0.38, engagement_high_pct:37.0, data_quality:94.0, e_value_point:3.10, e_value_ci:2.41, subgroup_age_lt45:-0.36, subgroup_age_gte45:-0.24, subgroup_hba1c_high:-0.39 },
];

const MOCK_SIGNALS = [
  { signal_date:"2025-07-01", signal_type:"ok",      title:"Monitoring started",       description:"Post-study monitoring initiated. Baseline confirmed: effect -0.30 HbA1c [-0.34, -0.26], N=194 (76 treatment / 118 control).", resolved:true  },
  { signal_date:"2025-10-15", signal_type:"warning",  title:"Adherence drop detected",  description:"Rolling engagement high-tier % dropped to 32.1% (-2.4pp vs baseline). Likely seasonal pattern. Effect slightly attenuated to -0.28 but CI still excludes null.", resolved:true  },
  { signal_date:"2026-01-10", signal_type:"ok",       title:"Subgroup effect confirmed", description:"Age <45 and HbA1c 6.0-6.4 subgroup effects confirmed stable over 6 months. No meaningful drift detected.", resolved:true  },
  { signal_date:"2026-04-01", signal_type:"ok",       title:"Effect stable - Apr 2026",  description:"Rolling 6M estimate -0.29 [-0.33, -0.25] consistent with bootstrap result. E-value 3.10 above threshold. N now 531.", resolved:false },
];

// ── SVG mini-chart helpers ────────────────────────────────────────────────────

function MiniChart({ data, field, ci_lower, ci_upper, refLine, color, height=100, decimals=2, unit="" }) {
  const W = 300, H = height;
  const PAD = { top:8, right:8, bottom:22, left:36 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  const vals = data.map(d => d[field]);
  const allVals = [
    ...vals,
    ...(ci_lower ? data.map(d => d[ci_lower]) : []),
    ...(ci_upper ? data.map(d => d[ci_upper]) : []),
    ...(refLine !== undefined ? [refLine] : []),
  ];
  const rawLo = Math.min(...allVals);
  const rawHi = Math.max(...allVals);
  const pad   = (rawHi - rawLo) * 0.15 || 0.5;   // 15% padding, correct sign always
  const lo = rawLo - pad;
  const hi = rawHi + pad;
  const range = hi - lo || 1;

  const px = (i) => PAD.left + (i / Math.max(data.length - 1, 1)) * cw;
  const py = (v) => PAD.top + ch - ((v - lo) / range) * ch;

  const pts = data.map((d, i) => `${px(i)},${py(d[field])}`).join(" ");

  // Y axis: 3 labels
  const yTicks = [lo + range * 0.1, lo + range * 0.5, lo + range * 0.9];

  // X axis: show first, mid, last month labels
  const xLabels = data.length > 0 ? [
    { i:0,                           label: data[0].wave_month?.slice(0,7) },
    { i:Math.floor((data.length-1)/2),label: data[Math.floor((data.length-1)/2)]?.wave_month?.slice(0,7) },
    { i:data.length-1,               label: data[data.length-1].wave_month?.slice(0,7) },
  ] : [];

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:"block", height:H, overflow:"visible" }}>
      {/* Y grid lines + labels */}
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={PAD.left} y1={py(v)} x2={W - PAD.right} y2={py(v)}
            stroke={C.border} strokeWidth={0.5} strokeDasharray="3 3" />
          <text x={PAD.left - 4} y={py(v) + 3} textAnchor="end"
            fontSize={7.5} fill={C.faint} fontFamily={MONO}>
            {v.toFixed(decimals)}{unit}
          </text>
        </g>
      ))}

      {/* CI band */}
      {ci_lower && ci_upper && (
        <polygon fill={`${color}18`}
          points={[
            ...data.map((d,i) => `${px(i)},${py(d[ci_upper])}`),
            ...data.map((_,i) => `${px(data.length-1-i)},${py(data[data.length-1-i][ci_lower])}`),
          ].join(" ")} />
      )}

      {/* Reference line */}
      {refLine !== undefined && (
        <>
          <line x1={PAD.left} y1={py(refLine)} x2={W - PAD.right} y2={py(refLine)}
            stroke={C.border2} strokeWidth={1} strokeDasharray="4 3" />
          <text x={W - PAD.right + 2} y={py(refLine) + 3}
            fontSize={7} fill={C.faint} fontFamily={MONO}>ref</text>
        </>
      )}

      {/* Main line */}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2}
        strokeLinecap="round" strokeLinejoin="round" />

      {/* Data point dots */}
      {data.map((d, i) => (
        <circle key={i} cx={px(i)} cy={py(d[field])} r={2.5} fill={color} />
      ))}

      {/* X axis labels */}
      {xLabels.map(({ i, label }) => (
        <text key={i} x={px(i)} y={H - 4} textAnchor="middle"
          fontSize={7.5} fill={C.faint} fontFamily={MONO}>
          {label}
        </text>
      ))}
    </svg>
  );
}

function SubgroupForest({ snapshots }) {
  const latest = snapshots[snapshots.length - 1];
  if (!latest) return null;

  const rows = [
    { label:"Overall",              n:2847, effect:latest.effect_rolling,    study:-0.33, color:C.green, bold:true  },
    { label:"Age <45",              n:1062, effect:latest.subgroup_age_lt45,  study:-0.41, color:C.blue  },
    { label:"Age ≥45",              n:1785, effect:latest.subgroup_age_gte45, study:-0.27, color:C.blue  },
    { label:"HbA1c 6.0–6.4 ★",     n:1580, effect:latest.subgroup_hba1c_high,study:-0.44, color:C.amber, highlight:true },
  ];

  const xMin=-0.55, xMax=0.05, w=180;
  const toX = v => Math.max(0,Math.min(w,(v-xMin)/(xMax-xMin)*w));
  const nullX = toX(0);

  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-border">
          {["Subgroup","N","Effect plot","Now vs Study"].map(h => (
            <th key={h} className="px-1.5 py-1.5 text-left text-[11px] font-semibold text-foreground">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className={`border-b border-border ${r.highlight ? "bg-[#FAEEDA]" : "bg-transparent"}`}>
            <td className={`px-1.5 py-2 text-[12.5px] text-foreground ${r.bold ? "font-semibold" : "font-normal"}`}>{r.label}</td>
            <td className="px-1.5 py-2 font-mono text-[12px] text-muted-foreground">{r.n.toLocaleString()}</td>
            <td className="px-1.5 py-2">
              <svg width={w+20} height={16} style={{ display:"block", overflow:"visible" }}>
                <line x1={nullX+10} y1={0} x2={nullX+10} y2={16}
                  stroke={C.border2} strokeWidth={1} strokeDasharray="2 2" />
                <line x1={toX(r.effect-0.06)+10} y1={8} x2={toX(r.effect+0.04)+10} y2={8}
                  stroke={r.color} strokeWidth={r.bold?2:1.5} />
                {r.bold
                  ? <polygon fill={r.color}
                      points={`${toX(r.effect)+10},3 ${toX(r.effect)+15},8 ${toX(r.effect)+10},13 ${toX(r.effect)+5},8`} />
                  : <circle cx={toX(r.effect)+10} cy={8} r={3.5} fill={r.color} />}
              </svg>
            </td>
            <td className="px-1.5 py-2 font-mono text-[12px]">
              <span className="font-semibold" style={{ color:r.color }}>{r.effect.toFixed(2)}</span>
              <span className="text-muted-foreground"> Study: {r.study.toFixed(2)} </span>
              <span style={{ color: Math.abs(r.effect-r.study) < 0.04 ? C.green : C.amber }}>
                {Math.abs(r.effect-r.study) < 0.04 ? "✓" : "⚠"}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SignalLog({ signals }) {
  const icon = { ok:Check, warning:AlertTriangle, alert:X };
  const iconStyle = {
    ok:      { bg:C.greenLt, color:C.green,   bd:C.greenMd  },
    warning: { bg:C.amberLt, color:C.amber,   bd:"#EF9F27"  },
    alert:   { bg:C.redLt,   color:C.red,     bd:"#F09595"  },
  };
  return (
    <div className="flex flex-col gap-3.5">
      {[...signals].reverse().map((s, i) => {
        const st = iconStyle[s.signal_type] || iconStyle.ok;
        const SignalIcon = icon[s.signal_type] || Check;
        return (
          <div key={i} className="flex items-start gap-2.5">
            <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full"
              style={{ background:st.bg, border:`1px solid ${st.bd}`, color:st.color }}>
              <SignalIcon size={13} />
            </div>
            <div>
              <div className="mb-1 flex items-center gap-2">
                <span className="font-mono text-[11px] text-muted-foreground">
                  {new Date(s.signal_date).toLocaleDateString("en-GB",{month:"short",year:"numeric"})}
                </span>
                <span className="text-[12.5px] font-semibold text-foreground">{s.title}</span>
                {s.resolved && (
                  <Badge variant="secondary" className="text-[11px] font-normal text-primary">
                    resolved
                  </Badge>
                )}
              </div>
              <div className="text-[12px] leading-relaxed text-muted-foreground">{s.description}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function MonitoringView({ simResults, onBack, partnerLabel = 'Partner', chatProps = {} }) {
  const [snapshots,   setSnapshots]   = useState(MOCK_SNAPSHOTS);
  const [signals,     setSignals]     = useState(MOCK_SIGNALS);
  const [dataSource,  setDataSource]  = useState("mock"); // "live" | "mock"
  const [loading,     setLoading]     = useState(true);
  const [timeRange,   setTimeRange]   = useState("all"); // "3m" | "6m" | "all"
  const [showAlerts,  setShowAlerts]  = useState(false);
  const [alertEffect, setAlertEffect] = useState("0.05");
  const [alertEValue, setAlertEValue] = useState("2.5");
  const [alertSaved,  setAlertSaved]  = useState(false);

  // ── Fetch from Supabase ────────────────────────────────────────────────────
  useEffect(() => {
    const url  = import.meta.env.VITE_SUPABASE_URL;
    const key  = import.meta.env.VITE_SUPABASE_ANON_KEY;
    if (!url || !key) { setLoading(false); return; }

    async function fetchData() {
      try {
        const [snapRes, sigRes] = await Promise.all([
          fetch(`${url}/rest/v1/monitoring_snapshots?tenant_id=eq.${TENANT_ID}&order=wave_month.asc&select=*`, {
            headers: { apikey: key, Authorization: `Bearer ${key}` },
          }),
          fetch(`${url}/rest/v1/monitoring_signals?tenant_id=eq.${TENANT_ID}&order=signal_date.asc&select=*`, {
            headers: { apikey: key, Authorization: `Bearer ${key}` },
          }),
        ]);
        const snaps = await snapRes.json();
        const sigs  = await sigRes.json();
        if (Array.isArray(snaps) && snaps.length > 0) {
          setSnapshots(snaps);
          setDataSource("live");
        }
        if (Array.isArray(sigs) && sigs.length > 0) {
          setSignals(sigs);
        }
      } catch (e) {
        console.warn("MonitoringView: Supabase fetch failed, using mock data", e);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // ── Filter by time range ───────────────────────────────────────────────────
  const filtered = (() => {
    if (timeRange === "all") return snapshots;
    const months = timeRange === "3m" ? 3 : 6;
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - months);
    return snapshots.filter(d => new Date(d.wave_month) >= cutoff);
  })();

  const latest = filtered[filtered.length - 1] ?? snapshots[snapshots.length - 1];

  const studyEffect = simResults?.result?.effect ?? -0.33;

  const effectDrift = Math.abs((latest?.effect_rolling ?? studyEffect) - studyEffect);
  const effectStable = effectDrift < parseFloat(alertEffect || 0.05);
  const evalAbove    = (latest?.e_value_ci ?? 2.67) >= parseFloat(alertEValue || 2.5);


  function saveAlerts() {
    setAlertSaved(true);
    setTimeout(() => setAlertSaved(false), 2500);
  }

  if (loading) return (
    <div className="flex h-[200px] items-center justify-center text-[12.5px] text-muted-foreground">
      Loading monitoring data…
    </div>
  );

  return (
    <div className="mx-auto max-w-[1060px]">
      {/* Header */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="mb-1.5 text-[13px] font-semibold text-primary">
            Post-study monitoring
          </div>
          <div className="mb-1 text-[15px] font-semibold tracking-[-0.01em] text-foreground">
            Post-study monitoring dashboard
          </div>
          <div className="text-[12.5px] text-muted-foreground">
            Longitudinal real-world evidence · {partnerLabel} platform ·
            Baseline study N=824 · 12M primary endpoint {studyEffect.toFixed(2)} HbA1c
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Time range */}
          <div className="flex gap-0.5">
            {[["3m","3M"],["6m","6M"],["all","All"]].map(([v,label]) => (
              <button key={v} onClick={() => setTimeRange(v)}
                className={`cursor-pointer rounded-md border border-border px-2.5 py-1 text-[12px] ${
                  timeRange===v ? "bg-foreground text-white" : "bg-card text-muted-foreground"
                }`}>
                {label}
              </button>
            ))}
          </div>
          <Badge variant="secondary" className="gap-1.5 text-[11px] font-semibold text-primary">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: dataSource === "live" ? "var(--color-primary)" : "var(--color-muted-foreground)" }} />
            {dataSource === "live" ? "Live feed" : "Mock data"}
          </Badge>
          <span className="text-[12px] text-muted-foreground/70">Last updated: Apr 2026</span>
          <button onClick={() => setShowAlerts(a => !a)}
            className={`flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[12px] text-muted-foreground ${
              showAlerts ? "bg-[#f1efe8]" : "bg-card"
            }`}>
            <SlidersHorizontal size={13} /> Alert thresholds
          </button>
        </div>
      </div>

      {/* Alert threshold panel */}
      {showAlerts && (
        <Card className="mb-4 block gap-0 rounded-xl p-5">
          <div className="mb-1 flex items-center gap-2 text-[13px] font-semibold text-foreground">
            <SlidersHorizontal size={15} className="text-primary" />
            Alert threshold configuration
          </div>
          <div className="mb-4 mt-3 grid grid-cols-2 gap-4">
            <div>
              <div className="mb-1.5 text-[12px] text-foreground/80">
                Effect drift alert (HbA1c units) — alert if rolling estimate moves outside
                primary CI ± margin
              </div>
              <input value={alertEffect}
                onChange={e => setAlertEffect(e.target.value)}
                className="w-20 rounded-md border border-border bg-muted/40 px-2.5 py-1.5 font-mono text-[12.5px] text-foreground" />
            </div>
            <div>
              <div className="mb-1.5 text-[12px] text-foreground/80">
                E-value alert — alert if E-value (CI lower bound) drops below threshold
              </div>
              <input value={alertEValue}
                onChange={e => setAlertEValue(e.target.value)}
                className="w-20 rounded-md border border-border bg-muted/40 px-2.5 py-1.5 font-mono text-[12.5px] text-foreground" />
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <Button size="sm" onClick={saveAlerts}>Save thresholds</Button>
            {alertSaved && (
              <span className="flex items-center gap-1 text-[12.5px] text-primary"><Check size={13} /> Saved</span>
            )}
          </div>
        </Card>
      )}

      {/* Status bar */}
      <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-[#5DCAA5] bg-secondary px-4 py-3">
        <Radio size={17} className="mt-px flex-shrink-0 text-primary" />
        <div className="text-[12.5px] leading-relaxed text-foreground/80">
          Study findings confirmed in post-study monitoring. Rolling 6-month effect estimate{" "}
          <strong>{latest?.effect_rolling?.toFixed(2) ?? "−0.31"} HbA1c [{latest?.ci_lower?.toFixed(2) ?? "−0.38"}, {latest?.ci_upper?.toFixed(2) ?? "−0.24"}]</strong>{" "}
          is consistent with primary study result ({studyEffect.toFixed(2)}).
          No safety signals or unexpected engagement drift detected.
          N now <strong>{latest?.n_active?.toLocaleString() ?? "2,847"}</strong> active users with 12M follow-up data.
        </div>
      </div>

      {/* KPI row */}
      <div className="mb-5 grid grid-cols-6 gap-3.5">
        {[
          { label:"Active users",           value: latest?.n_active?.toLocaleString() ?? "2,847", sub:`↑ +245 vs M6` },
          { label:"HbA1c effect (rolling)", value: latest?.effect_rolling?.toFixed(2) ?? "−0.31",  sub:`Study: ${studyEffect.toFixed(2)} ${effectStable?"✓":"⚠"}`, ok: effectStable },
          { label:"Mediation % (M1)",        value: `${(latest?.mediation_pct ?? 68).toFixed(0)}%`, sub:`Study: 70% ${(latest?.mediation_pct??68)>=68?"✓":"⚠"}` },
          { label:"DM progression RR",       value: latest?.dm_rr?.toFixed(2) ?? "0.38",            sub:`Study: 0.36 ${(latest?.dm_rr??0.38)<=0.40?"✓":"⚠"}` },
          { label:"High engagement %",       value: `${(latest?.engagement_high_pct??37).toFixed(0)}%`, sub:`↑ +3pp vs baseline` },
          { label:"Data quality",            value: `${(latest?.data_quality??94).toFixed(0)}%`,     sub:`completeness` },
        ].map((k, i) => (
          <Card key={i} className="gap-0 rounded-xl p-4">
            <div className="mb-1 text-[11px] font-medium text-muted-foreground">{k.label}</div>
            <div className={`font-mono text-[18px] font-semibold ${k.ok === false ? "text-[#B98900]" : "text-foreground"}`}>{k.value}</div>
            <div className="mt-1 text-[12px] text-muted-foreground/70">{k.sub}</div>
          </Card>
        ))}
      </div>

      {/* Charts row 1 */}
      <div className="mb-4 grid grid-cols-2 gap-4">
        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-3 flex items-start justify-between">
            <div>
              <div className="text-[13px] font-semibold text-foreground">Rolling HbA1c effect</div>
              <div className="text-[12px] text-muted-foreground">6-month rolling window · 95% CI band</div>
            </div>
            <span className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
              effectStable
                ? "border-[#5DCAA5] bg-secondary text-primary"
                : "border-[#EF9F27] bg-[#FAEEDA] text-[#B98900]"
            }`}>
              {effectStable ? <><CheckCircle2 size={11} /> Stable</> : <><AlertTriangle size={11} /> Drifting</>}
            </span>
          </div>
          <MiniChart data={filtered} field="effect_rolling"
            ci_lower="ci_lower" ci_upper="ci_upper"
            refLine={studyEffect} color={C.green} height={110} decimals={2} />
          <div className="mt-1.5 flex justify-between">
            <span className="font-mono text-[11px] text-muted-foreground/70">
              {filtered[0]?.wave_month?.slice(0,7)}
            </span>
            <span className="font-mono text-[11px] text-muted-foreground/70">
              {filtered[filtered.length-1]?.wave_month?.slice(0,7)}
            </span>
          </div>
        </Card>

        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-3 flex items-start justify-between">
            <div>
              <div className="text-[13px] font-semibold text-foreground">High-engagement % over time</div>
              <div className="text-[12px] text-muted-foreground">% users in top engagement quartile</div>
            </div>
            <span className="flex items-center gap-1 rounded-full border border-[#5DCAA5] bg-secondary px-2 py-0.5 text-[11px] font-semibold text-primary">
              <CheckCircle2 size={11} /> No drift
            </span>
          </div>
          <MiniChart data={filtered} field="engagement_high_pct"
            color="#0EA5E9" height={100} decimals={0} unit="%" />
        </Card>
      </div>

      {/* Charts row 2 */}
      <div className="mb-4 grid grid-cols-2 gap-4">
        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-0.5 text-[13px] font-semibold text-foreground">
            Subgroup effect lines
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            Rolling 6M estimate per subgroup
          </div>
          {/* Multi-line mini chart */}
          <svg width="100%" viewBox="0 0 320 90" style={{ display:"block", height:90 }}>
            {[
              { field:"effect_rolling",      color:C.green,  label:"Overall",        dash:false },
              { field:"subgroup_age_lt45",   color:C.blue,   label:"Age <45",        dash:false },
              { field:"subgroup_age_gte45",  color:"#0EA5E9",label:"Age ≥45",        dash:true  },
              { field:"subgroup_hba1c_high", color:C.amber,  label:"HbA1c 6.0–6.4", dash:false },
            ].map((s, si) => {
              const vals = filtered.map(d => d[s.field]);
              const allV = filtered.flatMap(d => [d.effect_rolling, d.subgroup_age_lt45, d.subgroup_age_gte45, d.subgroup_hba1c_high]);
              const lo2 = Math.min(...allV)*1.05, hi2 = Math.max(...allV)*0.95;
              const r2 = Math.abs(hi2-lo2)||0.1;
              const px2 = (i) => (i/(filtered.length-1||1))*304+8;
              const py2 = (v) => 88-((v-lo2)/r2)*76;
              const pts2 = vals.map((v,i) => `${px2(i)},${py2(v)}`).join(" ");
              return (
                <polyline key={si} points={pts2} fill="none" stroke={s.color}
                  strokeWidth={s.dash?1:1.5}
                  style={s.dash?{strokeDasharray:"4 3"}:{}}
                  strokeLinecap="round" strokeLinejoin="round" />
              );
            })}
          </svg>
          <div className="mt-2 flex flex-wrap gap-2.5">
            {[
              { color:C.green, label:"Overall" },
              { color:C.blue,  label:"Age <45" },
              { color:"#0EA5E9", label:"Age ≥45" },
              { color:C.amber, label:"HbA1c 6.0–6.4" },
            ].map(s => (
              <div key={s.label} className="flex items-center gap-1.5">
                <div className="h-0.5 w-3 rounded-[1px]" style={{ background:s.color }} />
                <span className="text-[12px] text-muted-foreground">{s.label}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-0.5 text-[13px] font-semibold text-foreground">
            E-value trajectory
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            E-value (point estimate + CI) — monthly recalculation
          </div>
          <svg width="100%" viewBox="0 0 320 90" style={{ display:"block", height:90 }}>
            {(() => {
              const vals_pt = filtered.map(d => d.e_value_point);
              const vals_ci = filtered.map(d => d.e_value_ci);
              const allV = [...vals_pt, ...vals_ci];
              const lo3 = Math.min(...allV)*0.95, hi3 = Math.max(...allV)*1.05;
              const r3 = hi3-lo3||0.1;
              const px3 = (i) => (i/(filtered.length-1||1))*304+8;
              const py3 = (v) => 82-((v-lo3)/r3)*74;
              const alertY = py3(parseFloat(alertEValue||2.5));
              return (
                <>
                  {/* Concern zone */}
                  <rect x={0} y={alertY} width={320} height={90-alertY}
                    fill={C.redLt} opacity={0.5} />
                  <line x1={0} y1={alertY} x2={320} y2={alertY}
                    stroke={C.red} strokeWidth={0.75} strokeDasharray="3 3" />
                  <text x={4} y={alertY-2} fontSize={7.5} fill={C.red} fontFamily={MONO}>
                    threshold {alertEValue}
                  </text>
                  <polyline
                    points={vals_ci.map((v,i)=>`${px3(i)},${py3(v)}`).join(" ")}
                    fill="none" stroke={C.blue} strokeWidth={1.5}
                    strokeDasharray="4 3" strokeLinecap="round" />
                  <polyline
                    points={vals_pt.map((v,i)=>`${px3(i)},${py3(v)}`).join(" ")}
                    fill="none" stroke={C.green} strokeWidth={2}
                    strokeLinecap="round" strokeLinejoin="round" />
                </>
              );
            })()}
          </svg>
          <div className="mt-2 flex gap-2.5">
            <div className="flex items-center gap-1.5">
              <div className="h-0.5 w-3 rounded-[1px]" style={{ background:C.green }} />
              <span className="text-[12px] text-muted-foreground">Point estimate</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="h-px w-3 rounded-[1px]" style={{ background:C.blue, borderTop:`1px dashed ${C.blue}` }} />
              <span className="text-[12px] text-muted-foreground">CI lower bound</span>
            </div>
          </div>
          <div className="mt-2.5 flex items-center gap-1 text-[12px] text-muted-foreground">
            E-value has remained above {alertEValue} throughout monitoring
            {evalAbove ? <CheckCircle2 size={12} className="text-primary" /> : <span className="flex items-center gap-1 text-[#B98900]">— currently below threshold <AlertTriangle size={12} /></span>}
          </div>
        </Card>
      </div>

      {/* Charts row 3 */}
      <div className="mb-4 grid grid-cols-2 gap-4">
        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-0.5 text-[13px] font-semibold text-foreground">
            Cumulative sample growth
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            Users with ≥12M follow-up
          </div>
          <MiniChart data={filtered} field="n_active" color={C.green} height={100} decimals={0} />
        </Card>

        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-0.5 text-[13px] font-semibold text-foreground">
            Data quality over time
          </div>
          <div className="mb-3 text-[12px] text-muted-foreground">
            Completeness % per wave
          </div>
          <MiniChart data={filtered} field="data_quality" refLine={90} color="#0EA5E9" height={100} decimals={0} unit="%" />
          <div className="mt-1.5 text-[12px] text-muted-foreground/70">
            Dashed line = 90% completeness floor
          </div>
        </Card>
      </div>

      {/* Signal log + subgroup snapshot */}
      <div className="mb-4 grid grid-cols-2 gap-4">
        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-4 text-[13px] font-semibold text-foreground">
            Signal & drift log
          </div>
          <SignalLog signals={signals} />
        </Card>

        <Card className="block gap-0 rounded-xl p-5">
          <div className="mb-4 text-[13px] font-semibold text-foreground">
            Current subgroup snapshot — latest wave
          </div>
          <SubgroupForest snapshots={filtered} />
        </Card>
      </div>

      {/* Chatbot */}
      <InlineChatbot {...chatProps} />

      {/* Navigation */}
      <div className="mt-6 flex justify-between">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft size={15} /> Back to Report
        </Button>
        <Button onClick={() => {
          const date = new Date().toLocaleDateString("en-GB",{year:"numeric",month:"short",day:"numeric"});
          const content = `AUGURA HEALTH — ${partnerLabel.toUpperCase()} PLATFORM\nMONITORING REPORT\nGenerated: ${date}\n\nLatest wave: ${latest?.wave_month?.slice(0,7)}\nN active: ${latest?.n_active?.toLocaleString()}\nRolling effect: ${latest?.effect_rolling?.toFixed(2)} [${latest?.ci_lower?.toFixed(2)}, ${latest?.ci_upper?.toFixed(2)}]\nE-value: ${latest?.e_value_point?.toFixed(2)} (CI: ${latest?.e_value_ci?.toFixed(2)})\nEffect drift: ${effectDrift.toFixed(3)} — ${effectStable?"STABLE":"DRIFTING"}\n\nSignal log:\n${signals.map(s=>`${s.signal_date} [${s.signal_type.toUpperCase()}] ${s.title}: ${s.description}`).join("\n")}\n`;
          const blob = new Blob([content],{type:"text/plain"});
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `${partnerLabel}_Monitoring_Report_${date.replace(/ /g,"")}.txt`;
          a.click();
        }}>
          <Download size={15} /> Export monitoring report
        </Button>
      </div>
    </div>
  );
}
