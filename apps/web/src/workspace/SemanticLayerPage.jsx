import { useState, useMemo, useEffect } from 'react'
import { BookOpen, GitMerge, History, Search, Sparkles, X } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { SubTabs } from '@/cockpit/SubTabs'
import { apiJson } from '@/api'
import { getTaxonomyIndex, getConceptById } from '@/semantic/taxonomy-loader'
import { getCausalOntology } from '@/causal/ontology-loader'
import { getStoredSynonyms, getStoredStandardCodes, initSemanticStore, isSemanticStoreReady } from '@/lib/semantic-store'
import { EnrichmentPanel } from '@/workspace/EnrichmentPanel'

// Semantic layer browser (taxonomy + causal ontology + version).
// Ported from data-intake-nde. The Enrichment tab exposes the B4 pipeline
// (enrichPropose → review → enrichApply) via EnrichmentPanel.

// ── Shared modal shell ────────────────────────────────────────────────────────

const MODAL_TABS_STYLE = 'flex gap-0.5 border-b border-border mb-5'
const MODAL_TAB = (on) =>
  `-mb-px whitespace-nowrap border-b-2 px-3.5 py-2 text-[12.5px] font-medium transition-colors ${
    on ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
  }`

function Modal({ title, subtitle, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        className="relative mx-0 w-full max-w-2xl overflow-hidden rounded-t-2xl border border-border bg-background shadow-2xl sm:mx-4 sm:rounded-2xl"
        style={{ maxHeight: '85vh' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-semibold text-foreground">{title}</h2>
            {subtitle && <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="mt-0.5 flex-shrink-0 text-muted-foreground hover:text-foreground">
            <X size={17} />
          </button>
        </div>
        <div className="overflow-y-auto px-6 py-5" style={{ maxHeight: 'calc(85vh - 68px)' }}>
          {children}
        </div>
      </div>
    </div>
  )
}

// ── Concept detail modal ──────────────────────────────────────────────────────

const SYNONYM_TYPE_CHIP = {
  preferred:      'bg-primary/10 text-primary border-primary/20',
  acceptable:     'bg-muted/60 text-foreground border-border',
  abbreviation:   'bg-amber-50 text-amber-700 border-amber-200',
  brand_name:     'bg-indigo-50 text-indigo-700 border-indigo-200',
  dataset_column: 'bg-gray-50 text-gray-600 border-gray-200',
}

const POLARITY_STYLE = {
  increases: { chip: 'text-emerald-700 bg-emerald-50 border-emerald-200', symbol: '↑' },
  decreases: { chip: 'text-red-700 bg-red-50 border-red-200',            symbol: '↓' },
  neutral:   { chip: 'text-gray-600 bg-gray-50 border-gray-200',         symbol: '↔' },
}

function ConceptModal({ concept, onClose }) {
  const [tab, setTab] = useState('overview')

  const synonymRows = useMemo(
    () => (getStoredSynonyms() || []).filter(s => s.local_concept_id === concept.id),
    [concept.id]
  )
  const codeRows = useMemo(
    () => (getStoredStandardCodes() || []).filter(s => s.local_concept_id === concept.id),
    [concept.id]
  )
  const relations = useMemo(() => {
    const ont = getCausalOntology()
    return (ont.relations || []).filter(
      r => r.subject_concept_id === concept.id || r.object_concept_id === concept.id
    )
  }, [concept.id])

  return (
    <Modal title={concept.label} subtitle={concept.id} onClose={onClose}>
      <div className={MODAL_TABS_STYLE}>
        {[
          { id: 'overview',  label: 'Overview' },
          { id: 'synonyms',  label: `Synonyms${synonymRows.length ? ` (${synonymRows.length})` : ''}` },
          { id: 'standards', label: `Standards${codeRows.length ? ` (${codeRows.length})` : ''}` },
          { id: 'relations', label: `Relations${relations.length ? ` (${relations.length})` : ''}` },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} className={MODAL_TAB(tab === t.id)}>{t.label}</button>
        ))}
      </div>

      {tab === 'overview' && (
        <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-3 text-[13px]">
          {[
            ['Domain',         concept.domain],
            ['Layer',          `L${concept.layer}`],
            ['Review status',  concept.review_status],
            ['Version',        concept.version],
            ['Value type',     concept.value_type],
            ['Canonical unit', concept.canonical_unit],
            ['Value range',    concept.value_range ? `${concept.value_range[0]} – ${concept.value_range[1]}` : null],
            ['Temporality',    concept.temporality],
            ['OMOP domain',    concept.omop_domain],
            ['FHIR crosswalk', concept.fhir_crosswalk],
            ['SDTM crosswalk', concept.sdtm_crosswalk],
          ].filter(([, v]) => v).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-medium text-muted-foreground">{k}</dt>
              <dd className="text-foreground">{v}</dd>
            </div>
          ))}
          {concept.design_rationale && (
            <div className="col-span-2 mt-1 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2.5 text-[12.5px] text-amber-800">
              <span className="font-semibold">L2 rationale: </span>{concept.design_rationale}
            </div>
          )}
          {(concept.therapeutic_areas || []).length > 0 && (
            <div className="col-span-2 flex flex-wrap gap-1.5 mt-1">
              {concept.therapeutic_areas.map(a => (
                <span key={a} className="rounded-full bg-muted/50 border border-border px-2.5 py-0.5 text-[11.5px] text-muted-foreground">{a}</span>
              ))}
            </div>
          )}
        </dl>
      )}

      {tab === 'synonyms' && (
        synonymRows.length === 0
          ? <p className="text-[13px] text-muted-foreground">No synonyms recorded.</p>
          : <div className="flex flex-col gap-2">
              {synonymRows.map((s, i) => (
                <div key={i} className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-3.5 py-2.5">
                  <span className="flex-1 font-mono text-[13px] text-foreground">{s.synonym}</span>
                  <span className={`rounded border px-1.5 py-px text-[10.5px] font-medium ${SYNONYM_TYPE_CHIP[s.synonym_type] || 'bg-muted/40 text-muted-foreground border-border'}`}>
                    {s.synonym_type}
                  </span>
                  {s.source && <span className="text-[11px] text-muted-foreground/70">{s.source}</span>}
                </div>
              ))}
            </div>
      )}

      {tab === 'standards' && (
        codeRows.length === 0
          ? <p className="text-[13px] text-muted-foreground">No standard codes recorded.{concept.layer === 1 ? ' ⚠ Layer 1 concept should have at least one code.' : ''}</p>
          : <div className="flex flex-col gap-2">
              {codeRows.map((c, i) => (
                <div key={i} className="rounded-lg border border-border bg-muted/20 px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{c.vocabulary_id}</span>
                    <span className="font-mono text-[14px] font-semibold text-foreground">{c.concept_code}</span>
                    {c.standard_concept_flag === 'S' && (
                      <span className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-px text-[10px] font-medium text-emerald-700">Standard</span>
                    )}
                  </div>
                  {c.standard_concept_name && (
                    <div className="mt-1 text-[12.5px] text-muted-foreground">{c.standard_concept_name}</div>
                  )}
                </div>
              ))}
            </div>
      )}

      {tab === 'relations' && (
        relations.length === 0
          ? <p className="text-[13px] text-muted-foreground">This concept appears in no causal relations yet.</p>
          : <div className="flex flex-col gap-2">
              {relations.map(r => {
                const isSubject = r.subject_concept_id === concept.id
                const otherLabel = isSubject
                  ? getConceptById(r.object_concept_id)?.label  || r.object_concept_id
                  : getConceptById(r.subject_concept_id)?.label || r.subject_concept_id
                const pol = POLARITY_STYLE[r.polarity] || POLARITY_STYLE.neutral
                return (
                  <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/20 px-3.5 py-2.5 text-[13px]">
                    {isSubject ? (
                      <>
                        <span className="font-semibold text-primary">{concept.label}</span>
                        <span className="text-muted-foreground">→</span>
                        <span className="rounded border px-1.5 py-px text-[11px] font-mono border-border bg-muted/40 text-muted-foreground">{r.predicate.replace(/_/g, ' ')}</span>
                        <span className={`rounded border px-1.5 py-px text-[11px] font-semibold ${pol.chip}`}>{pol.symbol}</span>
                        <span className="text-foreground">{otherLabel}</span>
                      </>
                    ) : (
                      <>
                        <span className="text-foreground">{otherLabel}</span>
                        <span className="text-muted-foreground">→</span>
                        <span className="rounded border px-1.5 py-px text-[11px] font-mono border-border bg-muted/40 text-muted-foreground">{r.predicate.replace(/_/g, ' ')}</span>
                        <span className={`rounded border px-1.5 py-px text-[11px] font-semibold ${pol.chip}`}>{pol.symbol}</span>
                        <span className="font-semibold text-primary">{concept.label}</span>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
      )}
    </Modal>
  )
}

// ── Relation detail modal ─────────────────────────────────────────────────────

const SOURCE_TYPE_LABEL = {
  established_physiology: 'Established physiology',
  rct:                    'RCT',
  systematic_review:      'Systematic review',
  observational_cohort:   'Observational cohort',
  case_series:            'Case series',
  expert_consensus:       'Expert consensus',
  guideline:              'Guideline',
}

const STRENGTH_CHIP = {
  established: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  strong:      'bg-emerald-50 text-emerald-700 border-emerald-200',
  moderate:    'bg-amber-50 text-amber-700 border-amber-200',
  weak:        'bg-orange-50 text-orange-700 border-orange-200',
  unknown:     'bg-gray-50 text-gray-600 border-gray-200',
}

const STRENGTH_STYLE = {
  established: 'text-foreground font-semibold',
  strong:   'text-foreground font-semibold',
  moderate: 'text-muted-foreground',
  weak:     'text-muted-foreground/60',
  unknown:  'text-muted-foreground/40',
}

function RelationModal({ relation, onClose }) {
  const [tab, setTab] = useState('overview')
  const subLabel = getConceptById(relation.subject_concept_id)?.label || relation.subject_concept_id
  const objLabel = getConceptById(relation.object_concept_id)?.label  || relation.object_concept_id
  const pol = POLARITY_STYLE[relation.polarity] || POLARITY_STYLE.neutral

  return (
    <Modal title={`${subLabel} → ${objLabel}`} subtitle={relation.id} onClose={onClose}>
      <div className={MODAL_TABS_STYLE}>
        {[
          { id: 'overview',   label: 'Overview' },
          { id: 'evidence',   label: `Evidence (${(relation.evidence || []).length})` },
          { id: 'qualifiers', label: `Qualifiers (${(relation.qualifiers || []).length})` },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} className={MODAL_TAB(tab === t.id)}>{t.label}</button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-muted/20 px-4 py-3 text-[13px]">
            <span className="font-medium text-foreground">{subLabel}</span>
            <span className="rounded border border-border bg-muted/40 px-2 py-px font-mono text-[11px] text-muted-foreground">{relation.predicate.replace(/_/g, ' ')}</span>
            <span className={`rounded border px-1.5 py-px text-[11.5px] font-semibold ${pol.chip}`}>{pol.symbol} {relation.polarity}</span>
            <span className="text-muted-foreground">→</span>
            <span className="font-medium text-foreground">{objLabel}</span>
          </div>
          <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-3 text-[13px]">
            {[
              ['Strength',      relation.default_strength],
              ['Temporal lag',  relation.default_temporal_lag],
              ['Review status', relation.review_status],
              ['Version',       relation.version],
            ].filter(([, v]) => v).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="font-medium text-muted-foreground">{k}</dt>
                <dd className="text-foreground">{v}</dd>
              </div>
            ))}
          </dl>
          {relation.mechanism_summary && (
            <div className="rounded-lg border border-border bg-muted/20 px-4 py-3">
              <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">Mechanism</div>
              <p className="text-[13px] leading-relaxed text-foreground">{relation.mechanism_summary}</p>
            </div>
          )}
        </div>
      )}

      {tab === 'evidence' && (
        (relation.evidence || []).length === 0
          ? <p className="text-[13px] text-muted-foreground">No evidence recorded.</p>
          : <div className="flex flex-col gap-3">
              {(relation.evidence || []).map((e, i) => (
                <div key={i} className="rounded-xl border border-border bg-muted/10 px-4 py-3.5">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="text-[12px] font-semibold text-foreground">{SOURCE_TYPE_LABEL[e.source_type] || e.source_type}</span>
                    <span className={`rounded border px-1.5 py-px text-[10.5px] font-medium ${STRENGTH_CHIP[e.strength] || STRENGTH_CHIP.unknown}`}>
                      {e.strength}
                    </span>
                  </div>
                  {e.summary && <p className="mb-1.5 text-[12.5px] leading-relaxed text-foreground">{e.summary}</p>}
                  {e.population && <p className="mb-1 text-[12px] text-muted-foreground"><span className="font-medium">Population:</span> {e.population}</p>}
                  {e.citation && e.citation !== 'established physiology' && (
                    <p className="text-[11.5px] text-muted-foreground/80 italic">{e.citation}</p>
                  )}
                </div>
              ))}
            </div>
      )}

      {tab === 'qualifiers' && (
        (relation.qualifiers || []).length === 0
          ? <p className="text-[13px] text-muted-foreground">No qualifiers recorded.</p>
          : <div className="flex flex-col gap-3">
              {(relation.qualifiers || []).map((q, i) => (
                <div key={i} className="rounded-xl border border-border bg-muted/10 px-4 py-3.5">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="rounded border border-border bg-muted/40 px-1.5 py-px font-mono text-[10.5px] text-muted-foreground">{q.type}</span>
                    <span className="text-[13px] font-semibold text-foreground">{q.value}</span>
                    {q.is_hard_constraint && (
                      <span className="rounded border border-red-200 bg-red-50 px-1.5 py-px text-[10px] font-semibold text-red-700">Hard constraint</span>
                    )}
                  </div>
                  <div className="text-[12.5px] text-muted-foreground">
                    Effect: <span className="font-medium text-foreground">{q.effect?.replace(/_/g, ' ')}</span>
                  </div>
                  {q.notes && <p className="mt-1 text-[12px] text-muted-foreground italic">{q.notes}</p>}
                </div>
              ))}
            </div>
      )}
    </Modal>
  )
}

// ── Taxonomy tab ──────────────────────────────────────────────────────────────

const DOMAIN_CHIP = {
  therapeutics: 'text-blue-700 bg-blue-50 border-blue-200',
  measurement:  'text-amber-700 bg-amber-50 border-amber-200',
  condition:    'text-violet-700 bg-violet-50 border-violet-200',
  device:       'text-indigo-700 bg-indigo-50 border-indigo-200',
  procedure:    'text-cyan-700 bg-cyan-50 border-cyan-200',
  outcome:      'text-orange-700 bg-orange-50 border-orange-200',
  biomarker:    'text-teal-700 bg-teal-50 border-teal-200',
  pharmacology: 'text-rose-700 bg-rose-50 border-rose-200',
  structural:   'text-gray-600 bg-gray-50 border-gray-200',
}

function TaxonomyTab() {
  const [q, setQ] = useState('')
  const [domainFilter, setDomainFilter] = useState('all')
  const [layerFilter, setLayerFilter] = useState('all')
  const [modalConcept, setModalConcept] = useState(null)

  const allConcepts = useMemo(() => getTaxonomyIndex(), [])
  const domains = useMemo(
    () => ['all', ...new Set(allConcepts.map(c => c.domain).filter(Boolean))].sort((a, b) => a === 'all' ? -1 : a.localeCompare(b)),
    [allConcepts]
  )

  const filtered = useMemo(() => {
    const lq = q.toLowerCase()
    return allConcepts.filter(c => {
      if (domainFilter !== 'all' && c.domain !== domainFilter) return false
      if (layerFilter !== 'all' && String(c.layer) !== layerFilter) return false
      if (lq && !c.label.toLowerCase().includes(lq) && !(c.synonyms || []).some(s => s.toLowerCase().includes(lq))) return false
      return true
    })
  }, [allConcepts, q, domainFilter, layerFilter])

  const vocabBadge = (codes) => {
    if (!codes) return null
    const vocs = Object.keys(codes).filter(k => codes[k])
    if (!vocs.length) return null
    return vocs.map(v => (
      <span key={v} className="rounded border border-border bg-muted/40 px-1.5 py-px font-mono text-[10px] text-muted-foreground uppercase">
        {v}
      </span>
    ))
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search concepts or synonyms…"
            className="w-full rounded-md border border-border bg-background pl-8 pr-3 py-1.5 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <select value={layerFilter} onChange={e => setLayerFilter(e.target.value)} className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary">
          <option value="all">All layers</option>
          <option value="1">Layer 1 (standard)</option>
          <option value="2">Layer 2 (augura)</option>
        </select>
        <select value={domainFilter} onChange={e => setDomainFilter(e.target.value)} className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary">
          {domains.map(d => <option key={d} value={d}>{d === 'all' ? 'All domains' : d}</option>)}
        </select>
        <span className="text-[12px] text-muted-foreground">{filtered.length} concept{filtered.length !== 1 ? 's' : ''}</span>
      </div>

      {filtered.length === 0 ? (
        <div className="py-12 text-center text-[13px] text-muted-foreground">No concepts match your filters.</div>
      ) : (
        <Card className="gap-0 px-[18px] py-1 overflow-x-auto">
          <div className="flex min-w-[680px] gap-3 border-b border-border py-[11px] text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/70">
            <span className="flex-1">Concept</span>
            <span className="w-[120px]">Domain</span>
            <span className="w-16 text-center">Layer</span>
            <span className="w-[160px]">Standards</span>
            <span className="w-16 text-right">Synonyms</span>
          </div>
          {filtered.map((c, i) => (
            <div
              key={c.id}
              onClick={() => setModalConcept(c)}
              className={`flex min-w-[680px] cursor-pointer items-center gap-3 py-2.5 transition-colors hover:bg-muted/30 ${i < filtered.length - 1 ? 'border-b border-border' : ''}`}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate text-[13px] font-medium text-foreground">{c.label}</div>
                <div className="font-mono text-[10.5px] text-muted-foreground/70">{c.id}</div>
              </div>
              <div className="w-[120px]">
                <span className={`inline-block truncate rounded border px-1.5 py-px text-[10.5px] font-medium ${DOMAIN_CHIP[c.domain] || 'text-muted-foreground bg-muted/40 border-border'}`}>
                  {c.domain || '—'}
                </span>
              </div>
              <div className="w-16 text-center">
                <span className={`rounded border px-1.5 py-px text-[10.5px] font-mono font-semibold ${c.layer === 1 ? 'border-primary/30 bg-primary/5 text-primary' : 'border-border bg-muted/40 text-muted-foreground'}`}>
                  L{c.layer}
                </span>
              </div>
              <div className="flex w-[160px] flex-wrap gap-1">
                {vocabBadge(c.standard_codes) || <span className="text-[11px] text-muted-foreground/50">—</span>}
              </div>
              <div className="w-16 text-right font-mono text-[12px] text-muted-foreground">
                {c.synonyms?.length || 0}
              </div>
            </div>
          ))}
        </Card>
      )}

      {modalConcept && <ConceptModal concept={modalConcept} onClose={() => setModalConcept(null)} />}
    </>
  )
}

// ── Causal ontology tab ───────────────────────────────────────────────────────

function CausalOntologyTab() {
  const [q, setQ] = useState('')
  const [predFilter, setPredFilter] = useState('all')
  const [polarityFilter, setPolarityFilter] = useState('all')
  const [selected, setSelected] = useState(null)

  const ontology = useMemo(() => getCausalOntology(), [])
  const predicates = useMemo(() => Object.keys(ontology.predicates || {}), [ontology])

  const filtered = useMemo(() => {
    const lq = q.toLowerCase()
    return (ontology.relations || []).filter(r => {
      if (predFilter !== 'all' && r.predicate !== predFilter) return false
      if (polarityFilter !== 'all' && r.polarity !== polarityFilter) return false
      if (lq) {
        const subLabel = getConceptById(r.subject_concept_id)?.label?.toLowerCase() || r.subject_concept_id.toLowerCase()
        const objLabel = getConceptById(r.object_concept_id)?.label?.toLowerCase() || r.object_concept_id.toLowerCase()
        if (!subLabel.includes(lq) && !objLabel.includes(lq) && !r.predicate.includes(lq)) return false
      }
      return true
    })
  }, [ontology, q, predFilter, polarityFilter])

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search by concept name or predicate…"
            className="w-full rounded-md border border-border bg-background pl-8 pr-3 py-1.5 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <select value={predFilter} onChange={e => setPredFilter(e.target.value)} className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary">
          <option value="all">All predicates</option>
          {predicates.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={polarityFilter} onChange={e => setPolarityFilter(e.target.value)} className="rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary">
          <option value="all">All polarities</option>
          <option value="increases">↑ Increases</option>
          <option value="decreases">↓ Decreases</option>
          <option value="neutral">↔ Neutral</option>
        </select>
        <span className="text-[12px] text-muted-foreground">{filtered.length} relation{filtered.length !== 1 ? 's' : ''}</span>
      </div>

      {filtered.length === 0 ? (
        <div className="py-12 text-center text-[13px] text-muted-foreground">No relations match your filters.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map(r => {
            const subLabel = getConceptById(r.subject_concept_id)?.label || r.subject_concept_id
            const objLabel = getConceptById(r.object_concept_id)?.label  || r.object_concept_id
            const pol = POLARITY_STYLE[r.polarity] || POLARITY_STYLE.neutral
            return (
              <Card key={r.id} onClick={() => setSelected(r)} className="cursor-pointer gap-2 rounded-xl border px-4 py-3 transition-colors hover:bg-muted/30">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="font-medium text-foreground">{subLabel}</span>
                  <span className="flex items-center gap-1 rounded border px-2 py-px text-[11px] font-mono border-border bg-muted/40 text-muted-foreground">
                    {r.predicate.replace(/_/g, ' ')}
                  </span>
                  <span className={`rounded border px-1.5 py-px text-[11px] font-semibold ${pol.chip}`}>
                    {pol.symbol} {r.polarity}
                  </span>
                  <span className="text-muted-foreground">→</span>
                  <span className="font-medium text-foreground">{objLabel}</span>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-[11.5px] text-muted-foreground">
                  <span className={`font-medium ${STRENGTH_STYLE[r.default_strength] || ''}`}>{r.default_strength || 'unknown'} evidence</span>
                  {r.evidence?.length > 0 && <span>{r.evidence.length} source{r.evidence.length !== 1 ? 's' : ''}</span>}
                  {r.mechanism_summary && <span className="truncate max-w-[420px]">{r.mechanism_summary}</span>}
                </div>
              </Card>
            )
          })}
        </div>
      )}
      {selected && <RelationModal relation={selected} onClose={() => setSelected(null)} />}
    </>
  )
}

// ── Version admin tab ─────────────────────────────────────────────────────────

const humanize = (s) => String(s || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

function VersionAdminTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    apiJson('/semantic/release')
      .then(d => { if (alive) { setData(d); setLoading(false) } })
      .catch(e => { if (alive) { setError(e.message || String(e)); setLoading(false) } })
    return () => { alive = false }
  }, [])

  if (loading) {
    return <div className="py-12 text-center text-[13px] text-muted-foreground">Loading release info…</div>
  }
  if (error) {
    return <div className="py-12 text-center text-[13px] text-muted-foreground">Could not load release status: {error}</div>
  }

  const release = data?.release
  const counts = data?.counts || {}

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Current release</h3>
        {release ? (
          <Card className="gap-0 divide-y divide-border px-0 py-0 overflow-hidden">
            {[
              ['Semantic release', release.semantic_release_version],
              ['Taxonomy',         release.taxonomy_version],
              ['Causal ontology',  release.causal_ontology_version],
              ['DQ ontology',      release.dq_ontology_version],
              ['OMOP CDM',         release.omop_cdm_version],
              ['Source',           release.source],
            ].map(([label, value]) => value && (
              <div key={label} className="flex items-center justify-between px-4 py-2.5 text-[13px]">
                <span className="text-muted-foreground">{label}</span>
                <span className="font-mono font-semibold text-foreground">{value}</span>
              </div>
            ))}
          </Card>
        ) : (
          <p className="text-[13px] text-muted-foreground">No current release recorded — the semantic seed may not be applied yet.</p>
        )}
      </section>

      {Object.keys(counts).length > 0 && (
        <section>
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Table counts</h3>
          <Card className="gap-0 divide-y divide-border px-0 py-0 overflow-hidden">
            {Object.entries(counts).sort(([a], [b]) => a.localeCompare(b)).map(([table, n]) => (
              <div key={table} className="flex items-center justify-between px-4 py-2 text-[13px]">
                <span className="text-muted-foreground">{humanize(table)}</span>
                <span className="font-mono font-semibold text-foreground">{n}</span>
              </div>
            ))}
          </Card>
        </section>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

function Notice({ children }) {
  return <div className="py-16 text-center text-[13px] text-muted-foreground">{children}</div>
}

export function SemanticLayerPage() {
  const [sub, setSub] = useState('taxonomy')
  const [ready, setReady] = useState(() => isSemanticStoreReady())
  const [error, setError] = useState(null)

  useEffect(() => {
    if (ready) return
    let alive = true
    initSemanticStore()
      .then(() => { if (alive) setReady(true) })
      .catch(e => { if (alive) setError(e.message || String(e)) })
    return () => { alive = false }
  }, [ready])

  let body
  if (error) {
    body = <Notice>Could not load the semantic layer: {error}</Notice>
  } else if (!ready) {
    body = <Notice>Loading the semantic layer…</Notice>
  } else {
    body = (
      <>
        <SubTabs
          tabs={[
            { id: 'taxonomy',    label: 'Taxonomy',        icon: <BookOpen  size={13} /> },
            { id: 'causal',      label: 'Causal ontology', icon: <GitMerge  size={13} /> },
            { id: 'enrichment',  label: 'Enrichment',       icon: <Sparkles  size={13} /> },
            { id: 'versions',    label: 'Versions',        icon: <History   size={13} /> },
          ]}
          active={sub}
          onChange={setSub}
        />
        {sub === 'taxonomy'   && <TaxonomyTab />}
        {sub === 'causal'     && <CausalOntologyTab />}
        {sub === 'enrichment' && <EnrichmentPanel />}
        {sub === 'versions'   && <VersionAdminTab />}
      </>
    )
  }

  return (
    <WorkspacePage title="Semantic layer" sub="Taxonomy, causal ontology, and version management">
      {body}
    </WorkspacePage>
  )
}
