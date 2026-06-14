import { useState } from "react";
import { C, FONT, MONO } from "../theme";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card as ShadCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

// ── Shared micro-components (shadcn-backed; same API as before) ───────────────

// ── Tag → Badge ───────────────────────────────────────────────────────────────
const TAG_CLASS = {
  g: "bg-[#EAF3DE] text-[#27500A] border-[#97C459]",
  r: "bg-[#FCEBEB] text-[#791F1F] border-[#F09595]",
  b: "bg-[#E6F1FB] text-[#0C447C] border-[#85B7EB]",
  a: "bg-[#FAEEDA] text-[#633806] border-[#EF9F27]",
  p: "bg-[#EEEDFE] text-[#3C3489] border-[#AFA9EC]",
};
export const Tag = ({ children, color = "b" }) => (
  <Badge
    variant="outline"
    className={cn(
      "mt-px mr-0.5 rounded-lg border px-2 py-0.5 text-[11px] font-medium",
      TAG_CLASS[color] || TAG_CLASS.b,
    )}
  >
    {children}
  </Badge>
);

// ── Pill → Badge ──────────────────────────────────────────────────────────────
const PILL_CLASS = {
  KB: "bg-[#E6F1FB] text-[#0C447C] border-[#85B7EB]",
  L: "bg-[#E1F5EE] text-[#085041] border-[#5DCAA5]",
  "KB+L": "bg-[#EEEDFE] text-[#3C3489] border-[#AFA9EC]",
};
export const Pill = ({ children, type = "KB" }) => (
  <Badge
    variant="outline"
    className={cn(
      "rounded-lg border px-2 py-0.5 text-[10.5px] font-semibold",
      PILL_CLASS[type] || PILL_CLASS.KB,
    )}
  >
    {children}
  </Badge>
);

// ── SourcePill → Badge ────────────────────────────────────────────────────────
const SOURCE_CLASS = {
  MAUDE: "bg-[#FEF9C3] text-[#713F12] border-[#FDE047]",
  PubMed: "bg-[#FCE7F3] text-[#831843] border-[#F9A8D4]",
  "ClinicalTrials.gov": "bg-[#E0F2FE] text-[#075985] border-[#7DD3FC]",
  "FDA Guidance": "bg-[#FEF3C7] text-[#92400E] border-[#FCD34D]",
};
export const SourcePill = ({ name }) => (
  <Badge
    variant="outline"
    className={cn(
      "rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
      SOURCE_CLASS[name] || "bg-[#E6F1FB] text-[#0C447C] border-[#85B7EB]",
    )}
  >
    {name}
  </Badge>
);

// ── Card → shadcn Card (style passthrough preserved) ──────────────────────────
export const Card = ({ children, style = {} }) => (
  <ShadCard className="block gap-0 p-4 px-5" style={style}>
    {children}
  </ShadCard>
);

// ── Btn → Button (primary = solid green; sizes kept compatible) ───────────────
export const Btn = ({ children, onClick, primary, small, disabled, style = {} }) => (
  <Button
    variant={primary ? "default" : "outline"}
    size={small ? "sm" : "default"}
    onClick={onClick}
    disabled={disabled}
    style={style}
    className="text-xs font-medium"
  >
    {children}
  </Button>
);

// ── InfoBar → Alert ───────────────────────────────────────────────────────────
export const InfoBar = ({ children, sources = [] }) => (
  <Alert className="mb-5 border-border bg-secondary/40">
    <Info className="text-primary" />
    <AlertDescription className="text-[13px] leading-relaxed text-foreground/80">
      <div>{children}</div>
      {sources.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {sources.map((s) => (
            <SourcePill key={s} name={s} />
          ))}
        </div>
      )}
    </AlertDescription>
  </Alert>
);

// ── Radar (SVG) ───────────────────────────────────────────────────────────────
export function Radar({ labels, datasets, size = 220, maxVal = 5 }) {
  const cx = size/2, cy = size/2, r = size*0.34;
  const n = labels.length;
  const ang = i => (i*2*Math.PI/n) - Math.PI/2;
  const pt  = (val, i) => ({
    x: cx + r*(val/maxVal)*Math.cos(ang(i)),
    y: cy + r*(val/maxVal)*Math.sin(ang(i)),
  });
  const rings = maxVal === 100 ? [20,40,60,80,100] : [1,2,3,4,5];
  return (
    <svg width={size} height={size}>
      {rings.map(lv => (
        <polygon key={lv} fill="none" stroke={C.border} strokeWidth={0.5}
          points={labels.map((_,i)=>{const p=pt(lv,i);return`${p.x},${p.y}`;}).join(" ")} />
      ))}
      {labels.map((_,i)=>{const p=pt(maxVal,i);return(
        <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke={C.border} strokeWidth={0.5}/>
      );})}
      {datasets.map((ds,di)=>(
        <polygon key={di}
          fill={`${ds.stroke}18`} stroke={ds.stroke} strokeWidth={1.5}
          opacity={ds.dash?0.6:1}
          style={ds.dash?{strokeDasharray:"4 3"}:{}}
          points={ds.data.map((v,i)=>{const p=pt(v,i);return`${p.x},${p.y}`;}).join(" ")} />
      ))}
      {labels.map((lbl,i)=>{
        const p=pt(maxVal*1.18,i);
        const words=lbl.split(/\n/);
        return(
          <text key={i} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="central"
            fontSize={8.5} fill={C.muted} fontFamily={FONT}>
            {words.map((w,wi)=><tspan key={wi} x={p.x} dy={wi===0?0:10}>{w}</tspan>)}
          </text>
        );
      })}
    </svg>
  );
}

