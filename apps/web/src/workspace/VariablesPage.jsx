import { useState } from 'react'
import { CheckCircle2, TriangleAlert, Variable, Network, Boxes, Plus, GitFork, ShieldCheck } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { SubTabs } from '@/cockpit/SubTabs'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { AddItemModal } from '@/workspace/AddItemModal'
import { addLocalItem } from '@/workspace/localData'
import { Loading, EmptyState } from '@/workspace/CollectionStates'

// ── Demo data ──────────────────────────────────────────────────────────────
// Causal-DAG templates / models reused across studies. Node tuple is
// (exposure · outcome · confounders · mediators · instruments).
const DAGS = [
  {
    id: 'dag:lucis-hba1c-v1.0',
    name: 'Engagement → ΔHbA1c',
    study: 'Lucis',
    domain: 'Cardiometabolic · prevention',
    exposure: 'Monitoring tier',
    outcome: 'HbA1c 6m',
    nodes: 8,
    edges: 12,
    status: 'Draft',
    roles: ['Exposure', 'Outcome', 'Confounder', 'Mediator'],
  },
  {
    id: 'dag:bloom-ptl-v0.7',
    name: 'RPM adherence → preterm birth',
    study: 'Bloomlife',
    domain: 'Maternal-fetal · preterm labor',
    exposure: 'UAI monitoring',
    outcome: 'PTL admission',
    nodes: 12,
    edges: 18,
    status: 'Draft',
    roles: ['Exposure', 'Outcome', 'Confounder', 'Mediator', 'Instrument'],
  },
  {
    id: 'dag:cm-hba1c-v2.3',
    name: 'HbA1c control · standard adjustment',
    study: 'Template',
    domain: 'Cardiometabolic · T2DM',
    exposure: 'Monitoring intensity',
    outcome: 'HbA1c 6m',
    nodes: 14,
    edges: 21,
    status: 'Peer-reviewed',
    roles: ['Exposure', 'Outcome', 'Confounder', 'Mediator'],
  },
  {
    id: 'dag:mf-ptl-v1.2',
    name: 'Maternal-fetal · preterm labor',
    study: 'Template',
    domain: 'Maternal-fetal · obstetrics',
    exposure: '[any monitoring]',
    outcome: 'PTL admission',
    nodes: 10,
    edges: 15,
    status: 'Peer-reviewed',
    roles: ['Exposure', 'Outcome', 'Confounder', 'Instrument'],
  },
]

// Reference / foundation models that variables and DAGs are built on top of.
const MODELS = [
  {
    id: 'fm:cardiometabolic-outcome-v3',
    name: 'Cardiometabolic outcome prediction',
    type: 'Outcome-prediction reference',
    version: 'v3.1',
    validated: true,
    note: 'HbA1c / LDL / CRP trajectory priors used to calibrate effect estimates.',
  },
  {
    id: 'fm:engagement-propensity-v2',
    name: 'Engagement propensity',
    type: 'Propensity model',
    version: 'v2.4',
    validated: true,
    note: 'Estimates likelihood of sustained monitoring; powers confounding adjustment.',
  },
  {
    id: 'fm:missing-imputation-v1',
    name: 'Longitudinal imputation',
    type: 'Imputation model',
    version: 'v1.2',
    validated: false,
    note: 'Multiple imputation for intermittent sensor wear and missed visits.',
  },
]

const ROLE_TONE = {
  Exposure: 'text-[#0F6E56]',
  Outcome: 'text-[#B45309]',
  Confounder: 'text-[#3172B0]',
  Mediator: 'text-[#7C3AED]',
  Instrument: 'text-muted-foreground',
}

function RoleLegend({ roles }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {roles.map((role) => (
        <span
          key={role}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10.5px] font-medium"
        >
          <span className={`h-1.5 w-1.5 rounded-full bg-current ${ROLE_TONE[role] || 'text-muted-foreground'}`} />
          <span className="text-muted-foreground">{role}</span>
        </span>
      ))}
    </div>
  )
}

