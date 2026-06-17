import { useState } from 'react'
import {
  BookOpen, FlaskConical, Shield, FileText, Library, Target, Search as SearchIcon,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SubTabs } from '@/cockpit/SubTabs'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { openSearch } from '@/shell/searchBus'
import { apiJson } from '@/api'

const CORPUS_ICON = {
  book:   BookOpen,
  flask:  FlaskConical,
  shield: Shield,
  page:   FileText,
}

// ── Recherche de littérature PubMed (réelle) ──────────────────────────────────
// Interroge le backend POST /corpus/literature → PubMed (E-utilities NCBI) → ingestion
// dans le corpus du tenant (Document + Chunk). Rafraîchit les compteurs de sources.
function AdHocQuery() {
  const [q, setQ] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function run() {
    if (!q.trim() || running) return
    setRunning(true); setError(null); setResult(null)
    try {
      const res = await apiJson('/corpus/literature', {
        method: 'POST',
        body: JSON.stringify({ query: q.trim(), max_results: 10 }),
      })
      setResult(res)
    } catch (e) {
      setError(e?.message || 'La recherche a échoué.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
        <strong className="text-foreground">Search PubMed and index it.</strong>{' '}
        Describe an indication, intervention, and outcome — the agent queries PubMed (NCBI
        E-utilities) and ingests matching articles into your evidence base.
      </div>

      <Card className="gap-0 rounded-xl border p-5">
        <div className="mb-1 text-[15px] font-semibold text-foreground">Describe what you're looking for</div>
        <p className="mb-3 text-[12px] text-muted-foreground">Free text — indication, intervention, and outcome.</p>
        <textarea
          rows={3}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run() }}
          placeholder="e.g. digital engagement and glycemic control (HbA1c) in type 2 diabetes, randomized trials"
          className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-[12.5px] outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        />
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" onClick={() => { setQ(''); setResult(null); setError(null) }}>Clear</Button>
          <Button onClick={run} disabled={running || !q.trim()}>
            <SearchIcon className="h-3.5 w-3.5" /> {running ? 'Searching PubMed…' : 'Search PubMed'}
          </Button>
        </div>
      </Card>

      {error && (
        <Card className="gap-0 rounded-xl border p-4 text-[12.5px] text-[#C0392B]" style={{ borderLeft: '3px solid #C0392B' }}>
          {error}
        </Card>
      )}

      {result && (
        <Card className="gap-0 rounded-xl border p-5" style={{ borderLeft: '3px solid #047857' }}>
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[13.5px] font-semibold text-foreground">{result.query}</div>
              <div className="mt-0.5 text-[12px] text-muted-foreground">
                {result.ingested} indexed · {result.found} found on PubMed
                {result.embedded ? ' · embedded for semantic search' : ''}
              </div>
            </div>
            <Badge variant="secondary" className="font-mono text-[11px] text-primary">
              {result.ingested} new
            </Badge>
          </div>
          {result.documents.length === 0 ? (
            <div className="border-t border-border pt-3 text-[12px] text-muted-foreground">
              All matching articles were already in your corpus.
            </div>
          ) : (
            <div className="flex flex-col gap-2 border-t border-border pt-3">
              {result.documents.map((d) => (
                <div key={d.id} className="flex items-start gap-2 text-[12px] leading-snug">
                  <Badge variant="outline" className="mt-px flex-shrink-0 text-[10px] font-normal text-muted-foreground">
                    {d.evidence_type || 'study'}
                  </Badge>
                  <span className="min-w-0 text-foreground/85">
                    <a href={d.url} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
                      {d.title}
                    </a>
                    {d.age_label ? <span className="text-muted-foreground"> · {d.age_label}</span> : null}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

export function CorpusPage() {
  const { data: sources, loading } = useCollection('corpus_sources')
  const { data: coverage } = useCollection('corpus_coverage')
  const total = sources.reduce((sum, s) => sum + (s.count || 0), 0)
  const [sub, setSub] = useState('browse')

  return (
    <WorkspacePage
      eyebrow="Evidence base"
      title="Literature"
      sub={
        loading
          ? 'Loading…'
          : total
            ? `${total.toLocaleString()} indexed documents across ${sources.length} sources`
            : 'Tenant-wide evidence knowledge base'
      }
      action={<Button variant="outline" onClick={openSearch}>Search</Button>}
    >
      {loading && sources.length === 0 ? (
        <Loading />
      ) : sources.length === 0 ? (
        <EmptyState
          icon={Library}
          title="No corpus indexed yet"
          subtitle="Use the ad-hoc PubMed query to search and index evidence (PubMed, NCBI E-utilities) into your corpus."
          cta={<Button onClick={() => setSub('query')}><SearchIcon className="h-3.5 w-3.5" /> Search PubMed</Button>}
        />
      ) : (
        <>
          <SubTabs
            tabs={[
              { id: 'browse',  label: 'Browse',        icon: <Library size={14} /> },
              { id: 'matches', label: 'Study matches', icon: <Target size={14} /> },
              { id: 'query',   label: 'Ad-hoc query',  icon: <SearchIcon size={14} /> },
            ]}
            active={sub}
            onChange={setSub}
          />

          {/* ════════════════════════ BROWSE ════════════════════════ */}
          {sub === 'browse' && (
            <>
              {/* source cards */}
              <div className="mb-[22px] grid grid-cols-2 gap-3.5 sm:grid-cols-4">
                {sources.map((s) => {
                  const CorpusIcon = CORPUS_ICON[s.icon] ?? FileText
                  return (
                    <Card key={s.name} className="gap-0 p-[18px]">
                      <span className="mb-3 flex h-9 w-9 items-center justify-center rounded-[9px] bg-secondary text-primary">
                        <CorpusIcon size={18} />
                      </span>
                      <div className="font-mono text-[24px] font-medium leading-none text-foreground">
                        {s.count}
                      </div>
                      <div className="mt-1.5 text-[13px] text-muted-foreground">{s.name}</div>
                    </Card>
                  )
                })}
              </div>

              {/* Coverage by product category */}
              {coverage.length > 0 && (
                <Card className="mb-[22px] gap-0 px-[22px] py-5">
                  <h3 className="m-0 text-[15px] font-semibold text-foreground">
                    Coverage by product category
                  </h3>
                  <p className="mt-1.5 mb-4 text-[13px] text-muted-foreground">
                    Indexed evidence relevant to your active studies.
                  </p>
                  {coverage.map((c) => (
                    <div key={c.label} className="mb-3.5">
                      <div className="mb-1.5 flex justify-between text-[13px] text-foreground/80">
                        <span>{c.label}</span>
                        <span className="font-mono text-foreground">{c.pct}%</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-black/[0.08]">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${c.pct}%`, background: c.color }}
                        />
                      </div>
                    </div>
                  ))}
                </Card>
              )}
            </>
          )}

          {/* ════════════════════════ STUDY MATCHES ════════════════════════ */}
          {sub === 'matches' && (
            <EmptyState
              icon={Target}
              title="No study matches yet"
              subtitle="Documents matched to your studies by the profiling agent will appear here once a study completes a profiling run."
            />
          )}

          {/* ════════════════════════ AD-HOC QUERY ════════════════════════ */}
          {sub === 'query' && <AdHocQuery />}
        </>
      )}
    </WorkspacePage>
  )
}
