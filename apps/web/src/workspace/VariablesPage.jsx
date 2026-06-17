import { useState } from 'react'
import { CheckCircle2, TriangleAlert, Variable, Network, Boxes } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { SubTabs } from '@/cockpit/SubTabs'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { Loading, EmptyState } from '@/workspace/CollectionStates'

export function VariablesPage() {
  const { data: variables, loading } = useCollection('variables')
  const { openStudy } = useStudyNav()
  const [sub, setSub] = useState('variables')

  return (
    <WorkspacePage
      eyebrow="Modeling"
      title="Variables & models"
      sub="Variable registry, causal models, and reference standards across your studies"
    >
      <SubTabs
        tabs={[
          { id: 'variables', label: 'Variables' },
          { id: 'dags', label: 'DAGs' },
          { id: 'models', label: 'Foundation models' },
        ]}
        active={sub}
        onChange={setSub}
      />

      {sub === 'variables' &&
        (loading ? (
          <Loading />
        ) : variables.length === 0 ? (
          <EmptyState
            icon={Variable}
            title="No variables yet"
            subtitle="Variables appear here once a study's modeling registry is wired to a live data source."
          />
        ) : (
          <Card className="gap-0 px-[18px] py-1">
            <div className="flex gap-3.5 border-b border-border py-[11px] text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/70">
              <span className="flex-1">Variable</span>
              <span className="w-[110px]">Role</span>
              <span className="w-24">Study</span>
              <span className="w-[90px]">Type</span>
              <span className="w-20 text-right">Available</span>
            </div>
            {variables.map((r, i) => (
              <div
                key={r.id}
                onClick={() => openStudy(r.studyId || r.study)}
                className={`flex cursor-pointer items-center gap-3.5 py-3 transition-colors hover:bg-muted/30 ${i === variables.length - 1 ? '' : 'border-b border-border'}`}
                style={{ background: r.ok ? 'transparent' : 'rgba(185,137,0,0.05)' }}
              >
                <span className="flex-1 font-mono text-[13px] text-foreground">{r.v}</span>
                <span className="w-[110px]">
                  <Badge variant="outline" className="text-muted-foreground text-[10.5px]">
                    {r.role}
                  </Badge>
                </span>
                <span className="w-24 text-[13px] text-muted-foreground">{r.study}</span>
                <span className="w-[90px] text-[12.5px] text-muted-foreground">{r.type}</span>
                <span className="flex w-20 justify-end">
                  {r.ok ? (
                    <CheckCircle2 size={16} color="#047857" />
                  ) : (
                    <TriangleAlert size={16} color="#B98900" />
                  )}
                </span>
              </div>
            ))}
          </Card>
        ))}

      {sub === 'dags' && (
        <EmptyState
          icon={Network}
          title="No causal models yet"
          subtitle="Causal-DAG templates and study-specific models will appear here once connected to a live source."
        />
      )}

      {sub === 'models' && (
        <EmptyState
          icon={Boxes}
          title="No foundation models yet"
          subtitle="Reference and foundation models that variables and DAGs are built on will appear here once connected to a live source."
        />
      )}
    </WorkspacePage>
  )
}
