import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, ClipboardList } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { slugify } from '@/lib/utils'

const FRAMEWORKS = ['DiGA', 'CONSORT-AI', 'EU MDR', 'NICE DSP', 'EUnetHTA', 'FDA SaMD']

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
  const [name, setName] = useState('')
  const [tagline, setTagline] = useState('')
  const [category, setCategory] = useState('')
  const [framework, setFramework] = useState(FRAMEWORKS[0])

  const canCreate = name.trim().length > 1

  function create() {
    if (!canCreate) return
    const id = slugify(name)
    // No backend /studies POST yet, so creation does not persist; the form
    // still validates input and lands on the new study's first workflow step
    // (cohort upload).
    navigate(`/studies/${id}/workflow/assistant`)
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
            placeholder="e.g. Lucis — preventive biomarkers"
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
          <Button variant="ghost" onClick={() => navigate('/studies')}>
            Cancel
          </Button>
          <Button disabled={!canCreate} onClick={create}>
            Create study <ArrowRight size={15} />
          </Button>
        </div>
      </Card>
    </div>
  )
}
