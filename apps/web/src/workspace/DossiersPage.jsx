import { Lock, FileText } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { Loading, EmptyState } from '@/workspace/CollectionStates'

export function DossiersPage() {
  const { data: dossiers, loading } = useCollection('dossiers')
  const { openStudy } = useStudyNav()
  return (
    <WorkspacePage
      eyebrow="Output"
      title="Dossiers"
      sub="Submission-ready evidence packages across your studies"
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
              onClick={() => openStudy(String(d.name).split('—')[0].trim())}
              className="gap-0 cursor-pointer p-[18px_20px] transition-colors hover:border-primary/40"
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
                  <span>{d.state === 'locked' ? 'Awaiting results' : 'Compiled'}</span>
                  <span className="font-mono text-foreground">{d.pct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-black/[0.08]">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${d.pct}%`, background: d.pct > 0 ? '#047857' : 'transparent' }}
                  />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </WorkspacePage>
  )
}
