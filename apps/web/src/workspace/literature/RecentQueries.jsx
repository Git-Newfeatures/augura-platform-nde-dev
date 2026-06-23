import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { History, ChevronDown, ChevronRight, X, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'

// Recent search sessions (server). Re-opening = live re-run; not a snapshot/audit.
// Collapsed by default; hidden when there is no history.
// Deduplicated upstream (AdHocQuery); single removal (X) or global (Clear all).
export function RecentQueries({ entries, activeId, onOpen, onDelete, onClear }) {
  const [open, setOpen] = useState(false)
  if (!entries?.length) return null

  return (
    <Card className="gap-0 rounded-xl border p-0">
      <div className="flex w-full items-center gap-1.5 px-5 py-3 text-[13px] font-semibold text-foreground">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex flex-1 items-center gap-1.5 text-left"
        >
          {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
          <History size={14} className="text-primary" /> Recent queries
          <Badge variant="secondary" className="ml-1 font-mono text-[10.5px] text-primary">{entries.length}</Badge>
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            title="Clear all recent queries"
          >
            <Trash2 size={12} /> Clear all
          </button>
        )}
      </div>

      {open && (
        <div className="flex flex-col border-t border-border">
          {entries.map((e) => (
            <div
              key={e.id}
              className={cn(
                'flex items-center justify-between gap-3 border-b border-border px-5 py-2.5 last:border-b-0 hover:bg-muted/40',
                e.id === activeId && 'bg-secondary/40',
              )}
            >
              <button
                type="button"
                onClick={() => onOpen(e.id, e.question)}
                className="flex min-w-0 flex-1 items-center text-left"
              >
                <span className="min-w-0 truncate text-[12.5px] text-foreground">{e.question || '(untitled query)'}</span>
              </button>
              <span className="flex flex-shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
                <span>{relativeTime(e.createdAt)}</span>
                {onDelete && (
                  <button
                    type="button"
                    onClick={() => onDelete(e)}
                    className="rounded p-0.5 text-muted-foreground/70 hover:bg-muted hover:text-foreground"
                    title="Remove from recent queries"
                  >
                    <X size={13} />
                  </button>
                )}
              </span>
            </div>
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
