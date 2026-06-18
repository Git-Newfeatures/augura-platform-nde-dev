import { useState, useEffect, useRef } from 'react'
import {
  Database,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  Upload,
  Shield,
  Workflow,
  Activity,
  CheckCircle2,
  GitBranch,
  Check,
  AlertTriangle,
  Plus,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { SubTabs } from '@/cockpit/SubTabs'
import { CohortImport } from '@/workspace/CohortImport'
import { apiJson } from '@/api'
import { uploadDataset, mapDataset, runDq, getDq, listColumns } from '@/intake/intakeApi'

// Data workspace — port de la vue /datasets de Nico, recâblée sur le backend
// Quentin. Le flux intake (upload → mapping → data quality) vit ICI, par dataset,
// dans des sous-onglets — plus d'onglet « Intake » séparé.
// Upload/Mapping/Data Quality tapent les vraies routes (/datasets/upload,
// /{id}/map, /{id}/dq). Privacy/Validation/Lineage sont des placeholders « beta »
// (pas encore de backend), fidèles à la maquette de Nico.

// ── Small presentational helpers ──────────────────────────────────────────────
const TAG_CLS = {
  g: 'bg-secondary text-[#27500A] border-[#97C459]',
  a: 'bg-[#FAEEDA] text-[#854F0B] border-[#EF9F27]',
  b: 'bg-muted text-muted-foreground border-border',
  p: 'bg-purple-50 text-purple-700 border-purple-200',
  r: 'bg-red-50 text-red-700 border-red-200',
}
function Tag({ color = 'b', children }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10.5px] font-medium ${TAG_CLS[color] || TAG_CLS.b}`}>
      {children}
    </span>
  )
}

const TONE = {
  ok: { wrap: 'border-[#97C459] bg-secondary', text: 'text-[#27500A]', tag: 'g', Icon: Check },
  warn: { wrap: 'border-[#EF9F27] bg-[#FAEEDA]', text: 'text-[#854F0B]', tag: 'a', Icon: AlertTriangle },
  none: { wrap: 'border-border bg-card', text: 'text-muted-foreground', tag: 'b', Icon: Check },
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
      {right && <span className={`flex-shrink-0 text-[12px] ${rightTone ?? 'text-muted-foreground'}`}>{right}</span>}
    </div>
  )
}

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
      <Badge variant="outline" className="text-[#B98900] border-[#B98900]/30">
        {d.flags ?? 2} flags
      </Badge>
    )
  }
  if (d.state === 'draft') {
    return (
      <Badge variant="outline" className="text-[#3172B0] border-[#3172B0]/30">
        Draft
      </Badge>
    )
  }
  if (d.state === 'pending') {
    return (
      <Badge variant="outline" className="text-muted-foreground">
        Pending
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="text-muted-foreground">
      Locked
    </Badge>
  )
}

// ── Placeholder content (beta tabs — Privacy / Validation / Lineage) ───────────
const PRIVACY_ROWS = [
  { col: 'member_id', kind: 'Direct (record number)', action: 'Pseudonymised → member_id', tone: 'ok' },
  { col: 'age', kind: 'Quasi (age)', action: 'Retained · low re-id risk', tone: 'ok' },
  { col: 'sex', kind: 'Quasi (demographic)', action: 'Retained · low re-id risk', tone: 'ok' },
  { col: 'visit_date_*', kind: 'Quasi (dates)', action: 'Shifted · intervals kept', tone: 'ok' },
  { col: 'region', kind: 'Quasi (geo)', action: 'Generalised to region', tone: 'warn' },
  { col: 'hba1c_*', kind: 'Clinical measure', action: 'No identifier · retained', tone: 'none' },
]
const VALIDATION_ROWS = [
  { check: 'Row count', detail: 'Matches manifest · within expected range', tone: 'ok' },
  { check: 'Missingness', detail: 'Max 6.1% on hba1c_12m · all under 10% threshold', tone: 'ok' },
  { check: 'Type checks', detail: 'Every column matches its declared type', tone: 'ok' },
  { check: 'Constant columns', detail: 'No zero-variance columns detected', tone: 'ok' },
  { check: 'Duplicate rows', detail: '2 near-duplicate member_id × visit pairs', tone: 'warn' },
  { check: 'Primary key', detail: 'member_id × visit unique across all rows', tone: 'ok' },
]
const LINEAGE_STEPS = [
  { kind: 'source', label: 'Uploaded file', detail: 'Original wide-format spreadsheet · sha256:a7f2…' },
  { kind: 'transform', label: 'Server-side parse + profile', detail: 'Columns typed, null %, distinct counts' },
  { kind: 'transform', label: 'Taxonomy mapping', detail: 'Columns bound to Augura concepts' },
  { kind: 'transform', label: 'Data-quality pass', detail: 'Completeness, validity, consistency checks' },
]
const LINEAGE_USES = ['Causal model', 'Power simulation']

const BetaNote = ({ children }) => (
  <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
    {children}
  </div>
)

// ── Upload tab (real: POST /datasets/upload → new dataset) ─────────────────────
function UploadPanel({ columns, onUploaded }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const fileRef = useRef(null)

  async function handleFiles(fileList) {
    const file = fileList?.[0]
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const result = await uploadDataset(file)
      onUploaded(result)
    } catch (e) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="gap-0 rounded-xl border p-5">
        <SectionTitle
          icon={<Upload size={15} className="text-primary" />}
          sub="CSV or Excel — parsed and profiled server-side. Uploading creates a new dataset."
        >
          Upload dataset files
        </SectionTitle>
        <div
          onClick={() => fileRef.current?.click()}
          onDrop={(e) => {
            e.preventDefault()
            handleFiles(e.dataTransfer.files)
          }}
          onDragOver={(e) => e.preventDefault()}
          className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-border bg-secondary/40 px-6 py-8 text-center transition-colors hover:bg-secondary/80"
        >
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
          {busy ? (
            <span className="text-[12px] italic text-muted-foreground">Uploading &amp; profiling…</span>
          ) : (
            <>
              <Upload size={22} className="mb-2 text-muted-foreground" />
              <span className="text-[12px] font-medium text-foreground">Click or drag to upload</span>
              <span className="mt-1 text-[11px] text-muted-foreground">
                <strong>.csv · .xlsx · .xls</strong>
              </span>
            </>
          )}
          {error && <span className="mt-2 text-[10.5px] text-destructive">{error}</span>}
        </div>
      </Card>

      {columns && columns.length > 0 && <ColumnsTable columns={columns} />}
    </div>
  )
}

// ── Profiled columns table (GET /datasets/{id}/columns) ───────────────────────
function ColumnsTable({ columns }) {
  return (
    <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Column</th>
            <th className="px-4 py-2.5 font-medium">Sheet</th>
            <th className="px-4 py-2.5 font-medium">Type</th>
            <th className="px-4 py-2.5 font-medium text-right">Null %</th>
            <th className="px-4 py-2.5 font-medium text-right">Distinct</th>
            <th className="px-4 py-2.5 font-medium">Role</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((c) => (
            <tr key={c.id} className="border-b border-border/60 last:border-0">
              <td className="px-4 py-2 font-mono text-foreground">{c.name}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.sheet}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.value_kind ?? '—'}</td>
              <td className="px-4 py-2 text-right font-mono text-muted-foreground">
                {c.null_pct != null ? `${Math.round(c.null_pct <= 1 ? c.null_pct * 100 : c.null_pct)}%` : '—'}
              </td>
              <td className="px-4 py-2 text-right font-mono text-muted-foreground">{c.n_distinct ?? '—'}</td>
              <td className="px-4 py-2">
                {c.final_role || c.proposed_role ? (
                  <Badge variant="secondary" className="text-primary">
                    {c.final_role || c.proposed_role}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

// ── Mapping tab (POST /datasets/{id}/map) ─────────────────────────────────────
function ConfBadge({ score, label }) {
  if (score == null) return <span className="text-[10px] text-muted-foreground">{label || '—'}</span>
  const pct = Math.round(score * 100)
  const cls =
    score >= 0.8
      ? 'border-green-300 bg-green-50 text-green-700'
      : score >= 0.6
        ? 'border-amber-300 bg-amber-50 text-amber-700'
        : score >= 0.4
          ? 'border-red-300 bg-red-50 text-red-600'
          : 'border-border text-muted-foreground'
  return (
    <Badge variant="outline" className={`font-mono text-[10px] ${cls}`}>
      {label ? `${label} ${pct}%` : `${pct}%`}
    </Badge>
  )
}

function MappingPanel({ result }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-2.5">
        {[
          ['Mapped', `${result.mapped_count ?? 0} / ${result.total_count ?? 0}`],
          [
            'Avg confidence',
            result.avg_confidence != null ? `${Math.round(result.avg_confidence * 100)}%` : '—',
          ],
          ['Unmapped', (result.total_count ?? 0) - (result.mapped_count ?? 0)],
        ].map(([label, value]) => (
          <Card key={label} className="gap-0 rounded-xl border p-3 text-center">
            <div className="font-mono text-[20px] font-bold text-foreground">{value}</div>
            <div className="text-[10px] text-muted-foreground">{label}</div>
          </Card>
        ))}
      </div>

      <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
              <th className="px-4 py-2.5 font-medium">Source column</th>
              <th className="px-4 py-2.5 font-medium">Proposed concept</th>
              <th className="px-4 py-2.5 font-medium text-right">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {(result.columns || []).map((c) => (
              <tr key={c.column} className="border-b border-border/60 last:border-0">
                <td className="px-4 py-2 font-mono text-foreground">{c.column}</td>
                <td className="px-4 py-2 font-mono text-[11.5px] text-muted-foreground">
                  {c.proposed_canonical_id ?? <em className="text-muted-foreground/50">Unmapped</em>}
                </td>
                <td className="px-4 py-2 text-right">
                  <ConfBadge score={c.confidence} label={c.confidence_label} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

// ── Data Quality tab (POST + GET /datasets/{id}/dq) ───────────────────────────
function DqPanel({ run, bundle }) {
  const findings = bundle?.bundle?.provenance ?? []
  const scorePct = run.overall_score != null ? `${Math.round(run.overall_score * 100)}%` : '—'
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">Score: {scorePct}</Badge>
        <Badge variant="outline" className="text-muted-foreground">
          Status: {run.status ?? '—'}
        </Badge>
        <Badge variant="outline" className="text-muted-foreground">
          {findings.length} finding{findings.length === 1 ? '' : 's'}
        </Badge>
      </div>
      {findings.length === 0 ? (
        <EmptyState icon={Activity} title="No findings" subtitle="The data-quality pass returned no flagged checks." />
      ) : (
        <Card className="gap-0 rounded-xl border p-4">
          <ul className="flex flex-col">
            {findings.slice(0, 50).map((f, i) => (
              <li key={i} className="border-b border-border/60 py-1.5 text-[12.5px] last:border-0">
                <span className="mr-1.5 font-mono text-[10.5px] uppercase text-muted-foreground">[{f.severity}]</span>
                {f.message}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}

// ── Dataset detail (inline view that replaces the list) ───────────────────────
function DatasetDetail({ d, onBack, onOpenStudy, onUploaded }) {
  const isEmpty = !d.cols || d.cols === '—' || d.cols === 0
  const [sub, setSub] = useState(isEmpty ? 'upload' : 'mapping')
  const [columns, setColumns] = useState(null)
  const [meta, setMeta] = useState(null)

  // Mapping (lazy, cached) — runs on first visit to the Mapping tab.
  const [mapping, setMapping] = useState(null)
  const [mapBusy, setMapBusy] = useState(false)
  const [mapError, setMapError] = useState(null)

  // Data quality (lazy, cached) — runs on first visit to the DQ tab.
  const [dqRun, setDqRun] = useState(null)
  const [dqBundle, setDqBundle] = useState(null)
  const [dqBusy, setDqBusy] = useState(false)
  const [dqError, setDqError] = useState(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      const [cols, single] = await Promise.all([
        listColumns(d.id).catch(() => []),
        apiJson(`/datasets/${d.id}`).catch(() => null),
      ])
      if (!alive) return
      setColumns(Array.isArray(cols) ? cols : [])
      setMeta(single)
      // Lazy-load the default tab's data (post-await: not a synchronous effect setState).
      if (sub === 'mapping') ensureMapping()
      if (sub === 'dq') ensureDq()
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.id])

  async function ensureMapping() {
    if (mapping || mapBusy) return
    setMapBusy(true)
    setMapError(null)
    try {
      setMapping(await mapDataset(d.id))
    } catch (e) {
      setMapError(String(e?.message || e))
    } finally {
      setMapBusy(false)
    }
  }

  async function ensureDq() {
    if (dqRun || dqBusy) return
    setDqBusy(true)
    setDqError(null)
    try {
      const run = await runDq(d.id)
      setDqRun(run)
      setDqBundle(await getDq(d.id).catch(() => null))
    } catch (e) {
      setDqError(String(e?.message || e))
    } finally {
      setDqBusy(false)
    }
  }

  function goto(id) {
    setSub(id)
    if (id === 'mapping') ensureMapping()
    if (id === 'dq') ensureDq()
  }

  const rowsLabel = meta?.row_count != null ? Number(meta.row_count).toLocaleString() : d.rows
  const colsLabel = meta?.column_count != null ? meta.column_count : d.cols
  const mappedLabel = mapping ? `${mapping.mapped_count ?? 0} / ${mapping.total_count ?? 0}` : '—'
  const keyCol =
    (columns || []).find((c) => (c.final_role || c.proposed_role) === 'entity_id')?.name ?? '—'

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-[12.5px] font-medium text-primary transition-colors hover:text-primary/80"
        >
          <ArrowLeft size={14} /> Back to datasets
        </button>
        {d.study && (
          <Button variant="outline" size="sm" onClick={onOpenStudy} className="text-xs font-medium">
            Open study <ExternalLink className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      <Card className="gap-0 rounded-xl border p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3.5">
            <span className="flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[9px] border border-border bg-secondary text-muted-foreground">
              <Database size={17} />
            </span>
            <div className="min-w-0">
              <div className="font-mono text-sm text-foreground">{d.name}</div>
              <div className="mt-0.5 text-[12px] text-muted-foreground/70">
                {d.study || '—'} · updated {d.when}
              </div>
            </div>
          </div>
          <StatusBadge d={d} />
        </div>
        <div className="mt-4 flex flex-wrap gap-x-7 gap-y-2 border-t border-border pt-3.5">
          {[
            ['Rows', rowsLabel, 'text-foreground'],
            ['Columns', colsLabel, 'text-foreground'],
            ['Mapped', mappedLabel, 'text-[#27500A]'],
            ['Key', keyCol, 'text-foreground font-mono'],
            ['Used in', d.study ? '1 study' : '—', 'text-foreground'],
          ].map(([label, value, tone]) => (
            <div key={label} className="flex items-baseline gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">{label}</span>
              <span className={`text-[13px] font-semibold ${tone}`}>{value}</span>
            </div>
          ))}
        </div>
      </Card>

      <SubTabs
        className="mb-1"
        tabs={[
          { id: 'upload', label: 'Upload', icon: <Upload size={14} /> },
          { id: 'privacy', label: 'Privacy', icon: <Shield size={14} />, badge: 'beta' },
          { id: 'mapping', label: 'Mapping', icon: <Workflow size={14} /> },
          { id: 'dq', label: 'Data Quality', icon: <Activity size={14} /> },
          { id: 'validation', label: 'Validation', icon: <CheckCircle2 size={14} />, badge: 'beta' },
          { id: 'lineage', label: 'Lineage', icon: <GitBranch size={14} />, badge: 'beta' },
        ]}
        active={sub}
        onChange={goto}
      />

      {/* ── UPLOAD ── */}
      {sub === 'upload' && <UploadPanel columns={columns} onUploaded={onUploaded} />}

      {/* ── PRIVACY (beta placeholder) ── */}
      {sub === 'privacy' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Privacy (beta).</strong> A PII/PHI scan will gate the dataset before
            mapping. Wiring to a backend privacy pass is pending — the rows below are an illustrative preview.
          </BetaNote>
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

      {/* ── MAPPING (live) ── */}
      {sub === 'mapping' && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[12px] text-muted-foreground">
              Each column is matched to an Augura concept with a confidence score.
            </p>
            <Button
              size="sm"
              variant="outline"
              className="text-xs"
              disabled={mapBusy}
              onClick={() => {
                setMapping(null)
                ensureMapping()
              }}
            >
              {mapBusy ? 'Mapping…' : mapping ? 'Re-run' : 'Run mapping'}
            </Button>
          </div>
          {mapError ? (
            <EmptyState icon={Workflow} title="Mapping failed" subtitle={`POST /datasets/${d.id}/map — ${mapError}`} />
          ) : mapBusy && !mapping ? (
            <Loading label="Matching columns to the taxonomy…" />
          ) : mapping ? (
            <MappingPanel result={mapping} />
          ) : (
            <EmptyState icon={Workflow} title="No mapping yet" subtitle="Run mapping to bind columns to concepts." />
          )}
        </div>
      )}

      {/* ── DATA QUALITY (live) ── */}
      {sub === 'dq' && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[12px] text-muted-foreground">
              Completeness, validity, consistency and coherence checks across the dataset.
            </p>
            <Button
              size="sm"
              variant="outline"
              className="text-xs"
              disabled={dqBusy}
              onClick={() => {
                setDqRun(null)
                setDqBundle(null)
                ensureDq()
              }}
            >
              {dqBusy ? 'Running…' : dqRun ? 'Re-run' : 'Run checks'}
            </Button>
          </div>
          {dqError ? (
            <EmptyState icon={Activity} title="Data quality failed" subtitle={`POST /datasets/${d.id}/dq — ${dqError}`} />
          ) : dqBusy && !dqRun ? (
            <Loading label="Running data-quality checks…" />
          ) : dqRun ? (
            <DqPanel run={dqRun} bundle={dqBundle} />
          ) : (
            <EmptyState icon={Activity} title="No report yet" subtitle="Run the checks to see the data-quality report." />
          )}
        </div>
      )}

      {/* ── VALIDATION (beta placeholder) ── */}
      {sub === 'validation' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Validation (beta).</strong> A release-gate summary (row count,
            missingness, types, duplicates, primary key) will live here once wired. Preview below.
          </BetaNote>
          <Card className="gap-0 rounded-xl border p-5">
            <SectionTitle icon={<CheckCircle2 size={15} className="text-primary" />} sub="Row count, missingness, types, constants, duplicates">
              Data-quality checks
            </SectionTitle>
            <div className="flex flex-col gap-2">
              {VALIDATION_ROWS.map((r) => (
                <ScanRow
                  key={r.check}
                  left={r.check}
                  kind={r.detail}
                  right={r.tone === 'warn' ? 'Warn' : 'Pass'}
                  rightTone={TONE[r.tone].text}
                  badge={r.tone}
                />
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── LINEAGE (beta placeholder) ── */}
      {sub === 'lineage' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Lineage (beta).</strong> Every transformation from source to current
            state — versioned and replayable. Backend trace pending; preview below.
          </BetaNote>
          <Card className="gap-0 rounded-xl border p-5">
            <SectionTitle icon={<GitBranch size={15} className="text-primary" />} sub="Source → transforms → uses">
              Transformation trace
            </SectionTitle>
            <div className="flex flex-col">
              {LINEAGE_STEPS.map((s) => (
                <div key={s.label} className="flex gap-3">
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
              <div className="flex gap-3">
                <div className="flex w-4 flex-shrink-0 flex-col items-center">
                  <ArrowRight size={14} className="rotate-90 text-primary" />
                </div>
                <div>
                  <div className="text-[12.5px] font-semibold text-foreground">Used by</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {LINEAGE_USES.map((u) => (
                      <Tag key={u} color="p">
                        {u}
                      </Tag>
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

// ── Add-dataset screen (green CTA target) — the upload dropzone, wired so a
// successful upload drops straight into the new dataset's detail view. ─────────
function AddDatasetView({ onBack, onUploaded }) {
  return (
    <WorkspacePage
      eyebrow="Library · Cohorts"
      title="Add dataset"
      sub="Upload a CSV or Excel file — it's parsed and profiled server-side, then registered as a new dataset."
    >
      <div className="flex flex-col gap-4">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-[12.5px] font-medium text-primary transition-colors hover:text-primary/80"
        >
          <ArrowLeft size={14} /> Back to datasets
        </button>
        <UploadPanel columns={null} onUploaded={onUploaded} />
      </div>
    </WorkspacePage>
  )
}

export function DatasetsPage() {
  const [reloadToken, setReloadToken] = useState(0)
  const { data: datasets, loading } = useCollection('datasets', reloadToken)
  const { openStudy } = useStudyNav()
  const [selectedDataset, setSelectedDataset] = useState(null)
  const [adding, setAdding] = useState(false)
  const refresh = () => setReloadToken((t) => t + 1)

  // Upload creates a NEW dataset (backend has no upload-into-existing route) —
  // refresh the list, close the add screen, and switch into the new dataset.
  function handleUploaded(result) {
    const ds = result?.dataset
    if (!ds) return
    refresh()
    setAdding(false)
    setSelectedDataset({
      id: ds.id,
      name: ds.name,
      study: '',
      rows: ds.row_count != null ? Number(ds.row_count).toLocaleString() : '—',
      cols: ds.column_count ?? (result.columns?.length ?? '—'),
      state: ds.status ?? 'draft',
      when: 'Just now',
    })
  }

  const addButton = (
    <Button size="sm" onClick={() => setAdding(true)} className="text-xs font-medium">
      <Plus className="h-3.5 w-3.5" /> Add dataset
    </Button>
  )

  if (adding) {
    return <AddDatasetView onBack={() => setAdding(false)} onUploaded={handleUploaded} />
  }

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
          onUploaded={handleUploaded}
        />
      </WorkspacePage>
    )
  }

  return (
    <WorkspacePage
      eyebrow="Library · Cohorts"
      title="Data"
      sub={loading ? 'Loading…' : `${datasets.length} dataset${datasets.length === 1 ? '' : 's'} across your studies`}
      action={
        <div className="flex items-center gap-2">
          <CohortImport />
          {addButton}
        </div>
      }
    >
      {loading ? (
        <Loading />
      ) : datasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets yet"
          subtitle="Datasets registered against your studies will appear here. Upload a file to get started."
          cta={addButton}
        />
      ) : (
        <Card className="gap-0 px-[18px] py-1">
          {datasets.map((d, i) => (
            <div
              key={d.id}
              onClick={() => setSelectedDataset(d)}
              className={`flex cursor-pointer items-center gap-3.5 py-[15px] transition-colors hover:bg-muted/30 ${i === datasets.length - 1 ? '' : 'border-b border-border'}`}
            >
              <span className="flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[9px] border border-border bg-secondary text-muted-foreground">
                <Database size={17} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-mono text-sm text-foreground">{d.name}</div>
                <div className="mt-0.5 text-[12px] text-muted-foreground/70">
                  {d.study || '—'} · updated {d.when}
                </div>
              </div>
              <div className="w-32 flex-shrink-0 text-right font-mono text-[12.5px] text-muted-foreground">
                {d.rows} rows · {d.cols} cols
              </div>
              <div className="flex w-24 flex-shrink-0 justify-end">
                <StatusBadge d={d} />
              </div>
              <ArrowRight size={15} className="flex-shrink-0 text-muted-foreground/30" />
            </div>
          ))}
        </Card>
      )}
    </WorkspacePage>
  )
}
