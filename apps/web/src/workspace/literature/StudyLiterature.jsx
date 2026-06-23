import { useState, useEffect, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Lock, BookText, ArrowLeft, ChevronRight, ShieldCheck } from 'lucide-react'
import { EmptyState } from '@/workspace/CollectionStates'
import { ResultsList } from './ResultsList'
import { listSnapshots, getSnapshot, flattenItem, resultId } from './literatureClient'

// Study-scoped "Saved evidence" view: lists the frozen snapshots linked to the
// study (POST "Save to study" → study_id), and re-opens them read-only
// (identical results, content_hash verified backend-side). No mutation here.
export function StudyLiterature({ studyId }) {
  const [list, setList] = useState(null)        // null = loading
  const [openId, setOpenId] = useState(null)
  const [snap, setSnap] = useState(null)        // detail of the opened snapshot
  const [loadingSnap, setLoadingSnap] = useState(false)

  const refresh = useCallback(async () => {
    try { setList(await listSnapshots(studyId)) } catch { setList([]) }
  }, [studyId])
  // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch on mount/study change (setState post-await, useCallback stable)
  useEffect(() => { refresh() }, [refresh])

  const open = async (id) => {
    setOpenId(id); setLoadingSnap(true); setSnap(null)
    try { setSnap(await getSnapshot(id)) } catch { setSnap(null) } finally { setLoadingSnap(false) }
  }
  const back = () => { setOpenId(null); setSnap(null) }

  const head = (
    <div className="mb-1">
      <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-primary">
        <BookText size={13} /> Study · Evidence
      </div>
      <h1 className="mt-1 text-[22px] font-semibold tracking-[-0.02em] text-foreground">Saved evidence</h1>
      <p className="mt-1 text-[13.5px] text-muted-foreground">
        Frozen literature snapshots linked to this study — reproducible exactly, even if PubMed or ClinicalTrials.gov changes.
      </p>
    </div>
  )

  // ── Detail of a snapshot (read-only) ────────────────────────────────────────
  if (openId) {
    const sources = snap?.sources || ['pubmed', 'ctgov']
    const flat = (snap?.results || []).map(flattenItem)
    const groups = Object.fromEntries(
      sources.map((s) => [s, { results: flat.filter((r) => r.source === s), loading: false }]),
    )
    const marks = Object.fromEntries(flat.filter((r) => r.annotation).map((r) => [resultId(r), r.annotation]))
    const when = snap?.created_at ? new Date(snap.created_at).toLocaleDateString() : null

    return (
      <div className="flex flex-col gap-4">
        <button
          type="button"
          onClick={back}
          className="flex w-fit items-center gap-1.5 text-[12.5px] font-medium text-primary hover:underline"
        >
          <ArrowLeft size={14} /> Saved evidence
        </button>

        {loadingSnap ? (
          <div className="py-10 text-center text-[12px] text-muted-foreground">Loading snapshot…</div>
        ) : !snap ? (
          <Card className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-[12.5px] text-destructive">
            Could not load this snapshot.
          </Card>
        ) : (
          <>
            <Card className="flex flex-row items-center justify-between gap-3 rounded-xl border border-primary/40 bg-secondary/40 p-4 text-[12.5px]">
              <span className="flex min-w-0 items-center gap-2 text-foreground">
                <Lock size={15} className="flex-shrink-0 text-primary" />
                <span className="min-w-0">
                  <strong className="truncate">{snap.query || '(untitled query)'}</strong>
                  {when && <span className="text-muted-foreground"> · frozen {when}</span>}
                </span>
              </span>
              <span className="flex flex-shrink-0 items-center gap-1 text-[11.5px] font-medium text-primary">
                <ShieldCheck size={13} /> verified
              </span>
            </Card>
            <ResultsList
              sources={sources}
              groups={groups}
              statusFor={(id) => marks[id]}
              onKeep={() => {}}
              onDismiss={() => {}}
              readOnly
            />
          </>
        )}
      </div>
    )
  }

  // ── List of the study's snapshots ───────────────────────────────────────────
  return (
    <div className="flex flex-col gap-5">
      {head}
      {list == null ? (
        <div className="py-10 text-center text-[12px] text-muted-foreground">Loading saved evidence…</div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={BookText}
          title="No saved evidence yet"
          subtitle="Run an ad-hoc query in Literature, keep the relevant results, and use “Save to study” to freeze them here."
        />
      ) : (
        <Card className="gap-0 overflow-hidden p-0">
          {list.map((s, i) => (
            <button
              key={s.id}
              type="button"
              onClick={() => open(s.id)}
              className={`flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/40 ${i === list.length - 1 ? '' : 'border-b border-border/60'}`}
            >
              <Lock size={14} className="flex-shrink-0 text-primary" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{s.query || '(untitled query)'}</span>
              {Array.isArray(s.sources) && s.sources.map((src) => (
                <Badge key={src} variant="outline" className="flex-shrink-0 text-[10px] font-normal text-muted-foreground">{src}</Badge>
              ))}
              <span className="flex-shrink-0 font-mono text-[11px] text-muted-foreground/70">{s.result_count} res</span>
              <ChevronRight size={14} className="flex-shrink-0 text-muted-foreground/60" />
            </button>
          ))}
        </Card>
      )}
    </div>
  )
}
