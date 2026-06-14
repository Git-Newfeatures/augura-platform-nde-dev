import { useState } from 'react'
import {
  BookOpen, FlaskConical, Shield, FileText, Library, Plus,
  Grid3x3, Bookmark, Target, Search as SearchIcon, ArrowRight, Sparkles, AlertTriangle,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SubTabs } from '@/cockpit/SubTabs'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { openSearch } from '@/shell/searchBus'
import { AddItemModal } from '@/workspace/AddItemModal'
import { addLocalItem } from '@/workspace/localData'

const CORPUS_ICON = {
  book:   BookOpen,
  flask:  FlaskConical,
  shield: Shield,
  page:   FileText,
}

// ── Coverage heatmap (jurisdiction × evidence type) — demo doc counts ──────────
// Mirrors the navigation sketch's KB heatmap. Cells shade by document density on
// a green-intensity scale; sparse cells are flagged as strategic gaps (carmine).
const HEAT_COLS = ['FDA', 'EMA', 'MHRA', 'HAS']
const HEAT_ROWS = [
  { label: 'Guidance',       cells: [87, 42, 18, 14] },
  { label: 'RCT',            cells: [142, 98, 34, 21] },
  { label: 'RWE',            cells: [88, 71, 29, 12] },
  { label: 'Adverse events', cells: [76, 44, 9, 3] },
]

// Bucket a doc count into a 5-step green-intensity scale (0 = strategic gap).
function heatTone(n) {
  if (n <= 5)  return { bg: '#FCEBEB', fg: '#791F1F' }            // gap — carmine wash
  if (n <= 15) return { bg: '#EAF3DE', fg: '#27500A' }            // lvl1
  if (n <= 40) return { bg: '#9FE1CB', fg: '#085041' }            // lvl2
  if (n <= 90) return { bg: '#5DCAA5', fg: '#FFFFFF' }            // lvl3
  return { bg: '#0F6E56', fg: '#FFFFFF' }                          // lvl4
}

