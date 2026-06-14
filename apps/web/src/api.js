// Client API d'Augura — fondation du rebranchement front → FastAPI.
// Chaque appel porte le JWT Supabase courant en Authorization: Bearer (porte
// unique, spec §7). Base : VITE_API_URL (domaine Modal en prod, localhost en dev).
//
// Les vues sont rebranchées une à une sur ces helpers (studies, corpus, datasets,
// agents, simulations…) en remplacement des anciens fetch('/api/*') + lectures
// Supabase REST directes. Les types canoniques vivent dans packages/api-client.
import { supabase } from './supabase'

const API_BASE = import.meta.env.VITE_API_URL || ''

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
  if (opts.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
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
