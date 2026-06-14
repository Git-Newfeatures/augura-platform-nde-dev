// layout.jsx — shared responsive layout primitives.
// These encode the app's breakpoints ONCE so every surface composes from the
// same parts instead of hand-rolling fixed-pixel flex rows (the root cause of
// the horizontal-overflow bugs). Desktop appearance is unchanged; the primitives
// only add graceful reflow/stacking below lg/md.
//
// All accept `className` (merged via twMerge, so callers can override defaults)
// and spread the rest onto the root node.
import { cn } from "@/lib/utils";
import { useBreakpoint } from "@/lib/useBreakpoint";

// ── Page — fluid, centered page container with responsive horizontal padding.
// Use on surfaces that DON'T already sit inside AppShell's max-w container
// (study workspace, modals, auth). `narrow` for reading-width content.
export function Page({ children, className, narrow = false, ...rest }) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-4 sm:px-5 md:px-6",
        narrow ? "max-w-[920px]" : "max-w-[1280px]",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

// ── PageHeader — title cluster + actions that wrap instead of overflowing.
export function PageHeader({ title, subtitle, eyebrow, actions, className, ...rest }) {
  return (
    <div className={cn("mb-5 flex flex-wrap items-end justify-between gap-x-4 gap-y-3", className)} {...rest}>
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[.09em] text-primary">
            {eyebrow}
          </div>
        )}
        {title && (
          <h1 className="text-2xl font-bold tracking-tight text-foreground md:text-[28px]">{title}</h1>
        )}
        {subtitle && <div className="mt-1 text-sm text-muted-foreground">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

// ── Section — titled block with an optional actions slot.
export function Section({ title, actions, children, className, ...rest }) {
  return (
    <section className={cn("mb-6", className)} {...rest}>
      {(title || actions) && (
        <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-foreground">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

// ── Stack — vertical flex with a default gap (override via className gap-*).
export function Stack({ children, className, ...rest }) {
  return (
    <div className={cn("flex flex-col gap-4", className)} {...rest}>
      {children}
    </div>
  );
}

// ── Cluster — horizontal flex that WRAPS. Replaces fixed rows that overflowed.
export function Cluster({ children, className, ...rest }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-3", className)} {...rest}>
      {children}
    </div>
  );
}

// ── AutoGrid — responsive card grid with NO breakpoints needed.
// `repeat(auto-fit, minmax(min(100%, Npx), 1fr))` reflows columns to fit and the
// inner `min(100%, …)` guarantees a single column never overflows its container.
export function AutoGrid({ children, min = 240, className, style, ...rest }) {
  return (
    <div
      className={cn("grid gap-4", className)}
      style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${min}px), 1fr))`, ...style }}
      {...rest}
    >
      {children}
    </div>
  );
}

// ── Split — sidebar + content that stacks vertically below `stackBelow`.
// JS-driven (useBreakpoint) so the sidebar width + direction are exact and the
// content always carries `min-w-0` (kills the flexbox min-width:auto overflow).
export function Split({
  side,
  children,
  sideWidth = 280,
  stackBelow = "lg",
  gap = 20,
  className,
  sideClassName,
  contentClassName,
  style,
  ...rest
}) {
  const bp = useBreakpoint();
  const stacked = !bp[stackBelow];
  return (
    <div
      className={cn("flex", className)}
      style={{ flexDirection: stacked ? "column" : "row", gap, ...style }}
      {...rest}
    >
      <aside
        className={cn(sideClassName)}
        style={{ width: stacked ? "100%" : sideWidth, flexShrink: 0 }}
      >
        {side}
      </aside>
      <div className={cn("min-w-0 flex-1", contentClassName)}>{children}</div>
    </div>
  );
}

// ── ScrollX — horizontal-scroll container (thin scrollbar) for wide tables /
// tab strips, so the CONTENT scrolls instead of the whole page overflowing.
export function ScrollX({ children, className, ...rest }) {
  return (
    <div className={cn("scrollbar-thin -mx-1 overflow-x-auto px-1", className)} {...rest}>
      {children}
    </div>
  );
}
