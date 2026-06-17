import { useState } from 'react'
import { Lock, FileText } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { apiJson, apiFetch } from '@/api'

// Download requires the Bearer JWT, so a plain <a href> would 401 — fetch the bytes
// authenticated and open them via a blob URL.
async function openDossier(id) {
  const res = await apiFetch(`/documents/${id}/download`)
  if (!res.ok) return
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

const fieldCls =
  'rounded-lg border border-border bg-white px-2.5 py-1.5 text-[12.5px] text-foreground outline-none focus:border-primary/50'

// Poll a generation job until it settles (or times out) — the worker runs server-side.
async function pollJob(jobId, tries = 8) {
  for (let i = 0; i < tries; i++) {
    await new Promise((r) => setTimeout(r, 1200))
    try {
      const j = await apiJson(`/jobs/${jobId}`)
      if (j.status === 'succeeded' || j.status === 'failed') return j
    } catch {
      /* keep polling */
    }
  }
  return null
}

function GenerateControl({ studies, onGenerated }) {
  const [type, setType] = useState('report')
  const [studyId, setStudyId] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  async function generate() {
    setBusy(true)
    setMsg(null)
    try {
      const res = await apiJson('/documents', {
        method: 'POST',
        body: JSON.stringify({ type, study_id: studyId || null }),
      })
      const j = await pollJob(res.job_id)
      onGenerated()
      setMsg(j?.status === 'failed' ? 'Generation failed.' : 'Dossier generated.')
    } catch (e) {
      setMsg(
        String(e?.message || '').includes('401')
          ? 'Session expired — sign in again.'
          : 'Could not generate the dossier.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      {msg && <span className="text-[12px] text-muted-foreground">{msg}</span>}
      <select className={fieldCls} value={studyId} onChange={(e) => setStudyId(e.target.value)} disabled={busy}>
        <option value="">No study</option>
        {studies.map((s) => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </select>
      <select className={fieldCls} value={type} onChange={(e) => setType(e.target.value)} disabled={busy}>
        <option value="report">Evidence report</option>
        <option value="protocol">Study protocol</option>
      </select>
      <Button onClick={generate} disabled={busy}>
        {busy ? 'Generating…' : 'Generate dossier'}
      </Button>
    </div>
  )
}

export function DossiersPage() {
  const [reloadToken, setReloadToken] = useState(0)
  const { data: dossiers, loading } = useCollection('dossiers', reloadToken)
  const { studies } = useStudyNav()

  return (
    <WorkspacePage
      eyebrow="Output"
      title="Dossiers"
      sub="Submission-ready evidence packages across your studies"
      action={<GenerateControl studies={studies} onGenerated={() => setReloadToken((t) => t + 1)} />}
    >
      {loading ? (
        <Loading />
      ) : dossiers.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No dossiers yet"
          subtitle="Generate a dossier from one of your studies to get started."
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {dossiers.map((d) => (
            <Card
              key={d.id}
              className="gap-0 p-[18px_20px] transition-colors hover:border-primary/40"
            >
              <div className="mb-3.5 flex items-start justify-between">
                <span
                  className={`flex h-[38px] w-[38px] flex-shrink-0 items-center justify-center rounded-[10px] ${
                    d.state === 'locked'
                      ? 'border border-border bg-secondary text-muted-foreground'
                      : 'bg-secondary text-primary'
                  }`}
                >
                  {d.state === 'locked' ? <Lock size={18} /> : <FileText size={18} />}
                </span>
                <Badge
                  variant="outline"
                  className={
                    d.state === 'draft'
                      ? 'text-[#3172B0] border-[#3172B0]/30'
                      : 'text-muted-foreground'
                  }
                >
                  {d.framework}
                </Badge>
              </div>
              <div className="text-[15px] font-semibold leading-snug text-foreground">
                {d.name}
              </div>
              <div className="mt-3.5">
                <div className="mb-1.5 flex justify-between text-[12px] text-muted-foreground">
                  <span>{d.state === 'ready' ? 'Ready' : d.state === 'locked' ? 'Awaiting results' : 'Compiling…'}</span>
                  <span className="font-mono text-foreground">{d.pct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-black/[0.08]">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${d.pct}%`, background: d.pct > 0 ? '#047857' : 'transparent' }}
                  />
                </div>
              </div>
              {d.state === 'ready' && (
                <button
                  onClick={() => openDossier(d.id)}
                  className="mt-3 inline-block cursor-pointer border-none bg-transparent p-0 text-[12.5px] font-medium text-primary hover:underline"
                >
                  Open dossier →
                </button>
              )}
            </Card>
          ))}
        </div>
      )}
    </WorkspacePage>
  )
}
