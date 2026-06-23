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
  X,
  FileSpreadsheet,
  BookText,
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
import {
  uploadDataset,
  addFiles,
  removeFile,
  listFiles,
  mapDataset,
  runDq,
  getDq,
  listColumns,
  parseDataDictionary,
} from '@/intake/intakeApi'

// Data workspace — port of Nico's /datasets view, rewired onto Quentin's
// backend. The intake flow (upload → mapping → data quality) lives HERE, per
// dataset, in sub-tabs — no more separate "Intake" tab.
// Upload/Mapping/Data Quality hit the real routes (/datasets/upload,
// /{id}/map, /{id}/dq). Privacy/Validation/Lineage are "beta" placeholders
// (no backend yet), faithful to Nico's mockup.

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
  return null
}

const BetaNote = ({ children }) => (
  <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-[12px] leading-[1.55] text-muted-foreground">
    {children}
  </div>
)

// ── Upload tab (real: POST /datasets/upload → new dataset) ─────────────────────
function FilesPanel({ dataset, columns, onChanged }) {
  const [files, setFiles] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [warnings, setWarnings] = useState([])
  const fileRef = useRef(null)

  async function refresh() {
    setFiles(await listFiles(dataset.id).catch(() => []))
  }
  useEffect(() => {
    let alive = true
    ;(async () => {
      const fs = await listFiles(dataset.id).catch(() => [])
      if (alive) setFiles(fs)
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset.id])

  async function handleAdd(fileList) {
    const picked = Array.from(fileList || [])
    if (!picked.length) return
    setBusy(true)
    setError(null)
    try {
      const res = await addFiles(dataset.id, picked)
      setWarnings(res?.warnings || [])
      await refresh()
      onChanged?.()
    } catch (e) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleRemove(fileId) {
    setBusy(true)
    setError(null)
    try {
      const res = await removeFile(dataset.id, fileId)
      setWarnings(res?.warnings || [])
      await refresh()
      onChanged?.()
    } catch (e) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="gap-0 rounded-xl border p-5">
        <SectionTitle
          icon={<Upload size={15} className="text-primary" />}
          sub="CSV or Excel files with the same columns — appended into one dataset, profiled server-side."
        >
          Files
        </SectionTitle>

        {warnings.length > 0 && (
          <div className="mb-3 flex flex-col gap-1 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-[12px] text-primary">
            {warnings.map((w, i) => (
              <span key={i}>{w}</span>
            ))}
          </div>
        )}

        <div className="flex flex-col gap-2.5">
          {files === null ? (
            <span className="text-[12px] italic text-muted-foreground">Loading files…</span>
          ) : files.length === 0 ? (
            <span className="text-[12px] text-muted-foreground">No files yet — add one below.</span>
          ) : (
            files.map((f) => (
              <div
                key={f.id}
                className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3.5"
              >
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                  <FileSpreadsheet size={17} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-[13px] text-foreground">{f.filename}</div>
                  <div className="mt-0.5 text-[11.5px] text-muted-foreground">
                    {f.row_count != null ? `${Number(f.row_count).toLocaleString()} rows` : '—'} ·{' '}
                    {f.column_count ?? 0} cols
                  </div>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRemove(f.id)}
                  aria-label={`Remove ${f.filename}`}
                  className="flex-shrink-0 text-muted-foreground transition-colors hover:text-destructive disabled:opacity-40"
                >
                  <X size={16} />
                </button>
              </div>
            ))
          )}

          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            multiple
            className="hidden"
            onChange={(e) => handleAdd(e.target.files)}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            onDrop={(e) => {
              e.preventDefault()
              handleAdd(e.dataTransfer.files)
            }}
            onDragOver={(e) => e.preventDefault()}
            className="flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-secondary/40 px-4 py-4 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary/80 disabled:opacity-50"
          >
            <Plus size={15} />
            {busy ? 'Working…' : 'Add files'}
          </button>
          {error && <span className="text-[11px] text-destructive">{error}</span>}
        </div>
      </Card>

      <DataDictionaryPanel datasetId={dataset.id} />

      {columns && columns.length > 0 && <ColumnsByTable columns={columns} />}
    </div>
  )
}

// ── Profiled columns of ONE table (GET /datasets/{id}/columns, filtered by sheet) ─
function ColumnRows({ columns }) {
  return (
    <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Column</th>
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

// Distinct sheet/table names, in first-seen order.
function tablesOf(columns) {
  const sheets = []
  for (const c of columns) {
    const s = c.sheet || 'data'
    if (!sheets.includes(s)) sheets.push(s)
  }
  return sheets
}

// ── Columns preview as per-table tabs (the data model) ────────────────────────
function ColumnsByTable({ columns }) {
  const sheets = tablesOf(columns)
  const [active, setActive] = useState(sheets[0])
  const current = sheets.includes(active) ? active : sheets[0]
  const shown = columns.filter((c) => (c.sheet || 'data') === current)
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {sheets.map((s) => {
            const on = s === current
            const n = columns.filter((c) => (c.sheet || 'data') === s).length
            return (
              <button
                key={s}
                type="button"
                onClick={() => setActive(s)}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] transition-colors ${
                  on
                    ? 'border-primary/40 bg-secondary text-primary'
                    : 'border-border bg-card text-muted-foreground hover:bg-muted/40'
                }`}
              >
                <FileSpreadsheet size={13} />
                <span className="font-mono">{s}</span>
                <span className="text-[10.5px] text-muted-foreground">{n}</span>
              </button>
            )
          })}
        </div>
        <span className="text-[11px] text-muted-foreground">
          {sheets.length} table{sheets.length === 1 ? '' : 's'} in the data model
        </span>
      </div>
      <ColumnRows columns={shown} />
    </div>
  )
}

// ── Data dictionary (POST /datasets/{id}/data-dictionary) ─────────────────────
function DataDictionaryPanel({ datasetId }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const ref = useRef(null)

  async function handle(fileList) {
    const file = Array.from(fileList || [])[0]
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      setResult(await parseDataDictionary(datasetId, file))
    } catch (e) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
      if (ref.current) ref.current.value = ''
    }
  }

  return (
    <Card className="gap-0 rounded-xl border p-5">
      <SectionTitle
        icon={<BookText size={15} className="text-primary" />}
        sub="Upload a data dictionary (CSV/XLSX/TXT/MD). Dictionary-shaped tables are parsed directly; free-form ones are structured by the LLM."
      >
        Data dictionary{' '}
        <span className="rounded-full bg-muted px-1.5 py-px text-[10px] font-semibold text-muted-foreground">
          beta
        </span>
      </SectionTitle>

      <input
        ref={ref}
        type="file"
        accept=".csv,.xlsx,.xls,.txt,.md"
        className="hidden"
        onChange={(e) => handle(e.target.files)}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => ref.current?.click()}
        className="flex items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-secondary/40 px-4 py-3 text-[12.5px] text-muted-foreground transition-colors hover:bg-secondary/80 disabled:opacity-50"
      >
        <Plus size={15} />
        {busy ? 'Parsing…' : 'Upload data dictionary'}
      </button>
      {error && <span className="mt-2 text-[11px] text-destructive">{error}</span>}

      {result && (
        <div className="mt-3 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <Badge variant="outline" className="text-muted-foreground">
              {result.source_kind === 'structured' ? 'Structured' : 'AI-parsed'}
            </Badge>
            <span>
              {result.entries.length} variable{result.entries.length === 1 ? '' : 's'}
            </span>
          </div>
          {(result.warnings || []).map((w, i) => (
            <span key={i} className="text-[11px] text-muted-foreground">
              {w}
            </span>
          ))}
          {result.entries.length > 0 && (
            <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
                    <th className="px-4 py-2.5 font-medium">Variable</th>
                    <th className="px-4 py-2.5 font-medium">Label</th>
                    <th className="px-4 py-2.5 font-medium">Type</th>
                    <th className="px-4 py-2.5 font-medium">Description</th>
                    <th className="px-4 py-2.5 font-medium">Allowed values</th>
                  </tr>
                </thead>
                <tbody>
                  {result.entries.map((e, i) => (
                    <tr key={e.name + i} className="border-b border-border/60 align-top last:border-0">
                      <td className="px-4 py-2 font-mono text-foreground">{e.name}</td>
                      <td className="px-4 py-2 text-foreground">{e.label ?? '—'}</td>
                      <td className="px-4 py-2 text-muted-foreground">{e.value_type ?? '—'}</td>
                      <td className="px-4 py-2 text-muted-foreground">{e.description ?? '—'}</td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {e.allowed_values?.length ? e.allowed_values.join(', ') : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}
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

function MappingTable({ rows }) {
  return (
    <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Source column</th>
            <th className="px-4 py-2.5 font-medium">Proposed concept</th>
            <th className="px-4 py-2.5 font-medium text-center">Layer</th>
            <th className="px-4 py-2.5 font-medium">Domain</th>
            <th className="px-4 py-2.5 font-medium text-right">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.column} className="border-b border-border/60 last:border-0">
              <td className="px-4 py-2 font-mono text-foreground">{c.column}</td>
              <td className="px-4 py-2 font-mono text-[11.5px] text-muted-foreground">
                {c.proposed_canonical_id ?? <em className="text-muted-foreground/50">Unmapped</em>}
              </td>
              <td className="px-4 py-2 text-center">
                {c.layer != null ? (
                  <Badge variant="outline" className="font-mono text-[10px]">
                    L{c.layer}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground/40">—</span>
                )}
              </td>
              <td className="px-4 py-2">
                {c.domain ? (
                  <Badge variant="secondary" className="text-[10px] font-normal">
                    {c.domain}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground/40">—</span>
                )}
              </td>
              <td className="px-4 py-2 text-right">
                <ConfBadge score={c.confidence} label={c.confidence_label} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

// Mapping shown per table (sheet), not as one flat attribute list.
function MappingPanel({ result }) {
  const columns = result.columns || []
  const total = result.total_count ?? 0
  const mapped = result.mapped_count ?? 0
  const tally = (label) => columns.filter((c) => c.confidence_label === label).length
  const cards = [
    ['Mapping rate', total ? `${Math.round((mapped / total) * 100)}%` : '—'],
    ['High conf.', tally('High')],
    ['Medium conf.', tally('Medium')],
    ['Low conf.', tally('Low')],
    ['Unmapped', total - mapped],
  ]
  const sheets = tablesOf(columns)
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
        {cards.map(([label, value]) => (
          <Card key={label} className="gap-0 rounded-xl border p-3 text-center">
            <div className="font-mono text-[20px] font-bold text-foreground">{value}</div>
            <div className="text-[10px] text-muted-foreground">{label}</div>
          </Card>
        ))}
      </div>

      {sheets.map((s) => {
        const rows = columns.filter((c) => (c.sheet || 'data') === s)
        return (
          <div key={s} className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
              <FileSpreadsheet size={13} />
              <span className="font-mono text-foreground">{s}</span>
              <span className="text-[10.5px]">
                · {rows.length} column{rows.length === 1 ? '' : 's'}
              </span>
            </div>
            <MappingTable rows={rows} />
          </div>
        )
      })}
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
function DatasetDetail({ d, onBack, onOpenStudy }) {
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
          { id: 'upload', label: 'Files', icon: <Upload size={14} /> },
          { id: 'privacy', label: 'Privacy', icon: <Shield size={14} />, badge: 'beta' },
          { id: 'mapping', label: 'Mapping', icon: <Workflow size={14} /> },
          { id: 'dq', label: 'Data Quality', icon: <Activity size={14} />, badge: 'beta' },
          { id: 'validation', label: 'Validation', icon: <CheckCircle2 size={14} />, badge: 'beta' },
          { id: 'lineage', label: 'Lineage', icon: <GitBranch size={14} />, badge: 'beta' },
        ]}
        active={sub}
        onChange={goto}
      />

      {/* ── FILES ── */}
      {sub === 'upload' && (
        <FilesPanel
          dataset={d}
          columns={columns}
          onChanged={async () => {
            setColumns(await listColumns(d.id).catch(() => []))
            setMeta(await apiJson(`/datasets/${d.id}`).catch(() => null))
          }}
        />
      )}

      {/* ── PRIVACY (beta — backend pass pending) ── */}
      {sub === 'privacy' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Privacy (beta).</strong> A PII/PHI scan will gate the dataset before
            mapping. This view activates once the backend privacy pass is wired — no preview data is shown.
          </BetaNote>
          <EmptyState icon={Shield} title="Privacy scan coming soon" subtitle="Backend privacy pass not yet wired." />
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

      {/* ── VALIDATION (beta — backend gate pending) ── */}
      {sub === 'validation' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Validation (beta).</strong> A release-gate summary (row count,
            missingness, types, duplicates, primary key) will live here once wired — no preview data is shown.
          </BetaNote>
          <EmptyState icon={CheckCircle2} title="Release-gate summary coming soon" subtitle="Backend validation pass not yet wired." />
        </div>
      )}

      {/* ── LINEAGE (beta — backend trace pending) ── */}
      {sub === 'lineage' && (
        <div className="flex flex-col gap-4">
          <BetaNote>
            <strong className="text-foreground">Lineage (beta).</strong> Every transformation from source to current
            state — versioned and replayable — will appear here once the backend trace is wired.
          </BetaNote>
          <EmptyState icon={GitBranch} title="Transformation trace coming soon" subtitle="Backend lineage trace not yet wired." />
        </div>
      )}
    </div>
  )
}

// ── Add-dataset modal (green CTA target) — registers a dataset like Nico's
// legacy form (name + study), but with the file: one POST /datasets/upload
// creates + profiles it. One file → land in its detail view. Multiple files →
// one dataset per file (name = file name), then stay on the list. ──
const MODAL_INPUT_CLS =
  'w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-foreground ' +
  'placeholder:text-muted-foreground/60 outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15'

function AddDatasetModal({ studies, onClose, onUploaded }) {
  const [name, setName] = useState('')
  const [studyId, setStudyId] = useState('')
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const fileRef = useRef(null)

  function pickFiles(fileList) {
    const picked = Array.from(fileList || [])
    if (!picked.length) return
    setFiles(picked)
    setError(null)
    // Pre-fill the name from the first file if the user hasn't typed one.
    if (!name.trim()) {
      setName(picked[0].name.replace(/\.(csv|xlsx|xls)$/i, ''))
    }
  }

  function removeFile(idx) {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  // One or more files → ONE dataset (same columns, appended). Land in its detail.
  async function submit() {
    if (!files.length || busy) return
    setBusy(true)
    setError(null)
    try {
      const result = await uploadDataset(files, {
        name: name.trim() || undefined,
        studyId: studyId || undefined,
      })
      onUploaded(result)
    } catch (e) {
      setError(String(e?.message || e))
      setBusy(false)
    }
  }

  const ctaLabel = busy ? 'Uploading…' : 'Add dataset'

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[rgba(15,14,12,0.34)] p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <Card className="w-full max-w-[460px] gap-0 overflow-hidden p-0" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-border p-5">
          <div>
            <h2 className="text-[16px] font-semibold text-foreground">Add dataset</h2>
            <p className="mt-1 text-[13px] text-muted-foreground">
              Register a cohort dataset — select one or more CSV/Excel files with the same
              columns to combine them into one dataset.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4 p-5">
          <label className="block">
            <div className="mb-1.5 text-[12.5px] font-medium text-foreground">Dataset name</div>
            <input
              className={MODAL_INPUT_CLS}
              placeholder="e.g. cohort_2026"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block">
            <div className="mb-1.5 text-[12.5px] font-medium text-foreground">Study</div>
            <select className={MODAL_INPUT_CLS} value={studyId} onChange={(e) => setStudyId(e.target.value)}>
              <option value="">— No study —</option>
              {(studies || []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <div className="block">
            <div className="mb-1.5 text-[12.5px] font-medium text-foreground">
              File{files.length > 1 ? 's' : ''} <span className="text-[#C0392B]">*</span>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              multiple
              className="hidden"
              onChange={(e) => pickFiles(e.target.files)}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex w-full items-center gap-2 rounded-lg border border-dashed border-border bg-secondary/40 px-3 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:bg-secondary/80"
            >
              <Upload size={15} className="flex-shrink-0" />
              {files.length === 0
                ? 'Choose CSV or Excel files'
                : `${files.length} file${files.length === 1 ? '' : 's'} selected`}
            </button>
            <p className="mt-1.5 text-[11px] text-muted-foreground">.csv · .xlsx · .xls — same columns, appended</p>
            {files.length > 0 && (
              <ul className="mt-2 flex max-h-40 flex-col gap-1 overflow-y-auto">
                {files.map((f, i) => (
                  <li
                    key={f.name + i}
                    className="flex items-center gap-2 rounded-md border border-border bg-secondary/30 px-2.5 py-1.5"
                  >
                    <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-foreground">{f.name}</span>
                    {!busy && (
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        aria-label={`Remove ${f.name}`}
                        className="flex-shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                      >
                        <X size={13} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {error && <div className="text-[12px] text-destructive">{error}</div>}
        </div>

        <div className="flex justify-end gap-2 border-t border-border p-5">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button disabled={!files.length || busy} onClick={submit}>
            {ctaLabel}
          </Button>
        </div>
      </Card>
    </div>
  )
}

export function DatasetsPage() {
  const [reloadToken, setReloadToken] = useState(0)
  const { data: datasets, loading } = useCollection('datasets', reloadToken)
  const { data: studies } = useCollection('studies')
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
              <div className="w-40 flex-shrink-0 text-right font-mono text-[12.5px] text-muted-foreground">
                {d.files > 1 ? `${d.files} files · ` : ''}
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
      {adding && (
        <AddDatasetModal
          studies={studies}
          onClose={() => setAdding(false)}
          onUploaded={handleUploaded}
        />
      )}
    </WorkspacePage>
  )
}
