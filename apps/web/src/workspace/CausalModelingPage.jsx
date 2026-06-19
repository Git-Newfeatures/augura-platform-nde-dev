import { useState, useEffect } from 'react'
import { Network, Sparkles, TriangleAlert } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { apiJson } from '@/api'
import { parsePICOT } from '@/semantic/picot-parser'

// Causal modeling (port de la vue /causal de Nico, recâblée sur le backend).
// Flux : dataset mappé → POST /datasets/{id}/map (concepts) → POST /causal/dag.
// Le rendu SVG est en lecture seule pour cette première itération (l'éditeur
// drag/reclassify de IntakeDAG.jsx viendra ensuite).

// Couleurs de rôle (port fidèle de IntakeDAG.jsx).
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

// Les arêtes proposées par le LLM portent l'id `proposed_<subj>_<obj>` (cf. builder).
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
          return (
            <g key={n.id}>
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
                x={rx + NODE_W / 2}
                y={ry + NODE_H / 2 + 4}
                textAnchor="middle"
                fontSize="11.5"
                fontWeight="600"
                fill={s.text}
                style={{ pointerEvents: 'none' }}
              >
                {n.label.length > 20 ? n.label.slice(0, 19) + '…' : n.label}
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

function Result({ dag }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <QualityBadge q={dag.quality} />
        <Badge variant="secondary">{dag.nodes.length} nodes</Badge>
        <Badge variant="secondary">{dag.edges.length} edges</Badge>
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
    </div>
  )
}

export function CausalModelingPage() {
  const [datasets, setDatasets] = useState(null)
  const [datasetId, setDatasetId] = useState('')
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dag, setDag] = useState(null)

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

  async function generate() {
    if (!datasetId) return
    setBusy(true)
    setError('')
    setDag(null)
    try {
      const map = await apiJson(`/datasets/${datasetId}/map`, { method: 'POST' })
      const mapped_concepts = (map.columns || [])
        .filter((c) => c.proposed_canonical_id)
        .map((c) => ({
          concept_id: c.proposed_canonical_id,
          concept_label: c.column,
          confidence: c.confidence,
        }))
      // PICOT dérivé de la question (parser local) → enrichit le prompt B2.
      // Défensif : tout échec retombe sur picot=null (comportement d'avant inchangé).
      let picot = null
      try {
        if (question) {
          const p = parsePICOT(question)
          picot = {
            intervention: p.intervention ?? null,
            comparator: p.comparator ?? null,
            outcomes: (p.outcomes || []).map((o) => ({
              concept_id: o.concept_id ?? null,
              label: o.label ?? null,
            })),
            timeframe:
              Array.isArray(p.time_window) && p.time_window.length
                ? p.time_window.join(', ')
                : null,
            population: p.population ?? null,
            therapeutic_area: p.therapeutic_areas?.[0] ?? null,
            intervention_concept_id: null,
          }
        }
      } catch {
        picot = null
      }
      const result = await apiJson('/causal/dag', {
        method: 'POST',
        body: JSON.stringify({ mapped_concepts, picot, clinical_question: question || null }),
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
      sub="Generate an ontology-grounded causal DAG from a mapped dataset. Reviewed ontology relations are the ground truth; the LLM only contextualizes them to your question."
    >
      <Card className="mb-5 flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
            Dataset
            <select
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              className="min-w-[220px] rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground"
            >
              <option value="">{datasets == null ? 'Loading…' : 'Select a dataset…'}</option>
              {(datasets || []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={generate} disabled={!datasetId || busy} className="gap-1.5">
            <Sparkles className="h-3.5 w-3.5" />
            {busy ? 'Generating…' : 'Generate causal model'}
          </Button>
        </div>
        <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
          Clinical question (optional)
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            placeholder="e.g. Does higher app engagement reduce HbA1c at 12 months?"
            className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground"
          />
        </label>
        {error && <p className="text-[12px] text-red-700">{error}</p>}
      </Card>

      {busy && <Loading label="Querying the causal ontology and contextualizing…" />}
      {!busy && dag && <Result dag={dag} />}
      {!busy && !dag && !error && (
        <EmptyState
          icon={Network}
          title="No causal model yet"
          subtitle="Pick a mapped dataset and generate a DAG grounded in the reviewed causal ontology."
        />
      )}
    </WorkspacePage>
  )
}
