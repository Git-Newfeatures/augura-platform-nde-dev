import { useState, useEffect } from 'react'
import { CheckCircle2, TriangleAlert, Variable, Network, Boxes, Library } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { SubTabs } from '@/cockpit/SubTabs'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { apiJson } from '@/api'

// Catalog of taxonomy concepts (semantic subsystem) — GET /semantic/concepts.
function TaxonomyConcepts() {
  const [concepts, setConcepts] = useState(null)
  useEffect(() => {
    let alive = true
    ;(async () => {
      try { const c = await apiJson('/semantic/concepts'); if (alive) setConcepts(Array.isArray(c) ? c : []) }
      catch { if (alive) setConcepts([]) }
    })()
    return () => { alive = false }
  }, [])

  if (concepts == null) return <Loading />
  if (concepts.length === 0) {
    return (
      <EmptyState
        icon={Library}
        title="No taxonomy concepts yet"
        subtitle="The semantic taxonomy (standardised clinical concepts) will appear here once seeded."
      />
    )
  }
  return (
    <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Concept</th>
            <th className="px-4 py-2.5 font-medium">Domain</th>
            <th className="px-4 py-2.5 font-medium text-right">Layer</th>
            <th className="px-4 py-2.5 font-medium">Type</th>
            <th className="px-4 py-2.5 font-medium">Unit</th>
            <th className="px-4 py-2.5 font-medium">Role</th>
          </tr>
        </thead>
        <tbody>
          {concepts.map((c) => (
            <tr key={c.local_concept_id} className="border-b border-border/60 last:border-0">
              <td className="px-4 py-2 text-foreground">{c.concept_name}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.augura_domain}</td>
              <td className="px-4 py-2 text-right font-mono text-muted-foreground">{c.layer}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.value_type ?? '—'}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.canonical_unit ?? '—'}</td>
              <td className="px-4 py-2">
                {c.dq_column_role
                  ? <Badge variant="secondary" className="text-primary">{c.dq_column_role}</Badge>
                  : <span className="text-muted-foreground">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

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
          { id: 'taxonomy', label: 'Taxonomy' },
          { id: 'dags', label: 'DAGs' },
          { id: 'models', label: 'Foundation models' },
        ]}
        active={sub}
        onChange={setSub}
      />

      {sub === 'taxonomy' && <TaxonomyConcepts />}

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