function DagsTab() {
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-4">
        <p className="text-[12.5px] text-muted-foreground">
          Causal-DAG templates and study-specific models. Fork a vetted template instead of starting from a blank canvas.
        </p>
        <Button variant="outline" size="sm" className="flex-shrink-0">
          <Plus className="h-3.5 w-3.5" /> New DAG template
        </Button>
      </div>
      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
        {DAGS.map((d) => (
          <Card key={d.id} className="gap-3 rounded-xl border p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Network size={15} className="flex-shrink-0 text-primary" />
                  <h3 className="truncate text-[15px] font-semibold leading-tight text-foreground">{d.name}</h3>
                </div>
                <div className="mt-1 font-mono text-[11px] text-muted-foreground">{d.id}</div>
              </div>
              <Badge
                variant={d.status === 'Peer-reviewed' ? 'secondary' : 'outline'}
                className="flex-shrink-0 text-[10.5px]"
              >
                {d.status}
              </Badge>
            </div>

            <div className="text-[12.5px] text-muted-foreground">{d.domain}</div>

            <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-2.5 py-1.5 text-[12px]">
              <span className="font-medium text-[#0F6E56]">{d.exposure}</span>
              <span className="text-muted-foreground">→</span>
              <span className="font-medium text-[#B45309]">{d.outcome}</span>
            </div>

            <RoleLegend roles={d.roles} />

            <div className="flex items-center justify-between border-t border-border pt-2.5 text-[12px] text-muted-foreground">
              <span>
                <span className="font-mono font-semibold text-foreground">{d.nodes}</span> nodes ·{' '}
                <span className="font-mono font-semibold text-foreground">{d.edges}</span> edges
              </span>
              <span className="inline-flex items-center gap-1">
                {d.study === 'Template' ? (
                  <Boxes size={13} className="text-muted-foreground" />
                ) : (
                  <GitFork size={13} className="text-muted-foreground" />
                )}
                {d.study}
              </span>
            </div>
          </Card>
        ))}
      </div>
    </>
  )
}

function ModelsTab() {
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-4">
        <p className="text-[12.5px] text-muted-foreground">
          Reference and foundation models that variables and DAGs are built on top of. Edits go through review.
        </p>
        <Button variant="outline" size="sm" className="flex-shrink-0">
          <Plus className="h-3.5 w-3.5" /> Propose reference change
        </Button>
      </div>
      <div className="grid grid-cols-1 gap-3.5 md:grid-cols-3">
        {MODELS.map((m) => (
          <Card key={m.id} className="gap-2.5 rounded-xl border p-5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <Boxes size={15} className="flex-shrink-0 text-primary" />
                <h3 className="text-[15px] font-semibold leading-tight text-foreground">{m.name}</h3>
              </div>
              {m.validated ? (
                <Badge variant="secondary" className="flex-shrink-0 gap-1 text-[10.5px]">
                  <ShieldCheck size={11} /> Validated
                </Badge>
              ) : (
                <Badge variant="outline" className="flex-shrink-0 text-[10.5px] text-[#B45309]">
                  In review
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
              <span>{m.type}</span>
              <span className="text-border">·</span>
              <span className="font-mono">{m.version}</span>
            </div>
            <p className="text-[12px] leading-relaxed text-muted-foreground">{m.note}</p>
            <div className="border-t border-border pt-2 font-mono text-[11px] text-muted-foreground">{m.id}</div>
          </Card>
        ))}
      </div>
    </>
  )
}

export function VariablesPage() {
  const { data: variables, loading } = useCollection('variables')
  const { data: studies } = useCollection('studies')
  const { openStudy } = useStudyNav()
  const [adding, setAdding] = useState(false)
  const [sub, setSub] = useState('variables')
  const studyOptions = studies.map((s) => s.name)

  // Context-dependent "+" action — mirrors the sketch's vmAction label switch.
  const action =
    sub === 'variables' ? (
      <Button onClick={() => setAdding(true)}>
        <Plus className="h-3.5 w-3.5" /> Add variable
      </Button>
    ) : null

  return (
    <WorkspacePage
      eyebrow="Modeling"
      title="Variables & models"
      sub="Variable registry, causal models, and reference standards across your studies"
      action={action}
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
            subtitle="Add a variable, or switch on Demo data to explore a sample registry."
            cta={
              <Button onClick={() => setAdding(true)}>
                <Plus className="h-3.5 w-3.5" /> Add variable
              </Button>
            }
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
                key={r.v}
                onClick={() => openStudy(r.study)}
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

      {sub === 'dags' && <DagsTab />}
      {sub === 'models' && <ModelsTab />}

      {adding && (
        <AddItemModal
          title="Add variable"
          submitLabel="Add variable"
          subtitle="Register a variable in the modeling registry."
          fields={[
            { key: 'v', label: 'Variable name', placeholder: 'e.g. ldl_12m', required: true },
            { key: 'role', label: 'Role', type: 'select', options: ['Exposure', 'Outcome', 'Confounder', 'Mediator', 'Effect modifier'] },
            { key: 'study', label: 'Study', type: 'select', options: studyOptions },
            { key: 'type', label: 'Type', type: 'select', options: ['continuous', 'binary', 'count', 'categorical'] },
          ]}
          onClose={() => setAdding(false)}
          onSave={(f) => {
            addLocalItem('variables', {
              v: f.v,
              role: f.role,
              study: f.study || '—',
              type: f.type,
              ok: true,
            })
            setAdding(false)
          }}
        />
      )}
    </WorkspacePage>
  )
}
