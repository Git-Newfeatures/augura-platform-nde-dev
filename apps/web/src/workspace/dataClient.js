// dataClient.js — the single demo-vs-real data gate for the Evidence Workspace.
//
//   Demo-data toggle ON  → return the fixtures verbatim (fake data everywhere).
//   Demo-data toggle OFF → read the real Supabase table of the same name; a
//                          missing/empty table yields [] so the UI renders an
//                          EmptyState ("blank when not wired"). The real read is
//                          a genuine endpoint call (supabase /rest/v1/<table>).
import { useState, useEffect } from 'react'
import { supabase } from '@/supabase'
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

// PostgREST table per collection (read when demo is OFF).
const TABLES = {
  studies:         'studies',
  runs:            'runs',
  datasets:        'datasets',
  dossiers:        'dossiers',
  variables:       'variables',
  corpus_sources:  'corpus_sources',
  corpus_coverage: 'corpus_coverage',
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
        const table = TABLES[name]
        if (!table) {
          if (alive) setData(withLocal(name, []))
          return
        }
        const { data: rows, error } = await supabase.from(table).select('*')
        const base = error ? [] : (rows ?? [])
        // Real study rows lack the cockpit shape → normalize so the dashboard renders.
        if (alive) setData(withLocal(name, name === 'studies' ? base.map(studyFromRow) : base))
      } catch {
        if (alive) setData(withLocal(name, []))
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [name, demo, version])

  return { data: data ?? [], loading, demo }
}
