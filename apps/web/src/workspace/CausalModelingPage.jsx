import { useState, useEffect, useMemo } from 'react'
import { Network, Sparkles, TriangleAlert, CheckCircle2 } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { SubTabs } from '@/cockpit/SubTabs'
import { apiJson } from '@/api'
import { parsePICOT, findConceptInTaxonomy } from '@/semantic/picot-parser'
import { enrichApply } from '@/workspace/dataClient'
import { EnrichmentPanel } from '@/workspace/EnrichmentPanel'
import { resetSemanticStore, initSemanticStore } from '@/lib/semantic-store'

// Causal modeling (port of Nico's /causal view, rewired onto the backend).
// Flow: mapped dataset → POST /datasets/{id}/map (concepts) → POST /causal/dag.
// The SVG rendering is read-only for this first iteration (the drag/reclassify
// editor from IntakeDAG.jsx comes next).

// Role colors (faithful port of IntakeDAG.jsx).
const ROLE = {
  exposure: { fill: '#1F2937', stroke: '#1F2937', text: '#FFFFFF', label: 'Exposure' },
  outcome: { fill: '#0C447C', stroke: '#0C447C', text: '#FFFFFF', label: 'Outcome' },
  mediator: { fill: '#2A9D8F', stroke: '#2A9D8F', text: '#FFFFFF', label: 'Mediator' },
  confounder: { fill: '#FFF8E6', stroke: '#EF9F27', text: '#633806', label: 'Confounder' },
  effect_modifier: { fill: '#FDECEA', stroke: '#E24B4A', text: '#7A2020', label: 'Effect mod.' },
  collider: { fill: '#FDECEA', stroke: '#E24B4A', text: '#7A2020', label: 'Collider' },
  other: { fill: '#F5F4F0', stroke: '#888780', text: '#444441', label: 'Other' },
}
const NODE_W = 150
const NODE_H = 46

