// ClinicalTrials.gov relay — Supabase Edge Function (egress not blocked by the CT.gov WAF).
//
// Why: the CT.gov WAF returns 403 to Modal datacenter IPs (backend). Supabase Edge
// egress is not blocked → we re-issue the CT.gov v2 calls here, and the Modal backend
// calls this relay (AUGURA_CTGOV_RELAY_URL) instead of CT.gov directly.
//
// Upstream LOCKED to the CT.gov studies endpoint (not an open proxy):
//   GET /functions/v1/ctgov            → https://clinicaltrials.gov/api/v2/studies
//   GET /functions/v1/ctgov/NCT012345  → https://clinicaltrials.gov/api/v2/studies/NCT012345
// The query params (query.term, pageSize, format, filters) are forwarded as-is.
//
// Public (verify_jwt=false): read-only access to public data, locked upstream.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const UPSTREAM = "https://clinicaltrials.gov/api/v2/studies";
const MARKER = "/ctgov";

Deno.serve(async (req: Request) => {
  if (req.method !== "GET") {
    return new Response(JSON.stringify({ error: "method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  const url = new URL(req.url);
  // Sub-path after the function name: "" (search) or "/NCT012345" (fetch by id).
  const idx = url.pathname.indexOf(MARKER);
  let sub = idx >= 0 ? url.pathname.slice(idx + MARKER.length) : "";
  if (sub === "/") sub = "";

  const upstream = new URL(UPSTREAM + sub);
  for (const [k, v] of url.searchParams) upstream.searchParams.set(k, v);

  try {
    const upstreamRes = await fetch(upstream.toString(), {
      headers: { Accept: "application/json", "User-Agent": "Augura/1.0 (ctgov-relay)" },
    });
    const body = await upstreamRes.text();
    return new Response(body, {
      status: upstreamRes.status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "s-maxage=300, stale-while-revalidate=600",
      },
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "ctgov relay failed", detail: String(err) }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }
});
