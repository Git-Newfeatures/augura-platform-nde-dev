import { useState } from 'react'
import { Target, Search as SearchIcon } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/workspace/CollectionStates'
import { apiJson } from '@/api'

// ── Semantic search (pgvector) ────────────────────────────────────────────────
// POST /corpus/search: embed-on-server then tenant-scoped vector match.
export function SemanticSearch() {
  const [q, setQ] = useState('')
  const [running, setRunning] = useState(false)
  const [hits, setHits] = useState(null)
  const [error, setError] = useState(null)

  async function run() {
    if (!q.trim() || running) return
    setRunning(true); setError(null); setHits(null)
    try {
      const res = await apiJson('/corpus/search', {
        method: 'POST',
        body: JSON.stringify({ query: q.trim(), match_count: 20 }),
      })
      setHits(Array.isArray(res) ? res : [])
    } catch (e) {
      const m = String(e?.message || '')
      setError(m.includes('503')
        ? 'Semantic search unavailable: the embedding API key isn\'t configured yet.'
        : 'Search failed — check your connection.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
        <strong className="text-foreground">Semantic search across your corpus.</strong>{' '}
        Find the most relevant indexed passages by meaning (pgvector), scoped to your tenant.
      </div>
      <Card className="gap-0 rounded-xl border p-5">
        <textarea
          rows={2}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') run() }}
          placeholder="e.g. effect of engagement on HbA1c reduction"
          className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-[12.5px] outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        />
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" onClick={() => { setQ(''); setHits(null); setError(null) }}>Clear</Button>
          <Button onClick={run} disabled={running || !q.trim()}>
            <SearchIcon className="h-3.5 w-3.5" /> {running ? 'Searching…' : 'Search corpus'}
          </Button>
        </div>
      </Card>
      {error && (
        <Card className="gap-0 rounded-xl border p-4 text-[12.5px] text-[#C0392B]" style={{ borderLeft: '3px solid #C0392B' }}>
          {error}
        </Card>
      )}
      {hits && (hits.length === 0 ? (
        <EmptyState icon={Target} title="No matches" subtitle="No indexed passages matched this query." />
      ) : (
        <Card className="gap-0 rounded-xl border p-5">
          <div className="flex flex-col gap-3">
            {hits.map((h) => (
              <div key={h.id} className="flex items-start gap-2.5 border-b border-border/60 pb-3 last:border-0 last:pb-0">
                <Badge variant="outline" className="mt-px flex-shrink-0 text-[10px] font-normal text-muted-foreground">
                  {h.source_id || 'corpus'}
                </Badge>
                <span className="min-w-0 flex-1 text-[12.5px] leading-snug text-foreground/85">
                  {h.title && <span className="font-medium text-foreground">{h.title} · </span>}
                  {String(h.content || '').slice(0, 240)}
                </span>
                {h.similarity != null && (
                  <span className="flex-shrink-0 font-mono text-[11px] text-muted-foreground/70">
                    {Math.round(h.similarity * 100)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}
