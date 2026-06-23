// apps/web/src/workspace/literature/literatureClient.js
//
// Literature workbench client, wired to the real FastAPI backend:
//   - retrieve  → POST /corpus/literature/retrieve (stream NDJSON: meta|group|done)
//   - sessions  → POST/GET /corpus/literature/sessions(+events)   (Recent queries + audit)
//   - snapshots → POST/GET /corpus/literature/snapshots(/{id})    (Saved evidence)
//   - ingest    → POST /corpus/literature/ingest                  (Add to corpus, PubMed)
// No demo mode, no localStorage: everything comes from the backend (no-mock rule).
import { apiFetch, apiJson } from '@/api'

// Stable id of a result across sources (pmid for PubMed, nct_id for CT.gov).
export const resultId = (r) => r.pmid || r.nct_id || r.id || ''

// Flattens a backend item (nested record) → flat shape expected by the cards
// (r.pmid, r.abstract…). Keeps source/id/query_string/retrieval_date/record to
// rebuild a FrozenResult at Save time.
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
    rationale: item.rationale ?? null,
    ...rec,
    publication_date: rec.published_at ?? null,
  }
}

// NDJSON stream of the retrieve. onEvent receives {type:'meta'|'group'|'done'|'error', ...}.
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
  const emit = (raw) => { try { onEvent(JSON.parse(raw)) } catch { /* partial line */ } }
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

// ── Sessions (Recent queries) — server-side history ──────────────────────────
export const createSession = (query, studyId = null) =>
  apiJson('/corpus/literature/sessions', {
    method: 'POST',
    body: JSON.stringify({ query, study_id: studyId }),
  })

export const listSessions = () => apiJson('/corpus/literature/sessions')

// History deletion (Recent queries). Best-effort: returns an ok boolean.
export const deleteSession = (id) =>
  apiFetch(`/corpus/literature/sessions/${id}`, { method: 'DELETE' }).then((r) => r.ok).catch(() => false)
export const clearSessions = () =>
  apiFetch('/corpus/literature/sessions', { method: 'DELETE' }).then((r) => r.ok).catch(() => false)

// Best-effort: never throws (the audit must not break the flow).
export const logEvent = (sessionId, eventType, payload = {}) =>
  apiFetch(`/corpus/literature/sessions/${sessionId}/events`, {
    method: 'POST',
    body: JSON.stringify({ event_type: eventType, payload }),
  }).then((r) => r.ok).catch(() => false)

// ── Snapshots (Saved evidence) ────────────────────────────────────────────────
const MODEL_VERSION = 'retrieve'
const PROMPT_VERSION = 'v1'

export function saveSnapshot({ query, sources, studyId = null, items, modelVersion = MODEL_VERSION, promptVersion = PROMPT_VERSION }) {
  const results = items.map((r) => ({
    source: r.source,
    id: r.id,
    title: r.title,
    query_string: r.query_string,
    retrieval_date: r.retrieval_date,
    record: r.record,
    annotation: r.annotation ?? null,
    rationale: r.rationale ?? null,
  }))
  return apiJson('/corpus/literature/snapshots', {
    method: 'POST',
    body: JSON.stringify({
      query,
      sources,
      model_version: modelVersion,
      prompt_version: promptVersion,
      study_id: studyId,
      results,
    }),
  })
}

// studyId optional: filters the frozen snapshots linked to a study (study-scoped
// "Saved evidence" view). Without an argument → all snapshots of the tenant.
export const listSnapshots = (studyId = null) =>
  apiJson('/corpus/literature/snapshots' + (studyId ? `?study_id=${encodeURIComponent(studyId)}` : ''))
export const getSnapshot = (id) => apiJson(`/corpus/literature/snapshots/${id}`)

// ── Add to corpus (PubMed only) ───────────────────────────────────────────────
export const ingestPmids = (pmids) =>
  apiJson('/corpus/literature/ingest', { method: 'POST', body: JSON.stringify({ pmids }) })