function CoverageHeatmap() {
  return (
    <Card className="gap-0 rounded-xl border p-5">
      <div className="mb-1 flex items-center gap-1.5 text-[15px] font-semibold text-foreground">
        <Grid3x3 size={15} className="text-primary" /> Coverage heatmap
      </div>
      <p className="mb-3.5 text-[12px] text-muted-foreground">
        Jurisdiction × evidence type · document density per cell · red cells are strategic gaps.
      </p>
      <div
        className="grid items-center gap-1"
        style={{ gridTemplateColumns: `96px repeat(${HEAT_COLS.length}, 1fr)` }}
      >
        <div />
        {HEAT_COLS.map((c) => (
          <div key={c} className="px-1 py-1.5 text-center text-[11px] font-semibold text-muted-foreground">
            {c}
          </div>
        ))}
        {HEAT_ROWS.map((row) => (
          <div key={row.label} className="contents">
            <div className="py-2 pr-2 text-[11.5px] font-medium text-muted-foreground">{row.label}</div>
            {row.cells.map((n, i) => {
              const t = heatTone(n)
              return (
                <div
                  key={`${row.label}-${HEAT_COLS[i]}`}
                  className="rounded-md py-2 text-center font-mono text-[12px] font-semibold"
                  style={{ background: t.bg, color: t.fg }}
                  title={`${HEAT_COLS[i]} · ${row.label} — ${n} documents`}
                >
                  {n}
                </div>
              )
            })}
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground/80">
        Red cells flagged as priority gaps by Augura strategy weights.
      </p>
    </Card>
  )
}

// ── Saved queries (demo) ──────────────────────────────────────────────────────
const SAVED_QUERIES = [
  { title: 'CGM in prediabetes prevention',                 meta: 'Romain · today',        domain: 'Cardiometabolic', count: 98 },
  { title: 'Home fetal monitoring · false-positive rates',  meta: 'Marie-Laure · yesterday', domain: 'Maternal-fetal', count: 47 },
  { title: 'SaMD De Novo precedents · cardiovascular',      meta: 'François · last week',  domain: 'SaMD general',    count: 31 },
]

function SavedQueries({ onOpen }) {
  return (
    <Card className="gap-0 rounded-xl border p-5">
      <div className="mb-1 flex items-center gap-1.5 text-[15px] font-semibold text-foreground">
        <Bookmark size={15} className="text-primary" /> Saved queries
      </div>
      <p className="mb-3.5 text-[12px] text-muted-foreground">
        Ad-hoc searches you or the team saved for re-use.
      </p>
      <div className="flex flex-col gap-2">
        {SAVED_QUERIES.map((q) => (
          <div
            key={q.title}
            className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5"
          >
            <div className="min-w-0">
              <div className="truncate text-[12.5px] font-medium text-foreground">{q.title}</div>
              <div className="text-[11px] text-muted-foreground">{q.meta} · {q.count} matches</div>
            </div>
            <Badge variant="outline" className="text-[10.5px] font-normal text-muted-foreground">
              {q.domain}
            </Badge>
            <Button variant="ghost" size="sm" className="h-7 px-3 text-[12px]" onClick={onOpen}>
              Open
            </Button>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ── Study matches (demo) ──────────────────────────────────────────────────────
// Corpus subsets the profiling agent matched to each active study.
const STUDY_MATCHES = [
  {
    initial: 'L', accent: '#047857', name: 'Lucis — preventive biomarker platform',
    tagline: 'Intensified biomarker monitoring → HbA1c at 6 months',
    matched: 124,
    breakdown: ['FDA · 47', 'EMA · 31', 'MHRA · 14', 'Global · 32', 'RCT · 38', 'RWE · 52', 'Guidance · 18'],
    top: [
      { score: 0.94, tone: 'g', cite: 'Continuous glucose monitoring in T2DM: 6-month outcomes', src: 'EMA RWE · 2024' },
      { score: 0.91, tone: 'g', cite: 'SaMD for biomarker-based prevention', src: 'FDA Guidance · 2024' },
      { score: 0.89, tone: 'g', cite: 'Engagement-mediated HbA1c reduction: meta-analysis', src: 'Cochrane · 2023' },
    ],
    more: 121,
    note: { tone: 'ok', label: 'Strong corpus support', text: '124 matches ≥ 0.75 — well-precedented question, not a novel estimand.' },
  },
  {
    initial: 'B', accent: '#3172B0', name: 'Bloomlife — wearable pregnancy monitoring',
    tagline: 'Continuous uterine activity monitoring → false-positive PTL admissions',
    matched: 87,
    breakdown: ['FDA · 28', 'EMA · 19', 'MHRA · 8', 'Global · 32', 'Trial · 24', 'RWE · 14', 'Guidance · 12'],
    top: [
      { score: 0.92, tone: 'g', cite: 'External vs internal tocodynamometry: false-positive rates', src: 'RCT · 2023' },
      { score: 0.78, tone: 'a', cite: 'FDA De Novo decision · uterine activity SaMD', src: 'Precedent · 2022' },
      { score: 0.76, tone: 'a', cite: 'Home monitoring & preterm labor admissions: cohort', src: 'RWE · 2024' },
    ],
    more: 84,
    note: { tone: 'warn', label: 'Near-novel estimand', text: 'Only 1 match ≥ 0.85 — the engagement-to-PTL-admission link is thinly precedented. Agent suggests eliciting priors from the user.' },
  },
]

const SCORE_TONE = {
  g: { bg: 'var(--color-secondary)', fg: 'var(--color-primary)' },
  a: { bg: '#FAEEDA', fg: '#854F0B' },
}
const NOTE_TONE = {
  ok:   'border-[#97C459] bg-secondary text-[#27500A]',
  warn: 'border-[#EF9F27] bg-[#FAEEDA] text-[#854F0B]',
}

function MatchCard({ s, onOpen }) {
  return (
    <Card className="gap-0 rounded-xl border p-5" style={{ borderLeft: `3px solid ${s.accent}` }}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-[9px] text-[13px] font-semibold text-white"
            style={{ background: s.accent }}
          >
            {s.initial}
          </span>
          <div>
            <div className="text-[13.5px] font-semibold text-foreground">{s.name}</div>
            <div className="text-[12px] italic text-muted-foreground">{s.tagline}</div>
          </div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <Badge variant="secondary" className="font-mono text-[11px] text-primary">{s.matched} matched</Badge>
          <Button variant="outline" size="sm" className="h-7 px-3 text-[12px]" onClick={onOpen}>
            Open study <ArrowRight size={13} />
          </Button>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {s.breakdown.map((b) => (
          <Badge key={b} variant="outline" className="font-mono text-[10.5px] font-normal text-muted-foreground">
            {b}
          </Badge>
        ))}
      </div>

      <div className="border-t border-border pt-3">
        <div className="mb-1.5 text-[12px] font-semibold text-foreground">Top matches</div>
        <div className="flex flex-col gap-1.5">
          {s.top.map((m) => {
            const t = SCORE_TONE[m.tone]
            return (
              <div key={m.cite} className="flex items-start gap-2 text-[12px] leading-snug">
                <span
                  className="mt-px flex-shrink-0 rounded px-1.5 py-px font-mono text-[10.5px] font-semibold"
                  style={{ background: t.bg, color: t.fg }}
                >
                  {m.score.toFixed(2)}
                </span>
                <span className="min-w-0 text-foreground/85">
                  {m.cite} <span className="text-muted-foreground">· {m.src}</span>
                </span>
              </div>
            )
          })}
          <div className="text-[11px] text-muted-foreground/80">+{s.more} more in the study's profiling output</div>
        </div>
      </div>

      <div className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2.5 text-[12px] leading-[1.5] ${NOTE_TONE[s.note.tone]}`}>
        {s.note.tone === 'ok'
          ? <Sparkles size={14} strokeWidth={2.5} className="mt-px flex-shrink-0" />
          : <AlertTriangle size={14} strokeWidth={2.5} className="mt-px flex-shrink-0" />}
        <span><strong>{s.note.label}.</strong> {s.note.text}</span>
      </div>
    </Card>
  )
}

// ── Ad-hoc query (demo) ───────────────────────────────────────────────────────
const ADHOC_RESULTS = [
  { score: 0.93, tone: 'g', cite: 'CGM in prediabetes: behavior change cohort', src: 'RWE · 2024',   pill: 'EMA' },
  { score: 0.89, tone: 'g', cite: 'SaMD guidance · biomarker-driven lifestyle intervention', src: 'Guidance · 2024', pill: 'FDA' },
  { score: 0.81, tone: 'a', cite: 'Continuous monitoring & HbA1c trajectory: meta-analysis', src: 'Cochrane · 2023', pill: 'Global' },
  { score: 0.77, tone: 'a', cite: 'Digital coaching adherence & glycemic control', src: 'RWE · 2022', pill: 'MHRA' },
]

function AdHocQuery() {
  const [q, setQ] = useState('')
  const [ran, setRan] = useState(false)

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
        <strong className="text-foreground">Explore the corpus without a study.</strong>{' '}
        Describe a product or question — the same matching logic that runs inside a study's profiling step runs here, untethered. Demo only.
      </div>

      <Card className="gap-0 rounded-xl border p-5">
        <div className="mb-1 text-[15px] font-semibold text-foreground">Describe what you're looking for</div>
        <p className="mb-3 text-[12px] text-muted-foreground">Free text — indication, intervention, and outcome.</p>
        <textarea
          rows={3}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. Wearable continuous glucose monitoring for prediabetes prevention; want regulatory precedents and comparable evidence."
          className="w-full resize-y rounded-lg border border-input bg-background px-3 py-2 text-[12.5px] outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        />
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" onClick={() => { setQ(''); setRan(false) }}>Clear</Button>
          <Button onClick={() => setRan(true)}>
            <SearchIcon className="h-3.5 w-3.5" /> Run query
          </Button>
        </div>
      </Card>

      {ran && (
        <Card className="gap-0 rounded-xl border p-5" style={{ borderLeft: '3px solid #047857' }}>
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[13.5px] font-semibold text-foreground">
                {q.trim() || 'Wearable continuous glucose monitoring for prediabetes prevention'}
              </div>
              <div className="mt-0.5 text-[12px] text-muted-foreground">
                98 matches · cardiometabolic · FDA + EMA · last 5 years
              </div>
            </div>
            <Badge variant="secondary" className="font-mono text-[11px] text-primary">98 results</Badge>
          </div>
          <div className="flex flex-col gap-1.5 border-t border-border pt-3">
            {ADHOC_RESULTS.map((m) => {
              const t = SCORE_TONE[m.tone]
              return (
                <div key={m.cite} className="flex items-start gap-2 text-[12px] leading-snug">
                  <span
                    className="mt-px flex-shrink-0 rounded px-1.5 py-px font-mono text-[10.5px] font-semibold"
                    style={{ background: t.bg, color: t.fg }}
                  >
                    {Math.round(m.score * 100)}%
                  </span>
                  <Badge variant="outline" className="mt-px flex-shrink-0 text-[10px] font-normal text-muted-foreground">
                    {m.pill}
                  </Badge>
                  <span className="min-w-0 text-foreground/85">
                    {m.cite} <span className="text-muted-foreground">· {m.src}</span>
                  </span>
                </div>
              )
            })}
            <div className="text-[11px] text-muted-foreground/80">+94 more</div>
          </div>
        </Card>
      )}
    </div>
  )
}

export function CorpusPage() {
  const { data: sources, loading } = useCollection('corpus_sources')
  const { data: coverage } = useCollection('corpus_coverage')
  const total = sources.reduce((sum, s) => sum + (s.count || 0), 0)
  const [adding, setAdding] = useState(false)
  const [sub, setSub] = useState('browse')

  return (
    <WorkspacePage
      eyebrow="Evidence base"
      title="Literature"
      sub={
        loading
          ? 'Loading…'
          : total
            ? `${total.toLocaleString()} indexed documents across ${sources.length} sources`
            : 'Tenant-wide evidence knowledge base'
      }
      action={
        <div className="flex gap-2">
          <Button variant="outline" onClick={openSearch}>Search</Button>
          <Button onClick={() => setAdding(true)}><Plus className="h-3.5 w-3.5" /> Add source</Button>
        </div>
      }
    >
      {loading ? (
        <Loading />
      ) : sources.length === 0 ? (
        <EmptyState
          icon={Library}
          title="No corpus indexed yet"
          subtitle="Add an evidence source (PubMed, ClinicalTrials.gov, MAUDE, FDA guidance) — or switch on Demo data to explore a sample corpus."
          cta={<Button onClick={() => setAdding(true)}><Plus className="h-3.5 w-3.5" /> Add source</Button>}
        />
      ) : (
        <>
          <SubTabs
            tabs={[
              { id: 'browse',  label: 'Browse',        icon: <Library size={14} /> },
              { id: 'matches', label: 'Study matches', icon: <Target size={14} />, badge: STUDY_MATCHES.length },
              { id: 'query',   label: 'Ad-hoc query',  icon: <SearchIcon size={14} /> },
            ]}
            active={sub}
            onChange={setSub}
          />

          {/* ════════════════════════ BROWSE ════════════════════════ */}
          {sub === 'browse' && (
            <>
              {/* source cards */}
              <div className="mb-[22px] grid grid-cols-2 gap-3.5 sm:grid-cols-4">
                {sources.map((s) => {
                  const CorpusIcon = CORPUS_ICON[s.icon] ?? FileText
                  return (
                    <Card key={s.name} className="gap-0 p-[18px]">
                      <span className="mb-3 flex h-9 w-9 items-center justify-center rounded-[9px] bg-secondary text-primary">
                        <CorpusIcon size={18} />
                      </span>
                      <div className="font-mono text-[24px] font-medium leading-none text-foreground">
                        {s.count}
                      </div>
                      <div className="mt-1.5 text-[13px] text-muted-foreground">{s.name}</div>
                    </Card>
                  )
                })}
              </div>

              {/* Coverage heatmap (jurisdiction × evidence type) */}
              <div className="mb-[22px]">
                <CoverageHeatmap />
              </div>

              {/* Coverage by product category */}
              {coverage.length > 0 && (
                <Card className="mb-[22px] gap-0 px-[22px] py-5">
                  <h3 className="m-0 text-[15px] font-semibold text-foreground">
                    Coverage by product category
                  </h3>
                  <p className="mt-1.5 mb-4 text-[13px] text-muted-foreground">
                    Indexed evidence relevant to your active studies.
                  </p>
                  {coverage.map((c) => (
                    <div key={c.label} className="mb-3.5">
                      <div className="mb-1.5 flex justify-between text-[13px] text-foreground/80">
                        <span>{c.label}</span>
                        <span className="font-mono text-foreground">{c.pct}%</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-black/[0.08]">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${c.pct}%`, background: c.color }}
                        />
                      </div>
                    </div>
                  ))}
                </Card>
              )}

              {/* Saved queries */}
              <SavedQueries onOpen={() => setSub('query')} />
            </>
          )}

          {/* ════════════════════════ STUDY MATCHES ════════════════════════ */}
          {sub === 'matches' && (
            <div className="flex flex-col gap-4">
              <div className="rounded-xl border border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
                <strong className="text-foreground">Documents matched by the profiling agent</strong>, grouped by active study. Each list is the corpus subset a study built up through its profiling run — surfaced here for cross-study insight.
              </div>
              {STUDY_MATCHES.map((s) => (
                <MatchCard key={s.name} s={s} onOpen={openSearch} />
              ))}
            </div>
          )}

          {/* ════════════════════════ AD-HOC QUERY ════════════════════════ */}
          {sub === 'query' && <AdHocQuery />}
        </>
      )}
      {adding && (
        <AddItemModal
          title="Add source"
          submitLabel="Add source"
          subtitle="Register an evidence source in the corpus."
          fields={[
            { key: 'name', label: 'Source name', placeholder: 'e.g. PubMed', required: true },
            { key: 'count', label: 'Indexed documents', type: 'number', placeholder: '1200' },
            { key: 'icon', label: 'Icon', type: 'select', options: [
              { value: 'book', label: 'Literature' },
              { value: 'flask', label: 'Trials' },
              { value: 'shield', label: 'Safety / adverse events' },
              { value: 'page', label: 'Guidance / document' },
            ] },
          ]}
          onClose={() => setAdding(false)}
          onSave={(f) => {
            addLocalItem('corpus_sources', {
              name: f.name,
              count: Number(f.count) || 0,
              icon: f.icon || 'page',
            })
            setAdding(false)
          }}
        />
      )}
    </WorkspacePage>
  )
}
