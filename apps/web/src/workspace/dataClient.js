// dataClient.js — the single demo-vs-real data gate for the Evidence Workspace.
//
//   Demo-data toggle ON  → return the fixtures verbatim (fake data everywhere).
//   Demo-data toggle OFF → fetch the real collection through the FastAPI backend
//                          (apiJson → Authorization: Bearer <supabase jwt> →
//                          tenant-scoped RLS → Postgres). An empty/missing
//                          collection yields [] so the UI renders an EmptyState
//                          ("blank when not wired"). The front no longer talks to
//                          PostgREST directly — every read crosses the backend.
import { useState, useEffect } from 'react'
import { apiJson } from '@/api'
import { isMockEnabled } from '@/mocks/mockMode'
import { RUNS, DATASETS, CORPUS, DOSSIERS, VARIABLES, CORPUS_COVERAGE } from './workspaceData'
import { getAllStudies, studyFromRow } from '@/cockpit/cockpitData'
import { getLocalItems, DATA_CHANGED_EVENT } from './localData'

const FIXTURES = {
  studies:         () => getAllStudies(),
  runs:            () => RUNS,
  datasets:        () => DATASETS,
  dossiers:        () => DOSSIERS,
  variables:       () => VARIABLES,
  corpus_sources:  () => CORPUS.sources,
  corpus_coverage: () => CORPUS_COVERAGE,
}

// ── Normalizers : backend response → the exact shape each workspace view renders.
// The fixtures in workspaceData.js are the contract; these map live data onto it.

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

const normDatasets = (rows) =>
  (rows ?? []).map((d) => ({
    id: d.id,
    name: d.name,
    rows: d.row_count != null ? d.row_count.toLocaleString() : '—',
    cols: d.column_count ?? '—',
    study: d.study_name ?? '',
    state: d.status ?? 'pending',
    when: relTime(d.created_at),
  }))

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
// `runs` and `variables` have no backend list endpoint yet → [] (EmptyState).
const FETCHERS = {
  studies:         async () => normStudies(await apiJson('/studies')),
  datasets:        async () => normDatasets(await apiJson('/datasets')),
  dossiers:        async () => normDossiers(await apiJson('/documents')),
  corpus_sources:  async () => normSources(await apiJson('/corpus/sources')),
  corpus_coverage: async () => normCoverage(await apiJson('/corpus/coverage')),
  runs:            async () => [],
  variables:       async () => [],
}

const fixtureFor = (name) => (FIXTURES[name] ? FIXTURES[name]() : [])

// Prepend user-added local items (from the "Add …" buttons) to whatever the base
// source returned. Studies are skipped — getAllStudies() already merges created ones.
const withLocal = (name, base) =>
  name === 'studies' ? base : [...getLocalItems(name), ...base]

/**
 * Returns { data, loading, demo } for a workspace collection.
 * `data` is always an array. In demo mode it resolves synchronously. Re-reads when
 * a local item is added anywhere in the app (DATA_CHANGED_EVENT).
 */
export function useCollection(name) {
  const demo = isMockEnabled()
  const [version, setVersion] = useState(0)
  const [data, setData] = useState(() => (demo ? withLocal(name, fixtureFor(name)) : null))
  const [loading, setLoading] = useState(!demo)

  useEffect(() => {
    const bump = () => setVersion((v) => v + 1)
    window.addEventListener(DATA_CHANGED_EVENT, bump)
    return () => window.removeEventListener(DATA_CHANGED_EVENT, bump)
  }, [])

  useEffect(() => {
    if (demo) {
      setData(withLocal(name, fixtureFor(name)))
      setLoading(false)
      return
    }
    let alive = true
    setLoading(true)
    ;(async () => {
      try {
        const fetcher = FETCHERS[name]
        const base = fetcher ? await fetcher() : []
        if (alive) setData(withLocal(name, base))
      } catch {
        // Backend unreachable or non-2xx → blank (EmptyState), never crash the view.
        if (alive) setData(withLocal(name, []))
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [name, demo, version])

  return { data: data ?? [], loading, demo }
}
