import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Lock, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

// Snapshots gelés (Saved evidence) — ré-ouverture en lecture seule. Masqué si vide.
export function SavedEvidence({ entries, activeId, onOpen }) {
  const [open, setOpen] = useState(false)
  if (!entries?.length) return null

  return (
    <Card className="gap-0 rounded-xl border p-0">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-1.5 px-5 py-3 text-left text-[13px] font-semibold text-foreground">
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
        <Lock size={14} className="text-primary" /> Saved evidence
        <Badge variant="secondary" className="ml-1 font-mono text-[10.5px] text-primary">{entries.length}</Badge>
      </button>
      {open && (
        <div className="flex flex-col border-t border-border">
          {entries.map((e) => (
            <button
              key={e.snapshotId}
              type="button"
              onClick={() => onOpen(e.snapshotId)}
              className={cn('flex items-center justify-between gap-3 border-b border-border px-5 py-2.5 text-left last:border-b-0 hover:bg-muted/40', e.snapshotId === activeId && 'bg-secondary/40')}
            >
              <span className="min-w-0 truncate text-[12.5px] text-foreground">{e.question || '(untitled)'}</span>
              <span className="flex flex-shrink-0 items-center gap-2 text-[11px] text-muted-foreground">
                <Badge variant="outline" className="text-[10px] font-normal">{e.studyId ? 'study' : 'standalone'}</Badge>
                <span className="font-mono">{e.resultCount} res</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}
