import { useState } from 'react'
import { uploadDataset } from '../../intake/intakeApi'

export default function IntakeUpload({ onUploaded }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true); setError(null)
    try {
      const result = await uploadDataset(file)
      onUploaded(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-1 text-lg font-semibold">1 · Upload a dataset</h2>
      <p className="mb-4 text-sm text-muted-foreground">CSV or XLSX. Parsed and profiled server-side.</p>
      <input type="file" accept=".csv,.xlsx" disabled={busy} onChange={handleFile}
        className="block text-sm" />
      {busy && <p className="mt-3 text-sm text-muted-foreground">Uploading &amp; profiling…</p>}
      {error && <p className="mt-3 text-sm text-[#C0392B]">{error}</p>}
    </div>
  )
}
