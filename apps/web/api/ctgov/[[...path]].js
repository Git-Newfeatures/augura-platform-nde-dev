// Relais serverless ClinicalTrials.gov (Vercel / egress AWS).
//
// Pourquoi : le WAF de CT.gov renvoie 403 aux IP datacenter de Modal (backend).
// L'egress Vercel n'est PAS bloqué → on relaie les appels CT.gov v2 par ici, et le
// backend Modal appelle ce relais au lieu de CT.gov directement.
//
// Upstream VERROUILLÉ sur l'endpoint studies de CT.gov (pas un proxy ouvert) :
//   GET /api/ctgov            → https://clinicaltrials.gov/api/v2/studies
//   GET /api/ctgov/NCT012345  → https://clinicaltrials.gov/api/v2/studies/NCT012345
// Les query params (query.term, pageSize, format, filtres) sont transmis tels quels.

const UPSTREAM_BASE = 'https://clinicaltrials.gov/api/v2/studies'

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method not allowed' })
    return
  }

  // Segments de chemin après /api/ctgov (catch-all optionnel → req.query.path).
  const seg = req.query.path
  const suffix = Array.isArray(seg) && seg.length ? '/' + seg.map(encodeURIComponent).join('/') : ''
  const upstream = new URL(UPSTREAM_BASE + suffix)

  // Recopie les query params (sauf `path`, injecté par le routage catch-all).
  for (const [k, v] of Object.entries(req.query)) {
    if (k === 'path') continue
    upstream.searchParams.set(k, Array.isArray(v) ? v[0] : v)
  }

  try {
    const upstreamRes = await fetch(upstream, {
      headers: { Accept: 'application/json', 'User-Agent': 'Augura/1.0 (ctgov-relay)' },
    })
    const body = await upstreamRes.text()
    res.status(upstreamRes.status)
    res.setHeader('Content-Type', 'application/json; charset=utf-8')
    // Cache court côté edge : amortit les requêtes répétées sans périmer la fraîcheur.
    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=600')
    res.send(body)
  } catch (err) {
    res.status(502).json({ error: 'ctgov relay failed', detail: String(err && err.message) })
  }
}
