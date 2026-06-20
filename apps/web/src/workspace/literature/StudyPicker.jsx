import { useCollection } from '@/workspace/dataClient'
import { Button } from '@/components/ui/button'
import { Library, X } from 'lucide-react'

// Sélecteur d'étude pour « Save to study ». Lit la VRAIE liste d'études via le data
// client existant (jamais une liste mockée).
export function StudyPicker({ onPick, onClose }) {
  const { data: studies, loading } = useCollection('studies')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-1 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[15px] font-semibold text-foreground">
            <Library size={15} className="text-primary" /> Save to study
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
        </div>
        <p className="mb-3 text-[12px] text-muted-foreground">Freeze this evidence against a study for audit. It stays reproducible even if PubMed changes.</p>

        {loading ? (
          <div className="py-6 text-center text-[12.5px] text-muted-foreground">Loading studies…</div>
        ) : studies.length === 0 ? (
          <div className="py-6 text-center text-[12.5px] text-muted-foreground">No studies available to link.</div>
        ) : (
          <div className="flex max-h-[320px] flex-col gap-1.5 overflow-y-auto">
            {studies.map((s) => (
              <button
                key={s.id}
                onClick={() => onPick(s)}
                className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5 text-left hover:bg-muted/50"
              >
                <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-primary text-[12px] font-semibold text-white">
                  {(s.name || '?').charAt(0)}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium text-foreground">{s.name}</span>
                  {s.tagline && <span className="block truncate text-[11px] text-muted-foreground">{s.tagline}</span>}
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  )
}
