import { useEffect, useState } from 'react'
import { runDq, getDq } from '../../intake/intakeApi'

export default function IntakeDQ({ datasetId }) {
  const [res, setRes] = useState(null)
  const [bundle, setBundle] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    runDq(datasetId)
      .then(r => {
        if (!live) return
        setRes(r)
        return getDq(datasetId)
          .then(b => { if (live) setBundle(b) })
          .catch(() => { /* score already shown from run result */ })
      })
      .catch(e => { if (live) setError(e.message) })
    return () => { live = false }
  }, [datasetId])

  if (error) return <p className="text-sm text-[#C0392B]">{error}</p>
  if (!res) return <p className="text-sm text-muted-foreground">Running data-quality checks…</p>

  const findings = bundle?.bundle?.provenance ?? []
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-1 text-lg font-semibold">3 · Data quality</h2>
      <p className="mb-4 text-sm">
        Overall score: <span className="font-semibold">{res.overall_score != null ? (res.overall_score * 100).toFixed(0) + '%' : '—'}</span>
        {' · '}status {res.status}
      </p>
      <ul className="space-y-1 text-sm">
        {findings.slice(0, 50).map((f, i) => (
          <li key={i} className="border-t border-border py-1">
            <span className="font-mono text-xs text-muted-foreground">[{f.severity}]</span> {f.message}
          </li>
        ))}
        {findings.length === 0 && <li className="text-muted-foreground">No findings.</li>}
      </ul>
    </div>
  )
}
