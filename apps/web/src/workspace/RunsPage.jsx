import { Settings2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { Loading, EmptyState } from '@/workspace/CollectionStates'

export function RunsPage() {
  const { data: runs, loading } = useCollection('runs')
  const { openStudy } = useStudyNav()
  return (
    <WorkspacePage
      eyebrow="Compute"
      title="Audit"
      sub="Simulation & analysis runs across all your studies"
    >
      {loading ? (
        <Loading />
      ) : runs.length === 0 ? (
        <EmptyState
          icon={Settings2}
          title="No runs yet"
          subtitle="Simulation and profiling runs from your studies will appear here."
        />
      ) : (
        <Card className="gap-0 px-[18px] py-1">
          {runs.map((r, i) => (
            <div
              key={r.id}
              onClick={() => openStudy(r.study)}
              className={`flex cursor-pointer items-center gap-3.5 py-3.5 transition-colors hover:bg-muted/30 ${i === runs.length - 1 ? '' : 'border-b border-border'}`}
            >
              <span
                className="h-2 w-2 flex-shrink-0 rounded-full"
                style={{
                  background: r.state === 'running' ? '#3172B0' : 'var(--color-primary)',
                  boxShadow: r.state === 'running' ? '0 0 0 3px rgba(49,114,176,0.18)' : 'none',
                }}
              />
              <div className="w-24 flex-shrink-0 text-[13px] font-medium text-foreground">
                {r.study}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] text-foreground/80">{r.kind}</div>
                <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {r.estimator}
                </div>
              </div>
              {r.mode && (
                <Badge
                  variant={r.mode === 'VALIDATED' ? 'secondary' : 'outline'}
                  className={`font-mono text-[10px] tracking-[0.04em] ${r.mode === 'LIVE' ? 'text-[#3172B0]' : ''}`}
                >
                  {r.mode}
                </Badge>
              )}
              <div className="w-16 flex-shrink-0 text-right">
                {r.power != null ? (
                  <span className="font-mono text-[13px] text-foreground">
                    {(r.power * 100).toFixed(0)}%
                    <span className="text-[10px] text-muted-foreground"> pwr</span>
                  </span>
                ) : (
                  <span className="text-[11.5px] font-medium" style={{ color: '#3172B0' }}>
                    running…
                  </span>
                )}
              </div>
              <div className="w-16 flex-shrink-0 text-right text-[11.5px] text-muted-foreground">
                {r.when}
              </div>
            </div>
          ))}
        </Card>
      )}
    </WorkspacePage>
  )
}
