// dataClient.js — the real data layer for the Evidence Workspace.
//
//   Every collection is fetched through the FastAPI backend (apiJson →
//   Authorization: Bearer <supabase jwt> → tenant-scoped RLS → Postgres).
//   An empty/missing collection yields [] so the UI renders an EmptyState
//   ("blank when not wired"). The front never talks to PostgREST directly —
//   every read crosses the backend.
import { useState, useEffect } from 'react'
import { apiJson } from '@/api'
import { studyFromRow } from '@/cockpit/cockpitData'

// ── Normalizers : backend response → the exact shape each workspace view renders.

const SOURCE_META = {
  pubmed:         { name: 'PubMed',             icon: 'book'   },
  clinicaltrials: { name: 'ClinicalTrials.gov', icon: 'flask'  },
  ctgov:          { name: 'ClinicalTrials.gov', icon: 'flask'  },
  maude:          { name: 'MAUDE',              icon: 'shield' },
  guidance:       { name: 'FDA Guidance',       icon: 'page'   },
}

const humanize = (s) =>
  String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

// "2026-06-14T15:17Z" → "2h ago" / "3d ago" / "Just now".
const relTime = (iso) => {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return '—'
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}

const normStudies = (rows) =>
  (rows ?? []).map((r) => studyFromRow({ ...r, n: r.n_subjects ?? r.n }))

// study label resolved from the studies collection (backend keeps datasets↔studies
// independent, so /datasets carries study_id, not study_name).
const normDatasets = (rows, studyNameById = new Map()) =>
  (rows ?? []).map((d) => ({
    id: d.id,
    name: d.name,
    rows: d.row_count != null ? d.row_count.toLocaleString() : '—',
    cols: d.column_count ?? '—',
    study: studyNameById.get(d.study_id) ?? '',
    state: d.status ?? 'pending',
    when: relTime(d.created_at),
  }))

// Simulation runs → the exact shape RunsPage / HomePage "Recent runs" render.
// summary.recommended_power is a 0–100 percentage; the UI multiplies by 100, so we
// store it as a 0–1 fraction. `studyId` drives navigation, `study` is the display label.
const normRuns = (rows, studyNameById = new Map()) =>
  (rows ?? []).map((r) => {
    const s = r.summary || {}
    const running = r.status === 'queued' || r.status === 'running'
    return {
      id: r.id,
      studyId: r.study_id,
      study: studyNameById.get(r.study_id) ?? '—',
      kind: 'Simulation bootstrap',
      estimator: s.recommended_estimator ?? (running ? 'computing…' : '—'),
      mode: r.status === 'succeeded' ? 'VALIDATED' : running ? undefined : 'LIVE',
      power: s.recommended_power != null ? s.recommended_power / 100 : null,
      state: running ? 'running' : 'done',
      when: relTime(r.created_at),
    }
  })

const DOSSIER_LABEL = { protocol: 'Study protocol', report: 'Evidence report' }
const normDossiers = (rows) =>
  (rows ?? []).map((g) => ({
    id: g.id,
    name: DOSSIER_LABEL[g.type] ?? humanize(g.type),
    framework: humanize(g.type),
    state: g.status ?? 'draft',
    pct: g.status === 'ready' ? 100 : 0,
    when: relTime(g.created_at),
  }))

const normSources = (resp) =>
  (resp?.sources ?? []).map((s) => ({
    name: SOURCE_META[s.source_id]?.name ?? humanize(s.source_id),
    count: s.count,
    icon: SOURCE_META[s.source_id]?.icon ?? 'page',
  }))

// Coverage bars "by category": one bar per evidence type, share of the indexed
// corpus, greener as coverage rises. Derived from the backend coverage matrix.
const COVERAGE_PALETTE = ['#047857', '#3172B0', '#7C3AED', '#B45309', '#0E7490']
const normCoverage = (resp) => {
  const cells = resp?.matrix ?? []
  const byType = new Map()
  let total = 0
  for (const c of cells) {
    const n = c.doc_count ?? 0
    total += n
    byType.set(c.evidence_type, (byType.get(c.evidence_type) ?? 0) + n)
  }
  if (!total) return []
  return [...byType.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([type, n], i) => ({
      label: humanize(type),
      pct: Math.round((100 * n) / total),
      color: COVERAGE_PALETTE[i % COVERAGE_PALETTE.length],
    }))
}

// collection → async fetcher returning the normalized array (or [] on empty).
// `variables` has no backend list endpoint yet → [] (EmptyState).
const FETCHERS = {
  studies:         async () => normStudies(await apiJson('/studies')),
  datasets:        async () => {
    const [rows, studies] = await Promise.all([
      apiJson('/datasets'),
      apiJson('/studies').catch(() => []),
    ])
    const nameById = new Map((studies ?? []).map((s) => [s.id, s.name]))
    return normDatasets(rows, nameById)
  },
  dossiers:        async () => normDossiers(await apiJson('/documents')),
  corpus_sources:  async () => normSources(await apiJson('/corpus/sources')),
  corpus_coverage: async () => normCoverage(await apiJson('/corpus/coverage')),
  runs:            async () => {
    const [rows, studies] = await Promise.all([
      apiJson('/simulations/runs'),
      apiJson('/studies').catch(() => []),
    ])
    const nameById = new Map((studies ?? []).map((s) => [s.id, s.name]))
    return normRuns(rows, nameById)
  },
  variables:       async () => [],
}

/**
 * One-shot fetch of a normalized collection (same logic as useCollection, usable
 * outside React — e.g. to refresh a list after a mutation). Yields [] on error.
 */
export async function fetchCollection(name) {
  try {
    const fetcher = FETCHERS[name]
    return fetcher ? await fetcher() : []
  } catch {
    return []
  }
}

/**
 * Returns { data, loading } for a workspace collection. `data` is always an array;
 * the backend (or an empty/unwired collection) yields [] so the UI renders an
 * EmptyState rather than crashing. `reloadToken` forces a re-fetch when it changes.
 */
export function useCollection(name, reloadToken = 0) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoading(true)
      const base = await fetchCollection(name)
      if (alive) { setData(base); setLoading(false) }
    })()
    return () => { alive = false }
  }, [name, reloadToken])

  return { data: data ?? [], loading }
}
