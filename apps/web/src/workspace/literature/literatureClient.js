// apps/web/src/workspace/literature/literatureClient.js
//
// Client du workbench Littérature, branché sur le vrai backend FastAPI :
//   - retrieve  → POST /corpus/literature/retrieve (stream NDJSON: meta|group|done)
//   - sessions  → POST/GET /corpus/literature/sessions(+events)   (Recent queries + audit)
//   - snapshots → POST/GET /corpus/literature/snapshots(/{id})    (Saved evidence)
//   - ingest    → POST /corpus/literature/ingest                  (Add to corpus, PubMed)
// Pas de mode démo, pas de localStorage : tout vient du backend (règle no-mock).
import { apiFetch, apiJson } from '@/api'

// id stable d'un résultat across sources (pmid pour PubMed, nct_id pour CT.gov).
export const resultId = (r) => r.pmid || r.nct_id || r.id || ''

// Aplati un item backend (record imbriqué) → forme plate attendue par les cartes
// (r.pmid, r.abstract…). Conserve source/id/query_string/retrieval_date/record pour
// reconstruire un FrozenResult au moment du Save.
export function flattenItem(item) {
  const rec = item.record || {}
  return {
    source: item.source,
    id: item.id,
    title: item.title,
    query_string: item.query_string,
    retrieval_date: item.retrieval_date,
    record: rec,
    annotation: item.annotation ?? null,
    ...rec,
    publication_date: rec.published_at ?? null,
  }
}

// Stream NDJSON du retrieve. onEvent reçoit {type:'meta'|'group'|'done'|'error', ...}.
export async function streamRetrieve({ query, sources, dateRange, studyTypes, maxResults = 10, signal, onEvent }) {
  const body = JSON.stringify({
    query,
    sources: sources && sources.length ? sources : undefined,
    date_range: dateRange || 'any',
    study_types: studyTypes || [],
    max_results: maxResults,
  })
  let res
  try {
    res = await apiFetch('/corpus/literature/retrieve', { method: 'POST', body, signal })
  } catch (e) {
    if (e?.name === 'AbortError') return
    onEvent({ type: 'error', text: String(e?.message || e) })
    return
  }
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '')
    onEvent({ type: 'error', text: `HTTP ${res.status} ${detail.slice(0, 200)}` })
    return
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  const emit = (raw) => { try { onEvent(JSON.parse(raw)) } catch { /* ligne partielle */ } }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) { const raw = line.trim(); if (raw) emit(raw) }
    }
    if (buf.trim()) emit(buf.trim())
  } catch (e) {
    if (e?.name !== 'AbortError') onEvent({ type: 'error', text: String(e?.message || e) })
  }
}

// ── Sessions (Recent queries) — historique serveur ───────────────────────────
export const createSession = (query, studyId = null) =>
  apiJson('/corpus/literature/sessions', {
    method: 'POST',
    body: JSON.stringify({ query, study_id: studyId }),
  })

export const listSessions = () => apiJson('/corpus/literature/sessions')

// Best-effort : ne jette jamais (l'audit ne doit pas casser le flux).
export const logEvent = (sessionId, eventType, payload = {}) =>
  apiFetch(`/corpus/literature/sessions/${sessionId}/events`, {
    method: 'POST',
    body: JSON.stringify({ event_type: eventType, payload }),
  }).then((r) => r.ok).catch(() => false)

// ── Snapshots (Saved evidence) ────────────────────────────────────────────────
const MODEL_VERSION = 'retrieve'
const PROMPT_VERSION = 'v1'

export function saveSnapshot({ query, sources, studyId = null, items }) {
  const results = items.map((r) => ({
    source: r.source,
    id: r.id,
    title: r.title,
    query_string: r.query_string,
    retrieval_date: r.retrieval_date,
    record: r.record,
    annotation: r.annotation ?? null,
  }))
  return apiJson('/corpus/literature/snapshots', {
    method: 'POST',
    body: JSON.stringify({
      query,
      sources,
      model_version: MODEL_VERSION,
      prompt_version: PROMPT_VERSION,
      study_id: studyId,
      results,
    }),
  })
}

// studyId optionnel : filtre les snapshots gelés rattachés à une étude (vue
// « Saved evidence » scopée étude). Sans argument → tous les snapshots du tenant.
export const listSnapshots = (studyId = null) =>
  apiJson('/corpus/literature/snapshots' + (studyId ? `?study_id=${encodeURIComponent(studyId)}` : ''))
export const getSnapshot = (id) => apiJson(`/corpus/literature/snapshots/${id}`)

// ── Add to corpus (PubMed only) ───────────────────────────────────────────────
export const ingestPmids = (pmids) =>
  apiJson('/corpus/literature/ingest', { method: 'POST', body: JSON.stringify({ pmids }) })
