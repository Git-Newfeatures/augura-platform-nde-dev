import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { apiJson } from '@/api'

// Server-side dataset upload: posts the raw file (multipart) to POST /datasets/upload,
// where the backend parses, profiles columns, stores the binary, and persists the dataset.
export function DatasetUpload({ onUploaded }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const fileRef = useRef(null)

  async function onFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setMsg(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiJson('/datasets/upload', { method: 'POST', body: fd })
      const cols = res?.columns?.length ?? 0
      setMsg(`Uploaded "${res?.dataset?.name ?? file.name}" — ${cols} columns profiled.`)
      onUploaded?.(res)
    } catch (err) {
      const m = String(err?.message || '')
      setMsg(
        m.includes('401') ? 'Session expired — sign in again.'
          : m.includes('413') ? 'File too large.'
          : m.includes('415') ? 'Unsupported file type (use CSV or XLSX).'
          : 'Upload failed.',
      )
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="flex items-center gap-2">
      {msg && <span className="max-w-[300px] truncate text-[12px] text-muted-foreground">{msg}</span>}
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.xlsx,.xls,text/csv"
        onChange={onFile}
        disabled={busy}
        className="hidden"
      />
      <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={busy} className="text-xs font-medium">
        <Upload className="h-3.5 w-3.5" /> {busy ? 'Uploading…' : 'Upload dataset'}
      </Button>
    </div>
  )
}
