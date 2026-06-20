import { useReducer, useRef, useEffect, useState, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { AlertTriangle, SearchX, Lock, RefreshCw, Search as SearchIcon } from 'lucide-react'
import { ResultsList } from './ResultsList'
import { RecentQueries } from './RecentQueries'
import { SavedEvidence } from './SavedEvidence'
import { SessionActions } from './SessionActions'
import { StudyPicker } from './StudyPicker'
import {
  streamRetrieve, createSession, listSessions, logEvent,
  saveSnapshot, listSnapshots, getSnapshot, ingestPmids, flattenItem, resultId,
} from './literatureClient'

const DATE_RANGES = [
  { id: 'any', label: 'Any time' },
  { id: '1y', label: 'Last year' },
  { id: '5y', label: 'Last 5 years' },
  { id: '10y', label: 'Last 10 years' },
]
const STUDY_TYPES = [
  { id: 'rct', label: 'RCT' },
  { id: 'observational', label: 'Observational' },
  { id: 'systematic_review', label: 'Systematic review' },
  { id: 'meta_analysis', label: 'Meta-analysis' },
]
const SOURCE_OPTIONS = [
  { id: 'pubmed', label: 'PubMed' },
  { id: 'ctgov', label: 'ClinicalTrials.gov' },
]

// status: idle | querying | complete | error | frozen
const initialState = {
  sessionId: null,
  status: 'idle',
  question: '',
  dateRange: 'any',
  studyTypes: [],
  sources: ['pubmed', 'ctgov'],
  knownItem: false,
  knownItemMiss: false,
  groups: {},      // source -> { results, note, error, loading }
  marks: {},       // resultId -> 'kept' | 'dismissed'
  error: null,
  saved: null,     // { label, href } après sauvegarde
  frozenAt: null,
}

const blankGroups = (sources) => Object.fromEntries(sources.map((s) => [s, { results: [], loading: true }]))

function reducer(state, action) {
  switch (action.type) {
    case 'set_question': return { ...state, question: action.value }
    case 'set_date':     return { ...state, dateRange: action.value }
    case 'set_types':    return { ...state, studyTypes: action.value }
    case 'set_sources':  return { ...state, sources: action.value }
    case 'submit':
      return { ...state, status: 'querying', sessionId: action.sessionId, groups: blankGroups(state.sources), knownItem: false, knownItemMiss: false, marks: {}, error: null, saved: null, frozenAt: null }
    case 'ev_meta':
      return { ...state, sources: action.sources || state.sources, knownItem: !!action.known_item, groups: blankGroups(action.sources || state.sources) }
    case 'ev_group': {
      const items = (action.items || []).map(flattenItem)
      return { ...state, groups: { ...state.groups, [action.source]: { results: items, note: action.note, loading: false } } }
    }
    case 'ev_done': {
      const empty = Object.values(state.groups).every((g) => !(g.results && g.results.length))
      return { ...state, status: 'complete', knownItemMiss: state.knownItem && empty }
    }
    case 'ev_error': return { ...state, status: 'error', error: action.text || 'Query failed' }
    case 'mark':     return { ...state, marks: { ...state.marks, [action.id]: action.value } }
    case 'saved':    return { ...state, saved: action.saved }
    case 'reset':    return { ...initialState, dateRange: state.dateRange, studyTypes: state.studyTypes, sources: state.sources }
    case 'restore_frozen': {
      const snap = action.snapshot
      const sources = snap.sources || ['pubmed', 'ctgov']
      const flat = (snap.results || []).map((r) => flattenItem(r))
      const groups = Object.fromEntries(sources.map((s) => [s, { results: flat.filter((r) => r.source === s), loading: false }]))
      const marks = Object.fromEntries(flat.filter((r) => r.annotation).map((r) => [resultId(r), r.annotation]))
      return { ...initialState, status: 'frozen', question: snap.query ?? '', sources, groups, marks, frozenAt: snap.created_at || null }
    }
    default: return state
  }
}

export function AdHocQuery() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [history, setHistory] = useState([])
  const [saved, setSavedList] = useState([])
  const [picking, setPicking] = useState(false)
  const [ingest, setIngest] = useState({}) // resultId -> 'busy'|'done'|'error'
  const abortRef = useRef(null)

  const refreshHistory = useCallback(async () => {
    try {
      const rows = await listSessions()
      setHistory(rows.map((s) => ({ id: s.id, question: s.query, createdAt: s.created_at })))
    } catch { /* non-bloquant */ }
  }, [])
  const refreshSaved = useCallback(async () => {
    try {
      const rows = await listSnapshots()
      setSavedList(rows.map((s) => ({ snapshotId: s.id, question: s.query, studyId: s.study_id, resultCount: s.result_count })))
    } catch { /* non-bloquant */ }
  }, [])

  // eslint-disable-next-line react-hooks/set-state-in-effect -- appel au mount uniquement (useCallback stable)
  useEffect(() => { refreshHistory(); refreshSaved() }, [refreshHistory, refreshSaved])
  useEffect(() => () => abortRef.current?.abort(), [])

  const busy = state.status === 'querying'
  const frozen = state.status === 'frozen'
  const showResults = state.status === 'complete' || frozen

  const run = async () => {
    if (!state.question.trim() || busy) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    let sessionId = null
    try { const s = await createSession(state.question.trim()); sessionId = s.id } catch { /* session best-effort */ }
    dispatch({ type: 'submit', sessionId })
    refreshHistory()
    await streamRetrieve({
      query: state.question.trim(),
      sources: state.sources,
      dateRange: state.dateRange,
      studyTypes: state.studyTypes,
      signal: ctrl.signal,
      onEvent: (ev) => {
        if (ev.type === 'meta') dispatch({ type: 'ev_meta', sources: ev.sources, known_item: ev.known_item })
        else if (ev.type === 'group') dispatch({ type: 'ev_group', source: ev.source, items: ev.items, note: ev.note })
        else if (ev.type === 'done') dispatch({ type: 'ev_done' })
        else if (ev.type === 'error') dispatch({ type: 'ev_error', text: ev.text })
      },
    })
  }

  const mark = (result, value) => {
    const id = resultId(result)
    const next = state.marks[id] === value ? null : value
    dispatch({ type: 'mark', id, value: next })
    if (next && state.sessionId) {
      logEvent(state.sessionId, value === 'kept' ? 'result_kept' : 'result_dismissed', { id, source: result.source })
    }
  }

  const addToCorpus = async (result) => {
    if (result.source !== 'pubmed' || !result.pmid) return
    const id = resultId(result)
    setIngest((m) => ({ ...m, [id]: 'busy' }))
    try { await ingestPmids([result.pmid]); setIngest((m) => ({ ...m, [id]: 'done' })) }
    catch { setIngest((m) => ({ ...m, [id]: 'error' })) }
  }

  const allItems = () => Object.values(state.groups).flatMap((g) => (g.results || []).map((r) => ({ ...r, annotation: state.marks[resultId(r)] ?? null })))

  const doSave = async (scope, study) => {
    setPicking(false)
    try {
      await saveSnapshot({ query: state.question, sources: state.sources, studyId: scope === 'study' ? study?.id ?? null : null, items: allItems() })
      dispatch({ type: 'saved', saved: scope === 'study' ? { label: `Saved to ${study.name}.`, href: `/studies/${study.id}` } : { label: 'Saved to Literature (standalone).' } })
      refreshSaved()
    } catch (e) {
      dispatch({ type: 'saved', saved: { label: `Could not save (${String(e?.message || 'error').slice(0, 80)}).` } })
    }
  }

  const reopenRecent = (id, question) => { abortRef.current?.abort(); dispatch({ type: 'set_question', value: question || '' }) }
  const reopenSaved = async (id) => {
    abortRef.current?.abort()
    try { const snap = await getSnapshot(id); dispatch({ type: 'restore_frozen', snapshot: snap }) } catch { /* ignore */ }
  }
  const startNew = () => { abortRef.current?.abort(); setIngest({}); dispatch({ type: 'reset' }) }

  const toggleSource = (id) => {
    const set = new Set(state.sources)
    set.has(id) ? set.delete(id) : set.add(id)
    if (set.size) dispatch({ type: 'set_sources', value: [...set] })
  }
  const toggleType = (id) => {
    const set = new Set(state.studyTypes)
    set.has(id) ? set.delete(id) : set.add(id)
    dispatch({ type: 'set_types', value: [...set] })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
        <strong className="text-foreground">Live evidence retrieval.</strong>{' '}
        Ask a clinical question; the agent searches PubMed and ClinicalTrials.gov and returns structured, cited evidence, grouped by source. A live search takes up to ~90 seconds.
      </div>

      <RecentQueries entries={history} activeId={state.sessionId} onOpen={reopenRecent} />
      <SavedEvidence entries={saved} activeId={null} onOpen={reopenSaved} />

      {!frozen && (
        <Card className="gap-0 rounded-xl border p-5">
          <div className="mb-1 text-[15px] font-semibold text-foreground">Ask a research question</div>
          <p className="mb-3 text-[12px] text-muted-foreground">Plain English — the agent searches the selected sources and returns structured, cited results.</p>
          <textarea
            rows={3}
            value={state.question}
            disabled={busy}
            onChange={(e) => dispatch({ type: 'set_question', value: e.target.value })}
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run() }}
            placeholder="e.g. What is the evidence for GLP-1 agonists in heart failure?"
            className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-[12.5px] outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-60"
          />
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2.5">
            <Pills label="Sources" options={SOURCE_OPTIONS} active={state.sources} onToggle={toggleSource} busy={busy} />
            <div className="flex items-center gap-2">
              <span className="text-[11.5px] font-medium text-muted-foreground">Date</span>
              <div className="flex gap-0.5 rounded-lg border border-border p-0.5">
                {DATE_RANGES.map((d) => (
                  <button key={d.id} type="button" disabled={busy} onClick={() => dispatch({ type: 'set_date', value: d.id })}
                    className={cn('rounded-md px-2.5 py-1 text-[11.5px] font-medium transition-colors disabled:opacity-60', state.dateRange === d.id ? 'bg-secondary text-primary' : 'text-muted-foreground hover:text-foreground')}>
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
            <Pills label="Study types" options={STUDY_TYPES} active={state.studyTypes} onToggle={toggleType} busy={busy} />
          </div>
          <div className="mt-4 flex justify-end">
            <Button disabled={busy || !state.question.trim()} onClick={run}>
              <SearchIcon className="h-3.5 w-3.5" /> {busy ? 'Searching…' : 'Search sources'}
            </Button>
          </div>
        </Card>
      )}

      {frozen && (
        <Card className="flex flex-row items-center justify-between gap-3 rounded-xl border border-primary/40 bg-secondary/40 p-4 text-[12.5px]">
          <span className="flex items-center gap-2 text-foreground"><Lock size={15} className="flex-shrink-0 text-primary" /><span><strong>Frozen snapshot{state.frozenAt ? ` from ${new Date(state.frozenAt).toLocaleDateString()}` : ''}.</strong> Saved evidence — reproducible exactly.</span></span>
          <div className="flex flex-shrink-0 gap-2">
            <button type="button" onClick={() => { const q = state.question; dispatch({ type: 'reset' }); dispatch({ type: 'set_question', value: q }) }} className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted/50"><RefreshCw size={13} /> Re-run live</button>
            <button type="button" onClick={startNew} className="rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-foreground hover:bg-muted/50">Close</button>
          </div>
        </Card>
      )}

      {state.status === 'error' && (
        <Card className="flex flex-row items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-[12.5px] text-destructive">
          <AlertTriangle size={15} className="mt-px flex-shrink-0" />
          <span><strong>Search failed.</strong> {state.error} — try again or adjust the question.</span>
        </Card>
      )}

      {showResults && (state.knownItemMiss ? (
        <Card className="flex flex-row items-start gap-2 rounded-xl border border-border bg-muted/30 p-4 text-[12.5px] text-foreground/80">
          <SearchX size={15} className="mt-px flex-shrink-0 text-muted-foreground" />
          <span><strong className="text-foreground">No exact match found.</strong> The record may be too recently indexed, or check the PMID / DOI / NCT id.</span>
        </Card>
      ) : (
        <>
          <ResultsList
            sources={state.sources}
            groups={state.groups}
            statusFor={(id) => state.marks[id]}
            onKeep={(r) => mark(r, 'kept')}
            onDismiss={(r) => mark(r, 'dismissed')}
            onAddToCorpus={addToCorpus}
            ingestStateFor={(id) => ingest[id]}
            readOnly={frozen}
          />
          {!frozen && (
            <SessionActions
              saved={state.saved}
              onSaveToStudy={() => setPicking(true)}
              onSaveStandalone={() => doSave('standalone')}
              onNewQuery={startNew}
              onDiscard={startNew}
            />
          )}
        </>
      ))}

      {picking && <StudyPicker onPick={(s) => doSave('study', s)} onClose={() => setPicking(false)} />}
    </div>
  )
}

function Pills({ label, options, active, onToggle, busy }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11.5px] font-medium text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = active.includes(o.id)
          return (
            <button key={o.id} type="button" disabled={busy} onClick={() => onToggle(o.id)}
              className={cn('rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors disabled:opacity-60', on ? 'border-primary bg-secondary text-primary' : 'border-border text-muted-foreground hover:text-foreground')}>
              {o.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
