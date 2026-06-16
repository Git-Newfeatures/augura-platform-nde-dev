// primitives.jsx — cockpit primitives, shadcn-backed (same API as before so all
// consumers keep working). Card → shadcn Card, Pill/Tag → Badge, Ghost → Button.
import { Card as ShadCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Card — surface; callers may pass `style` (e.g. custom padding/borderColor) which
// overrides the defaults, and/or `className`.
export function Card({ children, style, className }) {
  return (
    <ShadCard className={cn("block gap-0 p-4 px-5", className)} style={style}>
      {children}
    </ShadCard>
  );
}

// Eyebrow — tiny uppercase label
export function Eyebrow({ children, color }) {
  return (
    <div
      className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/60"
      style={color ? { color } : undefined}
    >
      {children}
    </div>
  );
}

// Pill — rounded badge (kind: "active" | "flag" | "new" | plain)
const PILL = {
  active: "bg-secondary text-primary",
  flag:   "bg-[#FAEEDA] text-[#9A7200]",
  new:    "bg-secondary text-primary",
};
export function Pill({ children, kind }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border-transparent px-2 py-0.5 text-[11px] font-semibold",
        PILL[kind] || "bg-black/[0.06] text-muted-foreground",
      )}
    >
      {kind === "flag" ? "⚑ Attention" : children}
    </Badge>
  );
}

// Tag — small metadata badge
const TAG = {
  neutral: "bg-black/[0.05] text-muted-foreground",
  emerald: "bg-secondary text-primary",
};
export function Tag({ children, tone = "neutral", style }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border-transparent px-[9px] py-[3px] text-[11.5px] font-medium",
        TAG[tone] || TAG.neutral,
      )}
      style={style}
    >
      {children}
    </Badge>
  );
}

// Ghost — button (primary = filled, default = outline)
export function Ghost({ children, primary, onClick, style }) {
  return (
    <Button
      variant={primary ? "default" : "outline"}
      size="sm"
      onClick={onClick}
      style={style}
      className="rounded-full text-[13px] font-semibold"
    >
      {children}
    </Button>
  );
}
