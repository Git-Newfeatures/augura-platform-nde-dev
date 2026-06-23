// LOCAL mapping suggestions (offline), additive to the server mapping (POST
// /datasets/{id}/map). Wires the client semantic engine (concept-matcher +
// confidence-scorer + lexical-normalizer) onto the governed bundle (/semantic/bundle).
// Strictly isolated: any error (store unavailable, matching) returns `null` — it can't
// break the Mapping tab nor the server mapping, which remains the source of truth.
import { useState, useEffect, useMemo } from 'react'
import { Card } from '@/components/ui/card'
import { initSemanticStore, isSemanticStoreReady } from '@/lib/semantic-store'
import { getConceptById } from '@/semantic/taxonomy-loader'
import { matchColumn } from '@/semantic/concept-matcher'
import { computeConfidence, datasetMappingScore } from '@/semantic/confidence-scorer'

export function LocalMappingSuggestions({ columns }) {
  const [ready, setReady] = useState(() => isSemanticStoreReady())
  const [error, setError] = useState(null)

  useEffect(() => {
    if (ready) return
    let alive = true
    initSemanticStore()
      .then(() => { if (alive) setReady(true) })
      .catch((e) => { if (alive) setError(e?.message || String(e)) })
    return () => { alive = false }
  }, [ready])

  const { rows, score } = useMemo(() => {
    if (!ready || !columns?.length) return { rows: [], score: null }
    const rows = columns.map((c) => {
      const column = c.column || c.name || ''
      let best = null
      let confidence = null
      try {
        const candidates = matchColumn(column)
        best = candidates[0] || null
        if (best) {
          const concept = getConceptById(best.concept_id)
          try {
            confidence = computeConfidence(best, { numSummary: null, missing: 0 }, candidates, concept)
          } catch {
            const label = best.score >= 0.8 ? 'High' : best.score >= 0.5 ? 'Medium' : 'Low'
            confidence = { score: best.score, label }
          }
        }
      } catch {
        // matching unavailable for this column — silently ignored
      }
      return { column, best, confidence }
    })
    let score = null
    try {
      score = datasetMappingScore(rows.filter((r) => r.confidence).map((r) => ({ confidence: r.confidence })))
    } catch {
      score = null
    }
    return { rows, score }
  }, [ready, columns])

  if (error) return null
  if (!ready) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground">Loading local taxonomy…</p>
  }
  if (!rows.length) return null

  return (
    <Card className="mt-4 p-0 overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <h4 className="text-[13px] font-medium text-foreground">Local suggestions (offline)</h4>
        {score && (
          <span className="text-[11px] text-muted-foreground">
            {score.mappedCount}/{score.totalCount} · avg. confidence {Math.round((score.avgConfidence || 0) * 100)}%
          </span>
        )}
      </div>
      <table className="w-full text-left text-[12px]">
        <thead className="text-muted-foreground">
          <tr className="border-b border-border">
            <th className="px-4 py-2 font-medium">Column</th>
            <th className="px-4 py-2 font-medium">Suggested concept</th>
            <th className="px-4 py-2 font-medium">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.column} className="border-b border-border/60 last:border-0">
              <td className="px-4 py-2 font-mono text-foreground">{r.column}</td>
              <td className="px-4 py-2">{r.best ? r.best.concept_label : <span className="text-muted-foreground">—</span>}</td>
              <td className="px-4 py-2 text-muted-foreground">
                {r.confidence ? `${r.confidence.label} · ${Math.round((r.confidence.score || 0) * 100)}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
