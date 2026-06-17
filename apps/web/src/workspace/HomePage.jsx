import { useNavigate } from 'react-router-dom'
import {
  ClipboardList, Activity, Database, Flag, Plus, ArrowRight, BookOpen,
  FlaskConical, Shield, FileText,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Ico } from '@/cockpit/icons'
import { useCollection } from '@/workspace/dataClient'
import { Loading, EmptyState } from '@/workspace/CollectionStates'

// ── Local viz helpers ──────────────────────────────────────────────────────

function StepDots({ steps }) {
  const COLOR = {
    done:    'bg-primary',
    active:  'bg-[#3172B0]',
    pending: 'bg-[#B98900]',
    locked:  'bg-black/15',
  }
  return (
    <div className="flex items-center gap-[3px]">
      {steps.map((s) => (
        <span
          key={s.key}
          className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${COLOR[s.state] ?? 'bg-black/15'}`}
        />
      ))}
    </div>
  )
}

function MiniProgress({ value, color }) {
  return (
    <div className="h-1.5 w-full rounded-full bg-black/[0.08]">
      <div
        className="h-full rounded-full"
        style={{ width: `${value}%`, background: color }}
      />
    </div>
  )
}

// ── Corpus icon map ────────────────────────────────────────────────────────

const CORPUS_ICON = {
  book:   BookOpen,
  flask:  FlaskConical,
  shield: Shield,
  page:   FileText,
}

// ── Tone map for action rows ───────────────────────────────────────────────

const TONE = {
  amber:    { c: '#B98900', bg: 'rgba(232,184,0,0.16)' },
  bluecorn: { c: '#3172B0', bg: 'rgba(49,114,176,0.12)' },
  carmine:  { c: '#C0392B', bg: 'rgba(192,57,43,0.10)' },
}

// ── Section heading ────────────────────────────────────────────────────────

function SectionHead({ children, action }) {
  return (
    <div className="mb-3.5 flex items-baseline justify-between">
      <h2 className="m-0 text-[15.5px] font-semibold tracking-[-0.01em] text-foreground">
        {children}
      </h2>
      {action}
    </div>
  )
}

// ── Study card ─────────────────────────────────────────────────────────────

function StudyCard({ s, onOpen }) {
  const steps = s.steps || []
  const activeStepDef = steps[(s.activeStep || 1) - 1]
  return (
    <Card
      onClick={() => onOpen(s.id)}
      className="gap-0 flex cursor-pointer flex-col overflow-hidden p-0 transition-colors hover:border-primary/40"
    >
      {/* Top body */}
      <div className="p-[18px_20px_16px]">
        <div className="flex items-start gap-3.5">
          <span className="flex h-[42px] w-[42px] flex-shrink-0 items-center justify-center rounded-[11px] bg-secondary text-[18px] font-semibold text-primary">
            {s.initial}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[17px] font-semibold tracking-[-0.01em] text-foreground">
                {s.name}
              </span>
              {s.isNew && (
                <Badge variant="secondary" className="text-[10px] font-medium text-primary">
                  New
                </Badge>
              )}
            </div>
            <div className="mt-0.5 text-[13px] text-muted-foreground">{s.tagline}</div>
          </div>
        </div>
        <div className="mt-3.5 flex flex-wrap gap-1.5">
          <Badge variant="outline" className="text-[10.5px] font-normal text-muted-foreground">
            {s.category}
          </Badge>
          <Badge variant="outline" className="text-[10.5px] font-normal text-muted-foreground">
            N = {(s.n ?? 0).toLocaleString()}
          </Badge>
          <Badge variant="secondary" className="text-[10.5px] font-normal text-primary">
            {(s.framework || '').split(' · ')[0]}
          </Badge>
        </div>
      </div>

      {/* Progress footer band */}
      <div className="border-t border-border bg-black/[0.012] px-5 py-3.5">
        <div className="mb-2 flex items-center justify-between">
          <span className="whitespace-nowrap text-[12px] text-muted-foreground">
            <b className="font-mono font-medium text-foreground">{s.done}</b>
            {' '}of {s.total} ·{' '}
            <span className="font-medium text-primary">{s.readiness}% ready</span>
          </span>
          <span className="text-[11.5px] text-muted-foreground/70">{s.updated}</span>
        </div>
        <StepDots steps={steps} />
      </div>

      {/* Resume row */}
      <div className="flex items-center justify-between border-t border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/70">
            Up next
          </span>
          <span className="flex min-w-0 items-center gap-1.5 text-[13px] font-medium text-foreground/80">
            {activeStepDef && (
              <Ico name={activeStepDef.icon} size={14} color="var(--color-primary)" />
            )}
            <span className="truncate">
              {s.activeStep} · {activeStepDef?.label}
            </span>
          </span>
        </div>
        <span className="flex flex-shrink-0 items-center gap-1 text-[13px] font-medium text-primary">
          Resume <ArrowRight size={15} />
        </span>
      </div>
    </Card>
  )
}

// ── Action row ─────────────────────────────────────────────────────────────

function ActionRow({ a, study, onOpen, last }) {
  const tn = TONE[a.tone] || TONE.bluecorn
  return (
    <div
      onClick={() => onOpen(study.id)}
      className={`flex cursor-pointer items-center gap-3 py-3 px-1 transition-colors hover:bg-black/[0.015] ${last ? '' : 'border-b border-border'}`}
    >
      <span
        className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-[8px]"
        style={{ background: tn.bg, color: tn.c }}
      >
        <Ico name={a.icon} size={15} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-medium leading-snug text-foreground">{a.title}</div>
        <div className="mt-0.5 text-[11.5px] text-muted-foreground/80">
          {study.name} · {a.meta}
        </div>
      </div>
      <ArrowRight size={15} className="flex-shrink-0 text-muted-foreground/40" />
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export function HomePage() {
  const navigate = useNavigate()
  const { data: studies, loading: studiesLoading } = useCollection('studies')
  const { data: runs } = useCollection('runs')
  const { data: corpusSources } = useCollection('corpus_sources')
  const corpusTotal = corpusSources.reduce((sum, s) => sum + (s.count || 0), 0)

  const allActions = []
  studies.forEach((s) => (s.actions || []).forEach((a) => allActions.push({ a, study: s })))

  if (studiesLoading) {
    return (
      <div className="mx-auto max-w-[1200px] px-5 py-9">
        <Loading label="Loading your workspace…" />
      </div>
    )
  }

  // Real mode with no studies → onboarding empty state.
  if (studies.length === 0) {
    return (
      <div className="mx-auto max-w-[1200px] px-5 py-9 pb-24">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-primary">
              Evidence intelligence · Workspace
            </div>
            <h1 className="mt-2 text-[30px] font-semibold tracking-[-0.022em] text-foreground">
              Welcome
            </h1>
            <p className="mt-1.5 text-[15px] text-muted-foreground">
              No studies yet — create your first study to get started.
            </p>
          </div>
          <Button onClick={() => navigate('/studies/new')}>
            <Plus className="h-3.5 w-3.5" />
            New study
          </Button>
        </div>
        <EmptyState
          icon={ClipboardList}
          title="No active studies"
          subtitle="A study takes you from cohort upload through agentic profiling, causal design, digital-twin simulation, and a submission-ready dossier."
          cta={
            <Button onClick={() => navigate('/studies/new')}>
              <Plus className="h-3.5 w-3.5" />
              New study
            </Button>
          }
        />
      </div>
    )
  }

  const totalSubjects = studies.reduce((n, s) => n + (s.n || 0), 0)
  const runningNow = runs.filter((r) => r.state === 'running').length
  const STAT_CARDS = [
    {
      label: 'Studies in flight',
      value: String(studies.length),
      sub: 'across your workspace',
      Icon: ClipboardList,
    },
    {
      label: 'Audit',
      value: String(runs.length),
      sub: runningNow ? `${runningNow} running now` : 'all complete',
      Icon: Activity,
    },
    {
      label: 'Cohort subjects',
      value: totalSubjects.toLocaleString(),
      sub: `across ${studies.length} stud${studies.length === 1 ? 'y' : 'ies'}`,
      Icon: Database,
    },
    {
      label: 'Open flags',
      value: String(allActions.length),
      sub: allActions.length ? 'need attention' : 'all clear',
      Icon: Flag,
    },
  ]

  return (
    <div className="mx-auto max-w-[1200px] px-5 py-9 pb-24">
      {/* ── Header ── */}
      <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-primary">
            Evidence intelligence · Workspace
          </div>
          <h1 className="mt-2 text-[30px] font-semibold tracking-[-0.022em] text-foreground">
            Good afternoon
          </h1>
          <p className="mt-1.5 text-[15px] text-muted-foreground">
            {studies.length} active stud{studies.length === 1 ? 'y' : 'ies'}
            {allActions.length > 0 && (
              <>
                {' · '}
                <span className="font-medium" style={{ color: '#B98900' }}>
                  {allActions.length} item{allActions.length === 1 ? '' : 's'} need attention
                </span>
              </>
            )}
          </p>
        </div>
        <Button onClick={() => navigate('/studies/new')}>
          <Plus className="h-3.5 w-3.5" />
          New study
        </Button>
      </div>

      {/* ── Stat strip ── */}
      <div className="mb-7 grid grid-cols-2 gap-3.5 lg:grid-cols-4">
        {STAT_CARDS.map((m) => (
          <Card key={m.label} className="gap-0 p-[15px_17px]">
            <div className="flex items-center justify-between">
              <span className="text-[11.5px] font-medium text-muted-foreground">{m.label}</span>
              <m.Icon size={15} className="text-muted-foreground/50" />
            </div>
            <div className="mt-2">
              <div className="font-mono text-[26px] font-medium leading-none tracking-[-0.01em] text-foreground">
                {m.value}
              </div>
              <div className="mt-1.5 text-[11.5px] text-muted-foreground/70">{m.sub}</div>
            </div>
          </Card>
        ))}
      </div>

      {/* ── Two-column body ── */}
      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.62fr_1fr] lg:gap-6">
        {/* LEFT */}
        <div className="flex flex-col gap-6">
          {/* Active studies */}
          <section>
            <SectionHead
              action={
                <Button variant="ghost" size="sm" className="h-7 px-3 text-[12.5px]" onClick={() => navigate('/studies')}>
                  All studies
                </Button>
              }
            >
              Active studies
            </SectionHead>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {studies.map((s) => (
                <StudyCard key={s.id} s={s} onOpen={(id) => navigate(`/studies/${id}`)} />
              ))}
            </div>
          </section>

          {/* Recent runs */}
          <section>
            <SectionHead>Recent runs</SectionHead>
            {runs.length === 0 ? (
              <Card className="gap-0 px-[18px] py-8 text-center text-[13px] text-muted-foreground">
                No runs yet.
              </Card>
            ) : (
              <Card className="gap-0 px-[18px] py-1">
                {runs.map((r, i) => (
                  <div
                    key={r.id}
                    className={`flex items-center gap-3.5 py-3.5 ${i === runs.length - 1 ? '' : 'border-b border-border'}`}
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
                    <div className="w-16 text-right">
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
                    <div className="w-16 text-right text-[11.5px] text-muted-foreground">
                      {r.when}
                    </div>
                  </div>
                ))}
              </Card>
            )}
          </section>
        </div>

        {/* RIGHT */}
        <div className="flex flex-col gap-5 lg:sticky lg:top-4">
          {/* What needs attention */}
          <Card
            className="gap-0 px-[18px] py-4"
            style={{ borderColor: 'rgba(185,137,0,0.30)' }}
          >
            <div className="mb-1.5 flex items-center gap-2">
              <Flag size={16} style={{ color: '#B98900' }} />
              <h2 className="m-0 whitespace-nowrap text-[15px] font-semibold text-foreground">
                What needs attention
              </h2>
            </div>
            {allActions.length === 0 ? (
              <p className="mb-1 mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
                All clear — no open gates right now.
              </p>
            ) : (
              <>
                <p className="mb-2 text-[12.5px] leading-relaxed text-muted-foreground">
                  Resolve to unlock the next workflow gate.
                </p>
                {allActions.map(({ a, study }, i) => (
                  <ActionRow
                    key={a.id}
                    a={a}
                    study={study}
                    onOpen={(id) => navigate(`/studies/${id}`)}
                    last={i === allActions.length - 1}
                  />
                ))}
              </>
            )}
          </Card>

          {/* Evidence readiness */}
          <Card className="gap-0 px-[18px] py-4">
            <h2 className="mb-3.5 text-[15px] font-semibold text-foreground">
              Evidence readiness
            </h2>
            {studies.map((s) => (
              <div key={s.id} className="mb-3.5">
                <div className="mb-1.5 flex items-baseline justify-between">
                  <span className="text-[13px] font-medium text-foreground/80">{s.name}</span>
                  <span className="font-mono text-[12.5px] text-foreground">{s.readiness}%</span>
                </div>
                <MiniProgress
                  value={s.readiness}
                  color={s.readiness > 50 ? '#047857' : '#3172B0'}
                />
              </div>
            ))}
          </Card>

          {/* Datasets & corpus */}
          <Card className="gap-0 px-[18px] py-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="m-0 text-[15px] font-semibold text-foreground">
                Datasets & corpus
              </h2>
              {corpusTotal > 0 && (
                <span className="font-mono text-[11.5px] text-muted-foreground">
                  {corpusTotal.toLocaleString()} docs
                </span>
              )}
            </div>
            {corpusSources.length === 0 ? (
              <p className="text-[12.5px] text-muted-foreground">No corpus indexed yet.</p>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {corpusSources.map((src) => {
                  const CorpusIcon = CORPUS_ICON[src.icon] ?? FileText
                  return (
                    <div
                      key={src.name}
                      className="flex items-center gap-2.5 rounded-lg border border-border bg-secondary/30 px-3 py-2.5"
                    >
                      <CorpusIcon size={15} className="flex-shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <div className="font-mono text-[13px] text-foreground">{src.count}</div>
                        <div className="truncate text-[10.5px] text-muted-foreground">
                          {src.name}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
