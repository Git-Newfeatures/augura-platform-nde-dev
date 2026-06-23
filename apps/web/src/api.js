// Augura API client — foundation of the frontend → FastAPI rewiring.
// Every call carries the current Supabase JWT in Authorization: Bearer (single
// gate, spec §7). Base: VITE_API_URL (Modal domain in prod, localhost in dev).
//
// Views are rewired one by one onto these helpers (studies, corpus, datasets,
// agents, simulations…) replacing the old fetch('/api/*') + direct Supabase
// REST reads. The canonical types live in packages/api-client.
import { supabase } from './supabase'

// Prod fallback = Modal backend. Overridden by VITE_API_URL when it is set
// (http://localhost:8000 in dev via .env.local, or a Vercel project env var).
// Prevents the prod build from hitting the front origin relatively → 404.
const FALLBACK_API_BASE = 'https://quentin-45919--augura-api-api.modal.run'
const API_BASE = import.meta.env.VITE_API_URL || FALLBACK_API_BASE

if (!import.meta.env.VITE_API_URL) {
  console.warn(
    `[augura] VITE_API_URL not set — falling back to the default Modal backend (${FALLBACK_API_BASE}). ` +
      'Set VITE_API_URL to target a different backend (e.g. http://localhost:8000 in dev).',
  )
}

export async function getAccessToken() {
  try {
    const { data } = await supabase.auth.getSession()
    return data?.session?.access_token ?? null
  } catch {
    return null
  }
}

export async function apiFetch(path, opts = {}) {
  const token = await getAccessToken()
  const headers = new Headers(opts.headers || {})
  if (token) headers.set('Authorization', `Bearer ${token}`)
  // FormData (file upload) must keep the browser-set multipart boundary — never force JSON.
  const isFormData = typeof FormData !== 'undefined' && opts.body instanceof FormData
  if (opts.body && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers })
  return res
}

export async function apiJson(path, opts = {}) {
  const res = await apiFetch(path, opts)
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`API ${res.status} ${path}: ${detail.slice(0, 300)}`)
  }
  return res.json()
}
