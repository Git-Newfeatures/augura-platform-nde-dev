import { useState } from 'react'
import {
  Database,
  ArrowRight,
  ArrowLeft,
  Plus,
  Shield,
  Workflow,
  CheckCircle2,
  GitBranch,
  Check,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { AddItemModal } from '@/workspace/AddItemModal'
import { addLocalItem, localId } from '@/workspace/localData'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { SubTabs } from '@/cockpit/SubTabs'
import { Tag } from '@/ui/components'

// status → Badge props
function StatusBadge({ d }) {
  if (d.state === 'verified') {
    return (
      <Badge variant="secondary" className="text-primary">
        Verified
      </Badge>
    )
  }
  if (d.state === 'flag') {
    return (
      <Badge
        variant="outline"
        className="text-[#B98900] border-[#B98900]/30"
      >
        {d.flags ?? 2} flags
      </Badge>
    )
  }
  if (d.state === 'draft') {
    return (
      <Badge
        variant="outline"
        className="text-[#3172B0] border-[#3172B0]/30"
      >
        Draft
      </Badge>
    )
  }
  // locked
  return (
    <Badge variant="outline" className="text-muted-foreground">
      Locked
    </Badge>
  )
}

// ── Detail demo content ───────────────────────────────────────────────────────
// Tone → row chrome + Tag color, reused across the four detail tabs.
const TONE = {
  ok:   { wrap: 'border-[#97C459] bg-secondary', text: 'text-[#27500A]', tag: 'g', Icon: Check },
  warn: { wrap: 'border-[#EF9F27] bg-[#FAEEDA]', text: 'text-[#854F0B]', tag: 'a', Icon: AlertTriangle },
  none: { wrap: 'border-border bg-card',         text: 'text-muted-foreground', tag: 'b', Icon: Check },
}

// Privacy — PII / PHI scan, one row per column.
const PRIVACY_ROWS = [
  { col: 'member_id',      kind: 'Direct (record number)', action: 'Pseudonymised → member_id', tone: 'ok' },
  { col: 'age',            kind: 'Quasi (age)',            action: 'Retained · low re-id risk',  tone: 'ok' },
  { col: 'sex',            kind: 'Quasi (demographic)',    action: 'Retained · low re-id risk',  tone: 'ok' },
  { col: 'visit_date_*',   kind: 'Quasi (dates)',          action: 'Shifted · intervals kept',   tone: 'ok' },
  { col: 'region',         kind: 'Quasi (geo)',            action: 'Generalised to region',      tone: 'warn' },
  { col: 'hba1c_*',        kind: 'Clinical measure',       action: 'No identifier · retained',   tone: 'none' },
]

// Mapping — column → proposed taxonomy role.
const MAPPING_ROWS = [
  { col: 'engagement_score',    role: 'Exposure',    roleTone: 'g', conf: '0.98', tone: 'ok' },
  { col: 'hba1c_12m',           role: 'Outcome',     roleTone: 'r', conf: '0.97', tone: 'ok' },
  { col: 'rec_adherence_pct',   role: 'Mediator',    roleTone: 'p', conf: '0.94', tone: 'ok' },
  { col: 'age',                 role: 'Confounder',  roleTone: 'b', conf: '1.00', tone: 'ok' },
  { col: 'sex',                 role: 'Confounder',  roleTone: 'b', conf: '1.00', tone: 'ok' },
  { col: 'bmi',                 role: 'Confounder',  roleTone: 'b', conf: '0.99', tone: 'ok' },
]

// Validation — data-quality checks.
const VALIDATION_ROWS = [
  { check: 'Row count',         detail: 'Matches manifest · within expected range',        tone: 'ok' },
  { check: 'Missingness',       detail: 'Max 6.1% on hba1c_12m · all under 10% threshold',  tone: 'ok' },
  { check: 'Type checks',       detail: 'Every column matches its declared type',           tone: 'ok' },
  { check: 'Constant columns',  detail: 'No zero-variance columns detected',                tone: 'ok' },
  { check: 'Duplicate rows',    detail: '2 near-duplicate member_id × visit pairs',         tone: 'warn' },
  { check: 'Primary key',       detail: 'member_id × visit unique across all rows',         tone: 'ok' },
]

// Lineage — source → transforms → uses.
const LINEAGE_STEPS = [
  { kind: 'source',    label: 'Uploaded xlsx',         detail: 'Original wide-format spreadsheet · sha256:a7f2…' },
  { kind: 'transform', label: 'Wide-format reshape',   detail: 'Pivoted to one row per member × visit' },
  { kind: 'transform', label: 'Taxonomy mapping',      detail: 'Columns bound to Augura variables · 22 of 24 mapped' },
  { kind: 'transform', label: 'Validation pass',       detail: '14 checks · 1 soft flag accepted as known' },
]
const LINEAGE_USES = ['Lucis causal model', 'Power simulation']

// ── Detail row primitives ─────────────────────────────────────────────────────
function ScanRow({ left, kind, right, rightTone, badge }) {
  const t = TONE[badge] ?? TONE.none
  return (
    <div className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 ${t.wrap}`}>
      <span className={`flex w-4 flex-shrink-0 items-center justify-center ${t.text}`}>
        <t.Icon size={14} strokeWidth={2.5} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="font-mono text-[12px] text-foreground">{left}</div>
        {kind && <div className="text-[11.5px] text-muted-foreground">{kind}</div>}
      </div>
      {right && (
        <span className={`flex-shrink-0 text-[12px] ${rightTone ?? 'text-muted-foreground'}`}>{right}</span>
      )}
    </div>
  )
}

function SectionTitle({ icon, children, sub }) {
  return (
    <div className="mb-3">
      <div className="flex items-center gap-1.5 text-[15px] font-semibold text-foreground">
        {icon}
        {children}
      </div>
      {sub && <div className="mt-0.5 text-[12px] text-muted-foreground">{sub}</div>}
    </div>
  )
}

// ── Dataset detail (inline view that replaces the list) ───────────────────────
function DatasetDetail({ d, onBack, onOpenStudy }) {
  const [sub, setSub] = useState('privacy')
  const warnCount = VALIDATION_ROWS.filter((r) => r.tone === 'warn').length

  return (
    <div className="flex flex-col gap-4">
      {/* Back + study link */}
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-[12.5px] font-medium text-primary transition-colors hover:text-primary/80"
        >
          <ArrowLeft size={14} /> Back to datasets
        </button>
        <Button variant="outline" size="sm" onClick={onOpenStudy} className="text-xs font-medium">
          Open study <ExternalLink className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Dataset header + inline profile stats */}
      <Card className="gap-0 rounded-xl border p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3.5">
            <span className="flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[9px] border border-border bg-secondary text-muted-foreground">
              <Database size={17} />
            </span>
            <div className="min-w-0">
              <div className="font-mono text-sm text-foreground">{d.name}</div>
              <div className="mt-0.5 text-[12px] text-muted-foreground/70">
                {d.study} · updated {d.when}
              </div>
            </div>
          </div>
          <StatusBadge d={d} />
        </div>
        <div className="mt-4 flex flex-wrap gap-x-7 gap-y-2 border-t border-border pt-3.5">
          {[
            ['Rows', d.rows, 'text-foreground'],
            ['Columns', d.cols, 'text-foreground'],
            ['Mapped', `${MAPPING_ROWS.length} / ${d.cols}`, 'text-[#27500A]'],
            ['Key', 'member_id', 'text-foreground font-mono'],
            ['Used in', '1 study', 'text-foreground'],
          ].map(([label, value, tone]) => (
            <div key={label} className="flex items-baseline gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">{label}</span>
              <span className={`text-[13px] font-semibold ${tone}`}>{value}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Sub-tabs */}
      <SubTabs
        className="mb-1"
        tabs={[
          { id: 'privacy',    label: 'Privacy',    icon: <Shield size={14} /> },
          { id: 'mapping',    label: 'Mapping',    icon: <Workflow size={14} />, badge: 'beta' },
          { id: 'validation', label: 'Validation', icon: <CheckCircle2 size={14} />, badge: warnCount || undefined },
          { id: 'lineage',    label: 'Lineage',    icon: <GitBranch size={14} /> },
        ]}
        active={sub}
        onChange={setSub}
      />

      {/* ── PRIVACY ── */}
      {sub === 'privacy' && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-[#97C459] bg-secondary p-4">
            <div className="mb-1 flex items-center gap-1.5 text-[13px] font-semibold text-[#27500A]">
              <Shield size={15} strokeWidth={2.5} className="flex-shrink-0" />
              No direct PII detected
            </div>
            <div className="text-[12.5px] leading-[1.5] text-muted-foreground">
              Identifiers are pseudonymised or suppressed and dates are shifted. Consent scope: research use. Privacy is the first gate — nothing moves to mapping or studies until this stage is cleared.
            </div>
          </div>

          <Card className="gap-0 rounded-xl border p-5">
            <SectionTitle icon={<Shield size={15} className="text-primary" />} sub="Direct and quasi-identifiers, with the action taken">
              Identifiers detected &amp; handled
            </SectionTitle>
            <div className="flex flex-col gap-2">
              {PRIVACY_ROWS.map((r) => (
                <div key={r.col} className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 ${TONE[r.tone].wrap}`}>
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-[12px] text-foreground">{r.col}</div>
                    <div className="text-[11.5px] text-muted-foreground">{r.kind}</div>
                  </div>
                  <Tag color={TONE[r.tone].tag}>{r.action}</Tag>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── MAPPING ── */}
      {sub === 'mapping' && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
            <strong className="text-foreground">Mapping.</strong>{' '}
            Each column is bound to a proposed taxonomy role — exposure, outcome, confounder, or mediator — with a confidence score. Confirmed mappings make the dataset usable in studies.
          </div>

          <Card className="gap-0 rounded-xl border p-5">
            <SectionTitle icon={<Workflow size={15} className="text-primary" />} sub="Columns → Augura variable role · confirmed (demo)">
              Column → taxonomy role
            </SectionTitle>
            {/* header */}
            <div className="flex items-center gap-3 border-b border-border px-1 pb-2 text-[10.5px] font-semibold uppercase tracking-[0.05em] text-muted-foreground">
              <span className="flex-1">Source column</span>
              <span className="w-24">Role</span>
              <span className="w-12 text-right">Conf.</span>
              <span className="w-24 text-right">Status</span>
            </div>
            <div className="flex flex-col">
              {MAPPING_ROWS.map((r) => (
                <div key={r.col} className="flex items-center gap-3 border-b border-border px-1 py-2.5 last:border-b-0">
                  <span className="min-w-0 flex-1 font-mono text-[12px] text-foreground">{r.col}</span>
                  <span className="w-24"><Tag color={r.roleTone}>{r.role}</Tag></span>
                  <span className="w-12 text-right font-mono text-[12px] text-muted-foreground">{r.conf}</span>
                  <span className="flex w-24 justify-end">
                    <Tag color="g">Confirmed</Tag>
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── VALIDATION ── */}
      {sub === 'validation' && (
        <div className="flex flex-col gap-4">
          <div className={`rounded-xl border p-4 ${warnCount ? 'border-[#EF9F27] bg-[#FAEEDA]' : 'border-[#97C459] bg-secondary'}`}>
            <div className={`mb-1 flex items-center gap-1.5 text-[13px] font-semibold ${warnCount ? 'text-[#854F0B]' : 'text-[#27500A]'}`}>
              {warnCount
                ? <AlertTriangle size={15} strokeWidth={2.5} className="flex-shrink-0" />
                : <CheckCircle2 size={15} strokeWidth={2.5} className="flex-shrink-0" />}
              {warnCount
                ? `Usable · ${warnCount} soft flag${warnCount === 1 ? '' : 's'} to triage`
                : 'All data-quality checks passed'}
            </div>
            <div className="text-[12.5px] leading-[1.5] text-muted-foreground">
              {VALIDATION_ROWS.length - warnCount} of {VALIDATION_ROWS.length} checks passed · 0 hard flags. Soft flags do not block release but need a human decision.
            </div>
          </div>

          <Card className="gap-0 rounded-xl border p-5">
            <SectionTitle icon={<CheckCircle2 size={15} className="text-primary" />} sub="Row count, missingness, types, constants, duplicates">
              Data-quality checks
            </SectionTitle>
            <div className="flex flex-col gap-2">
              {VALIDATION_ROWS.map((r) => {
                const t = TONE[r.tone]
                return (
                  <ScanRow
                    key={r.check}
                    left={r.check}
                    kind={r.detail}
                    right={r.tone === 'warn' ? 'Warn' : 'Pass'}
                    rightTone={t.text}
                    badge={r.tone}
                  />
                )
              })}
            </div>
          </Card>
        </div>
      )}

      {/* ── LINEAGE ── */}
      {sub === 'lineage' && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
            <strong className="text-foreground">Lineage.</strong>{' '}
            Every transformation from source to current state — versioned, replayable, auditable.
          </div>

          <Card className="gap-0 rounded-xl border p-5">
            <SectionTitle icon={<GitBranch size={15} className="text-primary" />} sub="Source → transforms → uses">
              Transformation trace
            </SectionTitle>
            <div className="flex flex-col">
              {LINEAGE_STEPS.map((s) => (
                <div key={s.label} className="flex gap-3">
                  {/* rail */}
                  <div className="flex w-4 flex-shrink-0 flex-col items-center">
                    <span
                      className={`mt-1 h-2.5 w-2.5 flex-shrink-0 rounded-full ${
                        s.kind === 'source' ? 'bg-primary' : 'border-2 border-primary bg-card'
                      }`}
                    />
                    <span className="w-px flex-1 bg-border" />
                  </div>
                  <div className="pb-4">
                    <div className="flex items-center gap-2">
                      <span className="text-[12.5px] font-semibold text-foreground">{s.label}</span>
                      <Tag color={s.kind === 'source' ? 'b' : 'g'}>{s.kind === 'source' ? 'Source' : 'Transform'}</Tag>
                    </div>
                    <div className="mt-0.5 text-[12px] leading-[1.45] text-muted-foreground">{s.detail}</div>
                  </div>
                </div>
              ))}
              {/* terminal: used by */}
              <div className="flex gap-3">
                <div className="flex w-4 flex-shrink-0 flex-col items-center">
                  <ArrowRight size={14} className="rotate-90 text-primary" />
                </div>
                <div>
                  <div className="text-[12.5px] font-semibold text-foreground">Used by</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {LINEAGE_USES.map((u) => (
                      <Tag key={u} color="p">{u}</Tag>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

export function DatasetsPage() {
  const { data: datasets, loading } = useCollection('datasets')
  const { data: studies } = useCollection('studies')
  const { openStudy } = useStudyNav()
  const [adding, setAdding] = useState(false)
  const [selectedDataset, setSelectedDataset] = useState(null)
  const studyOptions = studies.map((s) => s.name)

  // Detail view replaces the list (sketch: "← Back to datasets" header).
  if (selectedDataset) {
    return (
      <WorkspacePage
        eyebrow="Library · Cohorts"
        title="Dataset"
        sub={`${selectedDataset.name} · ${selectedDataset.rows} rows · ${selectedDataset.cols} cols`}
      >
        <DatasetDetail
          d={selectedDataset}
          onBack={() => setSelectedDataset(null)}
          onOpenStudy={() => openStudy(selectedDataset.study)}
        />
      </WorkspacePage>
    )
  }

  return (
    <WorkspacePage
      eyebrow="Library · Cohorts"
      title="Data"
      sub={loading ? 'Loading…' : `${datasets.length} dataset${datasets.length === 1 ? '' : 's'} across your studies`}
      action={<Button onClick={() => setAdding(true)}><Plus className="h-3.5 w-3.5" /> Add dataset</Button>}
    >
      {loading ? (
        <Loading />
      ) : datasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets yet"
          subtitle="Add a dataset to start building your cohort library."
          cta={<Button onClick={() => setAdding(true)}><Plus className="h-3.5 w-3.5" /> Add dataset</Button>}
        />
      ) : (
        <Card className="gap-0 px-[18px] py-1">
          {datasets.map((d, i) => (
            <div
              key={d.id}
              onClick={() => setSelectedDataset(d)}
              className={`flex cursor-pointer items-center gap-3.5 py-[15px] transition-colors hover:bg-muted/30 ${i === datasets.length - 1 ? '' : 'border-b border-border'}`}
            >
              {/* Icon chip */}
              <span className="flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[9px] border border-border bg-secondary text-muted-foreground">
                <Database size={17} />
              </span>
              {/* Name + meta */}
              <div className="min-w-0 flex-1">
                <div className="font-mono text-sm text-foreground">{d.name}</div>
                <div className="mt-0.5 text-[12px] text-muted-foreground/70">
                  {d.study} · updated {d.when}
                </div>
              </div>
              {/* Rows × cols */}
              <div className="w-32 flex-shrink-0 text-right font-mono text-[12.5px] text-muted-foreground">
                {d.rows} rows · {d.cols} cols
              </div>
              {/* Status badge */}
              <div className="flex w-24 flex-shrink-0 justify-end">
                <StatusBadge d={d} />
              </div>
              {/* Arrow */}
              <ArrowRight size={15} className="flex-shrink-0 text-muted-foreground/30" />
            </div>
          ))}
        </Card>
      )}
      {adding && (
        <AddItemModal
          title="Add dataset"
          submitLabel="Add dataset"
          subtitle="Register a cohort dataset in your workspace."
          fields={[
            { key: 'name', label: 'Dataset name', placeholder: 'e.g. cohort_2026.xlsx', required: true },
            { key: 'study', label: 'Study', type: 'select', options: studyOptions },
            { key: 'rows', label: 'Rows', type: 'number', placeholder: '824' },
            { key: 'cols', label: 'Columns', type: 'number', placeholder: '18' },
          ]}
          onClose={() => setAdding(false)}
          onSave={(f) => {
            addLocalItem('datasets', {
              id: localId('ds'),
              name: f.name,
              study: f.study || '—',
              rows: Number(f.rows) || 0,
              cols: Number(f.cols) || 0,
              state: 'draft',
              when: 'just now',
            })
            setAdding(false)
          }}
        />
      )}
    </WorkspacePage>
  )
}
