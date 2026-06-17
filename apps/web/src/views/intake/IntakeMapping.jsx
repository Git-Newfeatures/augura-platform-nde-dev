import { useEffect, useState } from 'react'
import { mapDataset } from '../../intake/intakeApi'

export default function IntakeMapping({ datasetId, onNext }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    mapDataset(datasetId).then(r => live && setResult(r)).catch(e => live && setError(e.message))
    return () => { live = false }
  }, [datasetId])

  if (error) return <p className="text-sm text-[#C0392B]">{error}</p>
  if (!result) return <p className="text-sm text-muted-foreground">Mapping columns to the taxonomy…</p>

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-1 text-lg font-semibold">2 · Concept mapping</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        {result.mapped_count}/{result.total_count} columns matched
        {result.avg_confidence != null && ` · avg confidence ${(result.avg_confidence * 100).toFixed(0)}%`}
      </p>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-muted-foreground">
          <th className="py-1">Column</th><th>Proposed concept</th><th>Confidence</th></tr></thead>
        <tbody>
          {result.columns.map(c => (
            <tr key={c.column} className="border-t border-border">
              <td className="py-1 font-mono">{c.column}</td>
              <td>{c.proposed_canonical_id ?? '—'}</td>
              <td>{c.confidence_label}{c.confidence != null && ` (${(c.confidence * 100).toFixed(0)}%)`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={onNext}
        className="mt-4 rounded-md bg-[#1A6E7A] px-4 py-2 text-sm font-medium text-white">
        Next: Data quality
      </button>
    </div>
  )
}
