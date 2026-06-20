import { Button } from '@/components/ui/button'
import { Plus, Trash2, Bookmark, BookmarkCheck, Check } from 'lucide-react'

// Actions de session : sauver (étude ou standalone) gèle un snapshot. `saved`
// (quand défini) affiche une confirmation à la place des boutons de sauvegarde.
export function SessionActions({ saved, onSaveToStudy, onSaveStandalone, onNewQuery, onDiscard }) {
  return (
    <div className="flex flex-col gap-3">
      {saved ? (
        <>
          <div className="flex items-center gap-2 rounded-lg border border-primary/40 bg-secondary/50 px-3.5 py-2.5 text-[12.5px] text-foreground">
            <Check size={15} className="flex-shrink-0 text-primary" />
            <span>{saved.label}</span>
            {saved.href && <a href={saved.href} className="ml-auto text-[12px] font-medium text-primary hover:underline">Open →</a>}
          </div>
          <div className="flex justify-end">
            <Button variant="outline" onClick={onNewQuery}><Plus className="h-3.5 w-3.5" /> Start new query</Button>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={onDiscard}><Trash2 className="h-3.5 w-3.5" /> Discard</Button>
          <Button variant="outline" onClick={onNewQuery}><Plus className="h-3.5 w-3.5" /> New query</Button>
          <Button variant="outline" onClick={onSaveStandalone}><Bookmark className="h-3.5 w-3.5" /> Save as standalone</Button>
          <Button onClick={onSaveToStudy}><BookmarkCheck className="h-3.5 w-3.5" /> Save to study</Button>
        </div>
      )}
    </div>
  )
}