// ── Score bar ─────────────────────────────────────────────────────────────────
const SCORE_TOOLTIP = [
  "0 — No evidence of risk",
  "1 — Negligible risk",
  "2 — Low risk · manageable",
  "3 — Moderate risk · attention needed",
  "4 — High risk · mitigation required",
  "5 — Critical risk · may block study",
].join("\n");

export const ScoreBar = ({ score, color, max=5, tooltipOverride }) => (
  <div style={{ display:"flex", alignItems:"center", gap:6 }}>
    <div style={{ width:52, height:4, background:"#e8e6df", borderRadius:2, overflow:"hidden" }}>
      <div style={{ height:"100%", width:`${(score/max)*100}%`, background:color, borderRadius:2 }} />
    </div>
    <span title={tooltipOverride || SCORE_TOOLTIP}
      style={{ fontSize:10, color:C.faint, fontFamily:MONO, cursor:"help", borderBottom:"0.5px dotted #C4C2BA" }}>
      {score}/{max}
    </span>
  </div>
);

// ── Expandable intel row ──────────────────────────────────────────────────────
export function IntelRow({ label, score, scoreColor, delta, deltaDir, source, preliminary, max=5, children }) {
  const [open, setOpen] = useState(false);
  const dc = deltaDir==="better" ? "#27500A" : deltaDir==="worse" ? "#A32D2D" : "#854F0B";
  return (
    <>
      <tr onClick={()=>setOpen(!open)} style={{ cursor:"pointer" }}
        onMouseEnter={e=>e.currentTarget.style.background="#f5f4f0"}
        onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
        <td style={{ padding:"7px 8px", fontSize:11.5, color:C.text, borderBottom:`0.5px solid ${C.border}` }}>
          <span style={{ marginRight:6, fontSize:9, color:C.faint, display:"inline-block",
            transform:open?"rotate(90deg)":"none", transition:"transform .2s" }}>▶</span>
          {label}
          {preliminary && (
            <span style={{ marginLeft:6, fontSize:8.5, fontWeight:600, fontFamily:MONO,
              background:"#FFF3CD", color:"#854F0B", border:"0.5px solid #EF9F27",
              borderRadius:4, padding:"1px 5px", verticalAlign:"middle" }}>
              Preliminary
            </span>
          )}
        </td>
        <td style={{ padding:"7px 8px", borderBottom:`0.5px solid ${C.border}` }}>
          <ScoreBar score={score} color={scoreColor} max={max} />
        </td>
        {delta !== undefined && (
          <td style={{ padding:"7px 8px", fontSize:10, fontWeight:700, color:dc,
            borderBottom:`0.5px solid ${C.border}` }}>{delta}</td>
        )}
        {source !== undefined && (
          <td style={{ padding:"7px 8px", borderBottom:`0.5px solid ${C.border}` }}>
            <Pill type={source}>{source}</Pill>
          </td>
        )}
      </tr>
      {open && (
        <tr style={{ background:C.surface2 }}>
          <td colSpan={4} style={{ padding:"10px 14px", borderBottom:`0.5px solid ${C.border}` }}>
            <div style={{ display:"flex", flexDirection:"column", gap:8 }}>{children}</div>
          </td>
        </tr>
      )}
    </>
  );
}

export const IntelBlock = ({ label, children }) => (
  <div style={{ display:"flex", gap:10 }}>
    <span style={{ fontSize:9.5, fontWeight:700, color:C.faint, textTransform:"uppercase",
      letterSpacing:".04em", minWidth:82, paddingTop:2, flexShrink:0, fontFamily:MONO }}>
      {label}
    </span>
    <div style={{ fontSize:11, color:C.sub, lineHeight:1.6 }}>{children}</div>
  </div>
);

// ── Sparkline ─────────────────────────────────────────────────────────────────
export const Spark = ({ data, color }) => {
  const w=100, h=32, max=Math.max(...data), min=Math.min(...data), range=max-min||1;
  const pts=data.map((v,i)=>{
    const x=(i/(data.length-1))*w;
    const y=h-((v-min)/range)*(h-6)-3;
    return`${x},${y}`;
  }).join(" ");
  const [lx,ly]=pts.split(" ").pop().split(",");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"
      style={{ width:"100%", height:32, marginTop:6 }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5}
        strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx={lx} cy={ly} r={2.5} fill={color}/>
    </svg>
  );
};

// ── Mini line chart ───────────────────────────────────────────────────────────
export function MiniLineChart({ series, height=90 }) {
  const w=300, h=height;
  const allVals=series.flatMap(s=>s.data);
  const max=Math.max(...allVals)*1.05, min=Math.min(...allVals)*0.95, range=max-min||1;
  const px=(v,i,len)=>((i/(len-1))*w);
  const py=(v)=>(h-((v-min)/range)*(h-8)-4);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"
      style={{ width:"100%", height }}>
      {series.map((s,si)=>{
        const pts=s.data.map((v,i)=>`${px(v,i,s.data.length)},${py(v)}`).join(" ");
        const [lx,ly]=pts.split(" ").pop().split(",");
        return (
          <g key={si}>
            {s.fill && (
              <polygon fill={`${s.color}18`}
                points={`0,${h} ${pts} ${px(0,s.data.length-1,s.data.length)},${h}`} />
            )}
            <polyline points={pts} fill="none" stroke={s.color} strokeWidth={s.dash?1:1.5}
              style={s.dash?{strokeDasharray:"4 3"}:{}}
              strokeLinecap="round" strokeLinejoin="round"/>
            {!s.dash && <circle cx={lx} cy={ly} r={2.5} fill={s.color}/>}
          </g>
        );
      })}
    </svg>
  );
}
