// Relais ClinicalTrials.gov — Supabase Edge Function (egress non bloqué par le WAF CT.gov).
//
// Pourquoi : le WAF de CT.gov renvoie 403 aux IP datacenter de Modal (backend). L'egress
// Supabase Edge n'est pas bloqué → on réémet les appels CT.gov v2 par ici, et le backend
// Modal appelle ce relais (AUGURA_CTGOV_RELAY_URL) au lieu de CT.gov directement.
//
// Upstream VERROUILLÉ sur l'endpoint studies de CT.gov (pas un proxy ouvert) :
//   GET /functions/v1/ctgov            → https://clinicaltrials.gov/api/v2/studies
//   GET /functions/v1/ctgov/NCT012345  → https://clinicaltrials.gov/api/v2/studies/NCT012345
// Les query params (query.term, pageSize, format, filtres) sont transmis tels quels.
//
// Public (verify_jwt=false) : lecture seule de données publiques, upstream verrouillé.
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
  // Sous-chemin après le nom de la fonction : "" (search) ou "/NCT012345" (fetch par id).
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
