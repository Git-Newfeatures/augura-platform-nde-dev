import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { History, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

// Sessions de recherche récentes (serveur). Ré-ouverture = relance live ; pas un
// snapshot/audit. Replié par défaut ; masqué s'il n'y a pas d'historique.
export function RecentQueries({ entries, activeId, onOpen }) {
  const [open, setOpen] = useState(false)
  if (!entries?.length) return null

  return (
    <Card className="gap-0 rounded-xl border p-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-5 py-3 text-left text-[13px] font-semibold text-foreground"
      >
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
        <History size={14} className="text-primary" /> Recent queries
        <Badge variant="secondary" className="ml-1 font-mono text-[10.5px] text-primary">{entries.length}</Badge>
      </button>

      {open && (
        <div className="flex flex-col border-t border-border">
          {entries.map((e) => (
            <button
              key={e.id}
              type="button"
              onClick={() => onOpen(e.id, e.question)}
              className={cn(
                'flex items-center justify-between gap-3 border-b border-border px-5 py-2.5 text-left last:border-b-0 hover:bg-muted/40',
                e.id === activeId && 'bg-secondary/40',
              )}
            >
              <span className="min-w-0 truncate text-[12.5px] text-foreground">{e.question || '(untitled query)'}</span>
              <span className="flex flex-shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
                <span>{relativeTime(e.createdAt)}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}

function relativeTime(iso) {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const m = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}