// Wrap a node label onto up to `maxLines` lines so the full text is shown (the previous
// renderer hard-truncated at 19 chars). A <title> still carries the complete label on hover.
function wrapLabel(label, maxChars = 22, maxLines = 2) {
  const words = String(label ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (!words.length) return ['']
  const lines = []
  let cur = ''
  for (let i = 0; i < words.length; i++) {
    const next = cur ? `${cur} ${words[i]}` : words[i]
    if (!cur || next.length <= maxChars) {
      cur = next
    } else {
      lines.push(cur)
      cur = words[i]
      if (lines.length === maxLines) {
        lines[maxLines - 1] = `${lines[maxLines - 1]}…`
        cur = ''
        break
      }
    }
  }
  if (cur) lines.push(cur)
  return lines
}

// Edges proposed by the LLM carry the id `proposed_<subj>_<obj>` (cf. builder).
const isProposed = (e) => typeof e.id === 'string' && e.id.startsWith('proposed_')

function edgeColor(e) {
  if (isProposed(e)) return '#EF9F27'
  if (e.dag_role_to === 'mediator') return '#2A9D8F'
  if (e.supported_by_data) return '#047857'
  return '#9CA3AF'
}

function DagSvg({ nodes, edges }) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]))
  const xs = nodes.map((n) => n.x)
  const ys = nodes.map((n) => n.y)
  const minX = Math.min(...xs) - 20
  const minY = Math.min(...ys) - 20
  const w = Math.max(...xs) - minX + NODE_W + 40
  const h = Math.max(...ys) - minY + NODE_H + 40
  const cx = (n) => n.x - minX + NODE_W / 2
  const cy = (n) => n.y - minY + NODE_H / 2
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-[#FAFAF8]">
      <svg viewBox={`0 0 ${w} ${h}`} className="block h-auto w-full" style={{ minWidth: 560 }}>
        <defs>
          {[
            ['arr-main', '#047857'],
            ['arr-med', '#2A9D8F'],
            ['arr-conf', '#9CA3AF'],
            ['arr-prop', '#EF9F27'],
          ].map(([id, fill]) => (
            <marker key={id} id={id} markerWidth="9" markerHeight="9" refX="8" refY="3.5" orient="auto">
              <path d="M0,0 L8,3.5 L0,7 Z" fill={fill} />
            </marker>
          ))}
        </defs>
        {edges.map((e) => {
          const a = byId[e.from]
          const b = byId[e.to]
          if (!a || !b) return null
          const col = edgeColor(e)
          const marker =
            col === '#EF9F27'
              ? 'arr-prop'
              : col === '#2A9D8F'
                ? 'arr-med'
                : col === '#047857'
                  ? 'arr-main'
                  : 'arr-conf'
          return (
            <line
              key={e.id}
              x1={cx(a)}
              y1={cy(a)}
              x2={cx(b)}
              y2={cy(b)}
              stroke={col}
              strokeWidth={1.6}
              strokeDasharray={isProposed(e) ? '4,3' : undefined}
              markerEnd={`url(#${marker})`}
            />
          )
        })}
        {nodes.map((n) => {
          const s = ROLE[n.role] || ROLE.other
          const rx = n.x - minX
          const ry = n.y - minY
          const lines = wrapLabel(n.label)
          const labelCx = rx + NODE_W / 2
          const labelTop = ry + NODE_H / 2 + 4 - (lines.length - 1) * 6.5
          return (
            <g key={n.id}>
              <title>{n.label}</title>
              {n.adjusted && (
                <rect
                  x={rx - 4}
                  y={ry - 4}
                  width={NODE_W + 8}
                  height={NODE_H + 8}
                  rx={10}
                  fill="none"
                  stroke="#EF9F27"
                  strokeWidth={2}
                  strokeDasharray="5,2"
                  opacity={0.85}
                />
              )}
              <rect
                x={rx}
                y={ry}
                width={NODE_W}
                height={NODE_H}
                rx={6}
                fill={s.fill}
                stroke={s.stroke}
                strokeWidth={1}
                strokeDasharray={n.observed ? undefined : '5,3'}
              />
              <text
                textAnchor="middle"
                fontSize="10.5"
                fontWeight="600"
                fill={s.text}
                style={{ pointerEvents: 'none' }}
              >
                {lines.map((ln, li) => (
                  <tspan key={li} x={labelCx} y={labelTop + li * 12.5}>
                    {ln}
                  </tspan>
                ))}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
      {Object.values(ROLE).map((r) => (
        <span key={r.label} className="flex items-center gap-1.5">
          <span
            className="inline-block h-3 w-3 rounded-[3px] border"
            style={{ background: r.fill, borderColor: r.stroke }}
          />
          {r.label}
        </span>
      ))}
    </div>
  )
}

function QualityBadge({ q }) {
  const tone =
    q.label === 'High' ? 'text-emerald-700' : q.label === 'Medium' ? 'text-amber-700' : 'text-red-700'
  return (
    <Badge variant="outline" className={tone}>
      Quality: {q.label} ({(q.score * 100).toFixed(0)}%)
    </Badge>
  )
}

// ─── Accepting proposed edges ───────────────────────────────────────────────

/** Maps the backend error to a readable message. */
function mapAcceptError(err) {
  const msg = String(err?.message || err || '')
  if (msg.includes('403') || err?.status === 403) return 'Owners only.'
  if (msg.includes('unknown_concept_ids') || msg.includes('400'))
    return 'Concepts not yet created (proposed) — enrich them first.'
  return msg || 'An unexpected error occurred.'
}

/**
 * Section listing the edges proposed by the LLM, each with an "Accept"
 * button that calls enrichApply then reloads the DAG.
 */
function ProposedEdges({ edges, nodes, onAccepted }) {
  // Per-edge state: null | 'accepting' | 'done' | string (error)
  const [states, setStates] = useState({})

  const proposed = edges.filter(isProposed)
  if (proposed.length === 0) return null

  // Index of node labels for display.
  const labelById = Object.fromEntries(nodes.map((n) => [n.id, n.label]))

  async function accept(e) {
    setStates((s) => ({ ...s, [e.id]: 'accepting' }))
    try {
      await enrichApply({
        direct_relations: [
          {
            subject_concept_id: e.from,
            object_concept_id: e.to,
            predicate: e.predicate || 'causally_influences',
            polarity: e.polarity || 'neutral',
            default_strength: e.strength || 'moderate',
            mechanism_summary: e.notes || '',
            relation_id: e.id,
          },
        ],
      })
      setStates((s) => ({ ...s, [e.id]: 'done' }))
      // Reload the semantic store then regenerate the DAG.
      resetSemanticStore()
      await initSemanticStore()
      onAccepted()
    } catch (err) {
      setStates((s) => ({ ...s, [e.id]: mapAcceptError(err) }))
    }
  }

  return (
    <Card className="border-amber-300/60 p-4">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-amber-700">
        Proposed relations ({proposed.length})
      </div>
      <ul className="flex flex-col gap-2">
        {proposed.map((e) => {
          const state = states[e.id] ?? null
          const isDone = state === 'done'
          const isAccepting = state === 'accepting'
          const isError = state !== null && !isDone && !isAccepting

          return (
            <li key={e.id} className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <span className="font-medium text-foreground">
                {labelById[e.from] ?? e.from}
              </span>
              <span className="text-muted-foreground">→</span>
              <span className="font-medium text-foreground">
                {labelById[e.to] ?? e.to}
              </span>
              {e.predicate && (
                <Badge variant="outline" className="text-[10.5px] text-muted-foreground">
                  {e.predicate}
                </Badge>
              )}
              <span className="ml-auto flex items-center gap-2">
                {isDone ? (
                  <span className="flex items-center gap-1 text-emerald-700">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Accepted
                  </span>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 px-2 text-[11.5px] text-amber-700 border-amber-300 hover:bg-amber-50"
                    disabled={isAccepting}
                    onClick={() => accept(e)}
                  >
                    {isAccepting ? 'Saving…' : 'Accept'}
                  </Button>
                )}
              </span>
              {isError && (
                <span className="w-full text-[11.5px] text-red-700">{state}</span>
              )}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

// Step 3.4 — feedback to the semantic layer for relations the LLM excluded from the DAG.
const QUALIFIER_TYPES = [
  'population',
  'comorbidity',
  'age_range',
  'sex',
  'therapeutic_context',
  'biomarker_threshold',
  'temporal_context',
]
const QUALIFIER_EFFECTS = [
  'restricts_applicability',
  'attenuates_strength',
  'amplifies_strength',
  'reverses_polarity',
]

function ExcludedRelations({ excluded, onAccepted }) {
  const [states, setStates] = useState({}) // relation_id → null | 'working' | 'done' | errorString
  const [qualifying, setQualifying] = useState(null) // relation_id whose qualifier form is open
  const [qform, setQform] = useState({
    qualifier_type: QUALIFIER_TYPES[0],
    qualifier_effect: QUALIFIER_EFFECTS[0],
    qualifier_value: '',
  })

  if (!excluded || excluded.length === 0) return null

  async function doApply(relId, body) {
    setStates((s) => ({ ...s, [relId]: 'working' }))
    try {
      await enrichApply(body)
      resetSemanticStore()
      await initSemanticStore()
      setStates((s) => ({ ...s, [relId]: 'done' }))
      setQualifying(null)
      onAccepted?.()
    } catch (err) {
      setStates((s) => ({ ...s, [relId]: mapAcceptError(err) }))
    }
  }

  return (
    <Card className="p-4">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
        Excluded relations — review for the ontology ({excluded.length})
      </div>
      <ul className="flex flex-col gap-2.5">
        {excluded.map((ex) => {
          const st = states[ex.relation_id] ?? null
          const isDone = st === 'done'
          const isWorking = st === 'working'
          const isErr = st !== null && !isDone && !isWorking
          return (
            <li
              key={ex.relation_id}
              className="flex flex-col gap-1.5 border-b border-border/50 pb-2.5 last:border-0"
            >
              <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
                <span className="font-medium text-foreground">
                  {ex.subject_label || ex.subject_id}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {ex.predicate || '→'}
                </span>
                <span className="font-medium text-foreground">
                  {ex.object_label || ex.object_id}
                </span>
                <Badge variant="outline" className="ml-1 text-[10px] text-muted-foreground">
                  rec: {ex.recommendation}
                </Badge>
              </div>
              {ex.exclusion_reason && (
                <p className="text-[11.5px] text-muted-foreground">{ex.exclusion_reason}</p>
              )}
              {isDone ? (
                <span className="flex items-center gap-1 text-[12px] text-emerald-700">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Applied
                </span>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 border-red-300 px-2 text-[11.5px] text-red-700 hover:bg-red-50"
                    disabled={isWorking}
                    onClick={() =>
                      doApply(ex.relation_id, {
                        deactivate_relation: { relation_id: ex.relation_id },
                      })
                    }
                  >
                    {isWorking ? 'Working…' : 'Remove from ontology'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 px-2 text-[11.5px]"
                    disabled={isWorking}
                    onClick={() =>
                      setQualifying(qualifying === ex.relation_id ? null : ex.relation_id)
                    }
                  >
                    Add qualifier
                  </Button>
                </div>
              )}
              {qualifying === ex.relation_id && !isDone && (
                <div className="mt-1 flex flex-wrap items-end gap-2 rounded-md border border-border bg-muted/30 p-2">
                  <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                    Type
                    <select
                      value={qform.qualifier_type}
                      onChange={(e) => setQform((f) => ({ ...f, qualifier_type: e.target.value }))}
                      className="rounded border border-border bg-background px-1.5 py-1 text-[11.5px] text-foreground"
                    >
                      {QUALIFIER_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                    Effect
                    <select
                      value={qform.qualifier_effect}
                      onChange={(e) =>
                        setQform((f) => ({ ...f, qualifier_effect: e.target.value }))
                      }
                      className="rounded border border-border bg-background px-1.5 py-1 text-[11.5px] text-foreground"
                    >
                      {QUALIFIER_EFFECTS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-1 flex-col gap-0.5 text-[10px] text-muted-foreground">
                    Value
                    <input
                      value={qform.qualifier_value}
                      onChange={(e) => setQform((f) => ({ ...f, qualifier_value: e.target.value }))}
                      placeholder="e.g. type 2 diabetes"
                      className="rounded border border-border bg-background px-1.5 py-1 text-[11.5px] text-foreground"
                    />
                  </label>
                  <Button
                    size="sm"
                    className="h-7 px-2 text-[11.5px]"
                    disabled={isWorking || !qform.qualifier_value.trim()}
                    onClick={() =>
                      doApply(ex.relation_id, {
                        add_qualifier: {
                          relation_id: ex.relation_id,
                          qualifier_type: qform.qualifier_type,
                          qualifier_value: qform.qualifier_value.trim(),
                          qualifier_effect: qform.qualifier_effect,
                        },
                      })
                    }
                  >
                    {isWorking ? 'Saving…' : 'Apply qualifier'}
                  </Button>
                </div>
              )}
              {isErr && <span className="text-[11.5px] text-red-700">{st}</span>}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

function Result({ dag, onAccepted }) {
  const measured = dag.nodes.filter((n) => n.observed).length
  const structuralRoles = dag.llm_context?.structural_roles || {}
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <QualityBadge q={dag.quality} />
        <Badge variant="secondary">{dag.nodes.length} nodes</Badge>
        <Badge variant="secondary">{dag.edges.length} edges</Badge>
        <Badge variant="outline" className="text-muted-foreground">
          {measured} measured · {dag.nodes.length - measured} unmeasured
        </Badge>
        {dag.graph.adjusted_ids.length > 0 && (
          <Badge variant="outline" className="text-amber-700">
            Adjustment set: {dag.graph.adjusted_ids.length}
          </Badge>
        )}
      </div>

      {dag.nodes.length === 0 ? (
        <EmptyState
          icon={Network}
          title="The model came back empty"
          subtitle="No reviewed ontology relations connected the mapped concepts. Check the dataset mapping or seed the ontology."
        />
      ) : (
        <>
          <DagSvg nodes={dag.nodes} edges={dag.edges} />
          <Legend />
        </>
      )}

      {Object.keys(structuralRoles).length > 0 && (
        <Card className="p-4">
          <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
            Structural roles (deterministic, pre-LLM)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(structuralRoles).map(([cid, role]) => (
              <Badge key={cid} variant="outline" className="text-[10.5px]">
                <span className="font-mono">{cid}</span>
                <span className="ml-1 text-muted-foreground">· {role}</span>
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {dag.llm_context?.reasoning && (
        <Card className="p-4">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
            LLM reasoning
          </div>
          <p className="text-[12.5px] text-foreground">{dag.llm_context.reasoning}</p>
        </Card>
      )}

      {dag.missing_variables.length > 0 && (
        <Card className="p-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
            Missing variables (not in your data)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {dag.missing_variables.map((m) => (
              <Badge key={m.concept_id} variant="outline" className="text-muted-foreground">
                {m.label}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {dag.warnings.length > 0 && (
        <Card className="border-amber-300/60 p-4">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-amber-700">
            <TriangleAlert className="h-3.5 w-3.5" /> Warnings
          </div>
          <ul className="list-disc pl-5 text-[12.5px] text-muted-foreground">
            {dag.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </Card>
      )}

      {/* Proposed-edges section — only if the DAG contains any. */}
      <ProposedEdges edges={dag.edges} nodes={dag.nodes} onAccepted={onAccepted} />

      {/* Excluded relations — review for the ontology (remove / add qualifier). */}
      <ExcludedRelations excluded={dag.excluded_relations} onAccepted={onAccepted} />
    </div>
  )
}

// Maps the local parsePICOT output to the backend Picot payload (or null on failure).
function picotFromQuestion(question) {
  if (!question || !question.trim()) return null
  try {
    const p = parsePICOT(question)
    return {
      intervention: p.intervention ?? null,
      comparator: p.comparator ?? null,
      outcomes: (p.outcomes || []).map((o) => ({
        concept_id: o.concept_id ?? null,
        label: o.label ?? null,
      })),
      timeframe:
        Array.isArray(p.time_window) && p.time_window.length ? p.time_window.join(', ') : null,
      population: p.population ?? null,
      therapeutic_area: p.therapeutic_areas?.[0] ?? null,
      intervention_concept_id: null,
    }
  } catch {
    return null
  }
}

// Uniform PICOT frame from the regex parser output (parsePICOT) for side-by-side comparison.
function regexFrame(p) {
  return {
    population: p.population ?? null,
    intervention: p.intervention ?? null,
    comparator: p.comparator ?? null,
    outcomes: (p.outcomes || []).map((o) => o.label || o.concept_id).filter(Boolean),
    timeframe:
      Array.isArray(p.time_window) && p.time_window.length ? p.time_window.join(', ') : null,
    moderators: [],
    therapeutic_area: p.therapeutic_areas?.[0] ?? null,
  }
}

// ✓ when the text resolves to a taxonomy concept, "· gap" when it does not.
function Mark({ value }) {
  if (!value || (typeof value === 'string' && !value.trim())) {
    return <span className="text-muted-foreground/50">—</span>
  }
  let matched = false
  try {
    matched = !!findConceptInTaxonomy(value)
  } catch {
    matched = false
  }
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-foreground">{value}</span>
      {matched ? (
        <span className="text-emerald-600" title="matched a taxonomy concept">
          ✓
        </span>
      ) : (
        <span className="text-amber-600" title="no taxonomy match (gap)">
          · gap
        </span>
      )}
    </span>
  )
}

function FrameCell({ frame, field, kind }) {
  if (!frame) return <span className="text-muted-foreground/40">—</span>
  const v = frame[field]
  if (kind === 'list') {
    const items = (v || []).filter(Boolean)
    if (!items.length) return <span className="text-muted-foreground/50">—</span>
    return (
      <span className="flex flex-col gap-1">
        {items.map((it, i) => (
          <Mark key={i} value={it} />
        ))}
      </span>
    )
  }
  return <Mark value={v} />
}

const FRAME_ROWS = [
  ['Population', 'population', 'scalar'],
  ['Intervention / exposure', 'intervention', 'scalar'],
  ['Comparator', 'comparator', 'scalar'],
  ['Outcomes', 'outcomes', 'list'],
  ['Moderators', 'moderators', 'list'],
  ['Timeframe', 'timeframe', 'scalar'],
  ['Therapeutic area', 'therapeutic_area', 'scalar'],
]

// PICOT element values that did NOT resolve to a taxonomy concept (the gaps to enrich).
function frameGaps(frame) {
  if (!frame) return []
  const vals = []
  for (const [, field, kind] of FRAME_ROWS) {
    const v = frame[field]
    if (kind === 'list') (v || []).forEach((x) => x && vals.push(String(x)))
    else if (v && String(v).trim()) vals.push(String(v))
  }
  return vals.filter((v) => {
    try {
      return !findConceptInTaxonomy(v)
    } catch {
      return false
    }
  })
}

// Side-by-side audit of the deterministic regex parse vs the Haiku parse, with a ✓/gap marker
// on each element showing whether it resolved to a taxonomy concept (Phase 1).
function ParseCompare({ regex, haiku, haikuBusy, haikuError }) {
  if (!regex) return null
  return (
    <Card className="flex flex-col gap-1.5 p-4">
      <div className="grid grid-cols-[150px_1fr_1fr] gap-x-4 text-[11px] font-semibold uppercase tracking-[0.05em] text-muted-foreground">
        <span>Element</span>
        <span>Regex parser</span>
        <span className="flex items-center gap-2">
          Haiku
          {haikuBusy && (
            <span className="text-[10px] font-normal normal-case text-muted-foreground/70">
              improving…
            </span>
          )}
        </span>
      </div>
      {FRAME_ROWS.map(([label, field, kind]) => (
        <div
          key={field}
          className="grid grid-cols-[150px_1fr_1fr] items-start gap-x-4 border-t border-border/50 pt-1.5 text-[12.5px]"
        >
          <span className="text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            {label}
          </span>
          <FrameCell frame={regex} field={field} kind={kind} />
          {haikuError ? (
            <span className="text-[11px] text-muted-foreground/50">—</span>
          ) : (
            <FrameCell frame={haiku} field={field} kind={kind} />
          )}
        </div>
      ))}
      {haikuError && (
        <p className="mt-1 text-[11px] text-muted-foreground">
          Haiku parse unavailable: {haikuError}
        </p>
      )}
    </Card>
  )
}

export function CausalModelingPage() {
  const [sub, setSub] = useState('question')
  const [datasets, setDatasets] = useState(null)
  const [datasetId, setDatasetId] = useState('')
  const [question, setQuestion] = useState('')
  const [haiku, setHaiku] = useState(null) // { q, parsed } — keyed to the question it parsed
  const [haikuBusy, setHaikuBusy] = useState(false)
  const [haikuError, setHaikuError] = useState(null) // { q, msg }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dag, setDag] = useState(null)
  const [storeVersion, setStoreVersion] = useState(0) // bumped after enrichment reloads the store
  const [proceedWithGaps, setProceedWithGaps] = useState(false)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const d = await apiJson('/datasets')
        if (alive) setDatasets(Array.isArray(d) ? d : [])
      } catch {
        if (alive) setDatasets([])
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  // Load the semantic layer so taxonomy ✓/gap matching works.
  useEffect(() => {
    initSemanticStore().catch(() => {})
  }, [])

  // Phase 1: regex parses instantly (useMemo below); Haiku parses 700 ms after typing stops.
  useEffect(() => {
    if (question.trim().length <= 10) return
    let alive = true
    const id = setTimeout(async () => {
      setHaikuBusy(true)
      try {
        const res = await apiJson('/causal/parse-question', {
          method: 'POST',
          body: JSON.stringify({ question }),
        })
        if (alive) setHaiku({ q: question, parsed: res.parsed })
      } catch (e) {
        if (alive) setHaikuError({ q: question, msg: String(e?.message || e) })
      } finally {
        if (alive) setHaikuBusy(false)
      }
    }, 700)
    return () => {
      alive = false
      clearTimeout(id)
    }
  }, [question])

  // Instant deterministic parse — pure derivation; re-runs when the question OR the (reloaded)
  // semantic store changes, so ✓/gap markers refresh after enrichment.
  const regexParse = useMemo(() => {
    if (question.trim().length <= 10) return null
    try {
      return regexFrame(parsePICOT(question))
    } catch {
      return null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question, storeVersion])
  // Haiku result/error keyed to the question they were computed for (no stale flashes).
  const haikuParse = haiku && haiku.q === question ? haiku.parsed : null
  const haikuErr = haikuError && haikuError.q === question ? haikuError.msg : null
  const showHaikuBusy = haikuBusy && !haikuParse && !haikuErr && question.trim().length > 10
  // Gaps drive the enrichment gate: the Haiku frame if present, else the regex frame.
  const activeFrame = haikuParse ?? regexParse
  // eslint-disable-next-line react-hooks/exhaustive-deps -- frameGaps reads the in-memory store
  const gaps = useMemo(() => frameGaps(activeFrame), [activeFrame, storeVersion])

  async function generate() {
    if (!question.trim()) {
      setSub('question')
      return
    }
    setBusy(true)
    setError('')
    setDag(null)
    setSub('dag')
    try {
      // A dataset is optional: when one is linked we map it and feed its mapped concepts
      // into the DAG; otherwise the model is generated from the clinical question alone.
      let mapped_concepts = []
      if (datasetId) {
        const map = await apiJson(`/datasets/${datasetId}/map`, { method: 'POST' })
        mapped_concepts = (map.columns || [])
          .filter((c) => c.proposed_canonical_id)
          .map((c) => ({
            concept_id: c.proposed_canonical_id,
            concept_label: c.column,
            confidence: c.confidence,
          }))
      }
      const parsed = picotFromQuestion(question)
      const result = await apiJson('/causal/dag', {
        method: 'POST',
        body: JSON.stringify({
          mapped_concepts,
          picot: parsed,
          clinical_question: question || null,
        }),
      })
      setDag(result)
    } catch (e) {
      setError(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <WorkspacePage
      eyebrow="Modeling"
      title="Causal modeling"
      sub="Frame a clinical question, then generate an ontology-grounded causal DAG. Reviewed ontology relations are the ground truth; the LLM only contextualizes them to your question."
    >
      <SubTabs
        className="mb-4"
        tabs={[
          { id: 'question', label: 'Causal question', icon: <Sparkles size={14} /> },
          { id: 'dag', label: 'DAG', icon: <Network size={14} /> },
        ]}
        active={sub}
        onChange={setSub}
      />

      {sub === 'question' && (
        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
              Clinical question
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={3}
                placeholder="e.g. Does higher app engagement reduce HbA1c at 12 months?"
                className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground"
              />
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[11px] text-muted-foreground">
                Parsed automatically as you type — regex instantly, Haiku a moment later.
              </p>
              <Button
                onClick={() => setSub('dag')}
                disabled={!question.trim()}
                className="ml-auto gap-1.5"
              >
                Continue to DAG
              </Button>
            </div>
          </Card>
          {regexParse ? (
            <ParseCompare
              regex={regexParse}
              haiku={haikuParse}
              haikuBusy={showHaikuBusy}
              haikuError={haikuErr}
            />
          ) : (
            <EmptyState
              icon={Sparkles}
              title="Frame your causal question"
              subtitle="Type a clinical question (10+ characters). It's parsed into PICOT with a ✓/gap marker per element from the taxonomy."
            />
          )}

          {regexParse &&
            (gaps.length === 0 ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-[12px] text-emerald-800">
                All PICOT elements resolved to taxonomy concepts ✓ — ready to generate.
              </div>
            ) : (
              <Card className="flex flex-col gap-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[12px] font-semibold text-amber-700">
                    {gaps.length} taxonomy gap{gaps.length === 1 ? '' : 's'} — resolve before
                    generating
                  </div>
                  <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={proceedWithGaps}
                      onChange={(e) => setProceedWithGaps(e.target.checked)}
                      className="h-3.5 w-3.5 accent-primary"
                    />
                    Proceed with gaps
                  </label>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {gaps.map((g, i) => (
                    <Badge
                      key={i}
                      variant="outline"
                      className="border-amber-300 text-[10.5px] text-amber-700"
                    >
                      {g}
                    </Badge>
                  ))}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Propose taxonomy concepts + relations to cover these gaps, review, and apply — the
                  parse re-checks automatically.
                </p>
                <EnrichmentPanel
                  externalQuestion={question}
                  onApplied={() => setStoreVersion((v) => v + 1)}
                />
              </Card>
            ))}
        </div>
      )}

      {sub === 'dag' && (
        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
                Link a dataset (optional)
                <select
                  value={datasetId}
                  onChange={(e) => setDatasetId(e.target.value)}
                  className="min-w-[220px] rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground"
                >
                  <option value="">{datasets == null ? 'Loading…' : 'No dataset'}</option>
                  {(datasets || []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                onClick={generate}
                disabled={!question.trim() || busy || (gaps.length > 0 && !proceedWithGaps)}
                className="gap-1.5"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {busy ? 'Generating…' : 'Generate causal model'}
              </Button>
            </div>
            {!question.trim() && (
              <p className="text-[12px] text-muted-foreground">
                Enter a clinical question in the “Causal question” tab first.
              </p>
            )}
            {question.trim() && gaps.length > 0 && !proceedWithGaps && (
              <p className="text-[12px] text-amber-700">
                {gaps.length} unresolved taxonomy gap{gaps.length === 1 ? '' : 's'} — resolve them in
                the “Causal question” tab, or check “Proceed with gaps”.
              </p>
            )}
            {error && <p className="text-[12px] text-red-700">{error}</p>}
          </Card>

          {busy && <Loading label="Querying the causal ontology and contextualizing…" />}
          {!busy && dag && <Result dag={dag} onAccepted={generate} />}
          {!busy && !dag && !error && (
            <EmptyState
              icon={Network}
              title="No causal model yet"
              subtitle="Generate a DAG grounded in the reviewed causal ontology — link a dataset to ground it in your data, or generate from the question alone."
            />
          )}
        </div>
      )}
    </WorkspacePage>
  )
}
