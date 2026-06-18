// Client API d'Augura — fondation du rebranchement front → FastAPI.
// Chaque appel porte le JWT Supabase courant en Authorization: Bearer (porte
// unique, spec §7). Base : VITE_API_URL (domaine Modal en prod, localhost en dev).
//
// Les vues sont rebranchées une à une sur ces helpers (studies, corpus, datasets,
// agents, simulations…) en remplacement des anciens fetch('/api/*') + lectures
// Supabase REST directes. Les types canoniques vivent dans packages/api-client.
import { supabase } from './supabase'

// Repli prod = backend Modal. Surchargé par VITE_API_URL quand il est défini
// (http://localhost:8000 en dev via .env.local, ou une env var du projet Vercel).
// Évite que le build prod tape en relatif sur l'origine du front → 404.
const FALLBACK_API_BASE = 'https://quentin-45919--augura-api-api.modal.run'
const API_BASE = import.meta.env.VITE_API_URL || FALLBACK_API_BASE

if (!import.meta.env.VITE_API_URL) {
  console.warn(
    `[augura] VITE_API_URL non défini — repli sur le backend Modal par défaut (${FALLBACK_API_BASE}). ` +
      'Définis VITE_API_URL pour cibler un autre backend (ex. http://localhost:8000 en dev).',
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
