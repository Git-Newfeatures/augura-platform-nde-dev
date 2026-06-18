import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, ClipboardList } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { slugify } from '@/lib/utils'
import { apiJson } from '@/api'
import { useReference } from '@/workspace/dataClient'

const fieldCls =
  'w-full rounded-lg border border-border bg-white px-3.5 py-2.5 text-sm text-foreground ' +
  'placeholder:text-muted-foreground/60 outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15'

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-[12.5px] font-medium text-foreground">{label}</span>
        {hint && <span className="text-[11px] text-muted-foreground/70">{hint}</span>}
      </div>
      {children}
    </label>
  )
}

export function NewStudyPage() {
  const navigate = useNavigate()
  const { data: frameworkRows } = useReference('frameworks')
  const FRAMEWORKS = (frameworkRows ?? []).map((f) => f.label)
  const [name, setName] = useState('')
  const [tagline, setTagline] = useState('')
  const [category, setCategory] = useState('')
  const [framework, setFramework] = useState(FRAMEWORKS[0])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const canCreate = name.trim().length > 1 && !busy

  async function create() {
    if (!canCreate) return
    setBusy(true)
    setError(null)
    try {
      // Persiste réellement l'étude côté backend ; on navigue vers l'UUID renvoyé
      // (et non un slug local) pour que la page workflow retrouve l'étude.
      const study = await apiJson('/studies', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          slug: slugify(name),
          tagline: tagline.trim() || null,
          category: category.trim() || null,
          framework,
        }),
      })
      navigate(`/studies/${study.id}/workflow/assistant`)
    } catch (e) {
      setBusy(false)
      setError(
        String(e?.message || '').includes('401')
          ? 'Session expired — please sign in again.'
          : 'Could not create the study. Please try again.',
      )
    }
  }

  return (
    <div className="mx-auto max-w-[680px] px-5 py-9 pb-24">
      {/* Breadcrumb */}
      <button
        onClick={() => navigate('/studies')}
        className="mb-5 flex items-center gap-1.5 text-[12.5px] font-medium text-primary"
      >
        <ArrowLeft size={14} /> Studies
      </button>

      {/* Header */}
      <div className="mb-6 flex items-start gap-3.5">
        <span className="flex h-[42px] w-[42px] flex-shrink-0 items-center justify-center rounded-[11px] bg-secondary text-primary">
          <ClipboardList size={20} />
        </span>
        <div>
          <h1 className="text-[24px] font-semibold tracking-[-0.02em] text-foreground">New study</h1>
          <p className="mt-1 text-[14px] text-muted-foreground">
            Name your study and pick a target framework. You'll upload the cohort and define the
            causal question in the next steps.
          </p>
        </div>
      </div>

      {/* Form */}
      <Card className="gap-0 flex flex-col gap-5 p-[22px_24px]">
        <Field label="Study name" hint="required">
          <input
            className={fieldCls}
            placeholder="e.g. preventive cardiometabolic biomarkers"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') create() }}
            autoFocus
          />
        </Field>

        <Field label="Tagline">
          <input
            className={fieldCls}
            placeholder="One line describing the product or programme"
            value={tagline}
            onChange={(e) => setTagline(e.target.value)}
          />
        </Field>

        <Field label="Category">
          <input
            className={fieldCls}
            placeholder="e.g. Consumer wellness · Maternal-fetal RPM"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </Field>

        <Field label="Target framework">
          <div className="flex flex-wrap gap-2">
            {FRAMEWORKS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFramework(f)}
                className={`rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  framework === f
                    ? 'border-primary bg-secondary text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </Field>

        <div className="mt-1 flex items-center justify-end gap-2 border-t border-border pt-4">
          {error && <span className="mr-auto text-[12.5px] text-red-600">{error}</span>}
          <Button variant="ghost" onClick={() => navigate('/studies')} disabled={busy}>
            Cancel
          </Button>
          <Button disabled={!canCreate} onClick={create}>
            {busy ? 'Creating…' : 'Create study'} <ArrowRight size={15} />
          </Button>
        </div>
      </Card>
    </div>
  )
}
