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

// Variables registry → flattens profiled dataset columns into the shape VariablesPage
// renders. A column is "ok" when it has a role and low missingness.
const normVariables = (datasetsWithCols, studyNameById = new Map()) => {
  const out = []
  for (const { dataset, columns } of datasetsWithCols) {
    for (const c of columns) {
      const role = c.final_role || c.proposed_role || '—'
      out.push({
        id: `${dataset.id}:${c.sheet}:${c.name}`,
        v: c.name,
        role,
        study: studyNameById.get(dataset.study_id) ?? dataset.name,
        studyId: dataset.study_id,
        type: c.value_kind || '—',
        ok: role !== '—' && (c.null_pct == null || c.null_pct <= 0.2),
      })
    }
  }
  return out
}

// collection → async fetcher returning the normalized array (or [] on empty).
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
  runs:            async () => {
    const [rows, studies] = await Promise.all([
      apiJson('/simulations/runs'),
      apiJson('/studies').catch(() => []),
    ])
    const nameById = new Map((studies ?? []).map((s) => [s.id, s.name]))
    return normRuns(rows, nameById)
  },
  variables:       async () => {
    const [datasets, studies] = await Promise.all([
      apiJson('/datasets'),
      apiJson('/studies').catch(() => []),
    ])
    const nameById = new Map((studies ?? []).map((s) => [s.id, s.name]))
    const withCols = await Promise.all(
      (datasets ?? []).map(async (d) => ({
        dataset: d,
        columns: await apiJson(`/datasets/${d.id}/columns`).catch(() => []),
      })),
    )
    return normVariables(withCols, nameById)
  },
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

// ── Reference catalogs ──────────────────────────────────────────────────────
//   Static config served by the backend /reference/* endpoints. Cached for the
//   session (these don't change between fetches). Raw payloads are cached; views
//   apply the exported normalizers (some need per-study context, e.g. {partner}).
const REFERENCE_ENDPOINTS = {
  outcomes:           '/reference/outcomes',
  study_designs:      '/reference/study-designs',
  estimands:          '/reference/estimands',
  estimators:         '/reference/estimators',
  frameworks:         '/reference/frameworks',
  evidence_types:     '/reference/evidence-types',
  domains:            '/reference/domains',
  jurisdictions:      '/reference/jurisdictions',
  literature_designs: '/reference/literature-study-designs',
  dq_rules:           '/reference/dq-rules',
  variable_roles:     '/reference/variable-roles',
  cesl_sources:       '/reference/cesl-sources',
}

const _refCache = new Map()

/** One-shot, session-cached fetch of a raw reference payload. Yields null on error. */
export async function fetchReference(name) {
  if (_refCache.has(name)) return _refCache.get(name)
  const path = REFERENCE_ENDPOINTS[name]
  const promise = (path ? apiJson(path) : Promise.resolve(null)).catch(() => null)
  _refCache.set(name, promise)
  return promise
}

/** Returns { data, loading } for a reference catalog. `data` is the raw payload (array or object) or null. */
export function useReference(name) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    ;(async () => {
      setLoading(true)
      const d = await fetchReference(name)
      if (alive) { setData(d); setLoading(false) }
    })()
    return () => { alive = false }
  }, [name])
  return { data, loading }
}

// snake_case API → the exact shapes each view renders. Pure functions, no fetch.

/** /reference/outcomes → { [columnCode]: { key, label, unit, primary, desc, tags, verdict, verdictLabel } }.
 *  The "In dataset ✓" availability tag is added by the view from the live cohort, not here. */
export const normOutcomeCatalog = (rows) =>
  Object.fromEntries((rows ?? []).map((o) => [o.code, {
    key: o.short_key, label: o.label, unit: o.unit, primary: o.is_primary,
    desc: o.description, tags: o.regulatory_tags ?? [],
    verdict: o.verdict, verdictLabel: o.verdict_label,
  }]))

/** /reference/estimators → array with camelCase fields matching the old ESTIMATORS const. */
export const normEstimators = (rows) =>
  (rows ?? []).map((e) => ({
    key: e.key, label: e.label, short: e.short, recommended: e.recommended,
    bootstrapPending: e.bootstrap_pending, interpretability: e.interpretability,
    stability: e.stability, tooltip: e.tooltip,
    eligibleStudyTypes: e.eligible_study_types ?? [],
  }))

/** Build the old ESTIMATOR_FILTER shape ({ retro:[keys], prosp:[keys] }) from normalized estimators. */
export const estimatorFilter = (estimators) => ({
  retro: (estimators ?? []).filter((e) => e.eligibleStudyTypes.includes('retro')).map((e) => e.key),
  prosp: (estimators ?? []).filter((e) => e.eligibleStudyTypes.includes('prosp')).map((e) => e.key),
})

/** /reference/study-designs → the StudyType selector shape. Only enriched designs
 *  (those with a description) are selector options. {partner} is interpolated here. */
export const normStudyDesigns = (rows, partner = 'Partner') =>
  (rows ?? [])
    .filter((d) => d.description != null && d.description !== '')
    .map((d) => ({
      id: d.code,
      name: d.label,
      desc: String(d.description ?? '').replaceAll('{partner}', partner),
      tags: (d.tags ?? []).map(([c, t]) => [c, String(t).replaceAll('{partner}', partner)]),
      estimands: d.estimands ?? [],
    }))

/** /reference/estimands → the old ESTIMAND_OPTS shape (desc ← description). */
export const normEstimands = (rows) =>
  (rows ?? []).map((e) => ({
    key: e.key, name: e.name, desc: e.description,
    regulatory: e.regulatory, recommended: e.recommended, tag: e.tag,
  }))

/** Array of { code, label } → { [code]: label } map (evidence-types/domains/jurisdictions/literature designs/sources). */
export const codeLabelMap = (rows) =>
  Object.fromEntries((rows ?? []).map((r) => [r.code, r.label]))
