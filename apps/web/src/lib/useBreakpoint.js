// useBreakpoint — single source of truth for JS-driven responsive decisions.
// Mirrors Tailwind's default breakpoints so CSS (md:/lg:/xl:) and JS agree.
// Returns booleans for "viewport is AT LEAST this width":
//   bp.md → ≥768px (tablet+), bp.lg → ≥1024px (laptop+), bp.xl → ≥1280px (desktop)
// "below lg" is simply !bp.lg.
import { useState, useEffect } from "react";

const QUERIES = {
  md: "(min-width: 768px)",
  lg: "(min-width: 1024px)",
  xl: "(min-width: 1280px)",
};

function read() {
  if (typeof window === "undefined" || !window.matchMedia) {
    // SSR / non-browser fallback: assume desktop so layout doesn't flash narrow.
    return { md: true, lg: true, xl: true };
  }
  return {
    md: window.matchMedia(QUERIES.md).matches,
    lg: window.matchMedia(QUERIES.lg).matches,
    xl: window.matchMedia(QUERIES.xl).matches,
  };
}

export function useBreakpoint() {
  const [bp, setBp] = useState(read);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mqls = Object.values(QUERIES).map((q) => window.matchMedia(q));
    const onChange = () => setBp(read());
    mqls.forEach((m) => m.addEventListener("change", onChange));
    return () => mqls.forEach((m) => m.removeEventListener("change", onChange));
  }, []);

  return bp;
}
