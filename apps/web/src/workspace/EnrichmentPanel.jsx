/**
 * EnrichmentPanel — panneau d'enrichissement sémantique B4.
 *
 * Flux : saisie d'une question clinique → job enrichPropose → polling avec
 * barre de progression → revue des propositions (concepts + relations) avec
 * cases à cocher → enrichApply → rechargement du store sémantique.
 *
 * Adapté de LearnFromQuestionPanel (lucis-dashboard) pour l'architecture
 * job + polling (au lieu du SSE direct).
 */
import { useState, useCallback } from 'react'
import { Sparkles } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { enrichPropose, pollJob, fetchEnrichProposals, enrichApply } from '@/workspace/dataClient'
import { resetSemanticStore, initSemanticStore } from '@/lib/semantic-store'
import { parsePICOT } from '@/semantic/picot-parser'

// ── Couleurs domaine (reprises de LearnFromQuestionPanel) ─────────────────────

function domainColor(domain) {
  const colors = {
    therapeutics: 'bg-blue-50 text-blue-700 border-blue-200',
    measurement:  'bg-purple-50 text-purple-700 border-purple-200',
    condition:    'bg-red-50 text-red-700 border-red-200',
    device:       'bg-teal-50 text-teal-700 border-teal-200',
    outcome:      'bg-green-50 text-green-700 border-green-200',
    biomarker:    'bg-orange-50 text-orange-700 border-orange-200',
    procedure:    'bg-yellow-50 text-yellow-700 border-yellow-200',
    pharmacology: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    structural:   'bg-gray-50 text-gray-700 border-gray-200',
  }
  return colors[domain] || 'bg-muted text-muted-foreground border-border'
}

// ── Barre de progression ──────────────────────────────────────────────────────

function ProgressBar({ value }) {
  // value : 0–100
  const pct = Math.max(0, Math.min(100, value ?? 0))
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-primary transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ── Item concept proposé ──────────────────────────────────────────────────────

function ConceptItem({ concept, checked, onToggle }) {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-md border px-3 py-2 transition-colors ${
        checked ? 'border-border bg-background' : 'border-border/40 bg-muted/30 opacity-60'
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={() => onToggle(concept.local_concept_id)}
        className="mt-0.5 h-3.5 w-3.5 cursor-pointer accent-primary"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] font-medium text-foreground">{concept.concept_name}</span>
          {concept.augura_domain && (
            <span className={`rounded border px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wide ${domainColor(concept.augura_domain)}`}>
              {concept.augura_domain}
            </span>
          )}
          {concept.layer != null && (
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
              L{concept.layer}
            </span>
          )}
          {concept.layer === 1 && (
            <span className="rounded border border-green-200 bg-green-50 px-1.5 py-0.5 font-mono text-[9px] text-green-700">
              standard code
            </span>
          )}
        </div>
        {concept.design_rationale && (
          <div className="mt-0.5 text-[10.5px] text-muted-foreground leading-snug">
            {concept.design_rationale}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Item relation proposée ────────────────────────────────────────────────────

function RelationItem({ relation, checked, onToggle, conceptLabels }) {
  const subjectLabel = conceptLabels[relation.subject_concept_id] || relation.subject_concept_id
  const objectLabel  = conceptLabels[relation.object_concept_id]  || relation.object_concept_id

  const polarityColor =
    relation.polarity === 'increases' ? 'text-green-700' :
    relation.polarity === 'decreases' ? 'text-red-700'   :
    'text-muted-foreground'

  return (
    <div
      className={`flex items-start gap-2.5 rounded-md border px-3 py-2 transition-colors ${
        checked ? 'border-border bg-background' : 'border-border/40 bg-muted/30 opacity-60'
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={() => onToggle(relation.relation_id)}
        className="mt-0.5 h-3.5 w-3.5 cursor-pointer accent-primary"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-1 text-[11.5px]">
          <span className="font-medium text-foreground">{subjectLabel}</span>
          <span className="font-mono text-[9.5px] text-muted-foreground">→</span>
          <span className={`font-mono text-[9.5px] ${polarityColor}`}>
            {relation.predicate}
          </span>
          <span className="font-mono text-[9.5px] text-muted-foreground">→</span>
          <span className="font-medium text-foreground">{objectLabel}</span>
        </div>
        {relation.mechanism_summary && (
          <div className="mt-0.5 text-[10.5px] text-muted-foreground leading-snug">
            {relation.mechanism_summary}
          </div>
        )}
        <div className="mt-0.5 flex gap-2">
          {relation.default_strength && (
            <span className="font-mono text-[9px] text-muted-foreground/70">{relation.default_strength}</span>
          )}
          {relation.default_strength && relation.default_temporal_lag && (
            <span className="font-mono text-[9px] text-muted-foreground/70">·</span>
          )}
          {relation.default_temporal_lag && (
            <span className="font-mono text-[9px] text-muted-foreground/70">{relation.default_temporal_lag}</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Composant principal ───────────────────────────────────────────────────────

export function EnrichmentPanel() {
  const [phase,    setPhase]    = useState('idle')   // idle | running | review | applying | done | error
  const [progress, setProgress] = useState(0)
  const [artifact, setArtifact] = useState(null)
  const [selected, setSelected] = useState(() => new Set())
  const [error,    setError]    = useState('')
  const [question, setQuestion] = useState('')
  const [result,   setResult]   = useState(null)

  // ── Toggle sélection individuelle ──────────────────────────────────────────
  const toggle = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // ── Tout sélectionner / désélectionner ────────────────────────────────────
  const toggleAll = useCallback(() => {
    if (!artifact) return
    const concepts  = artifact.proposals?.taxonomy_concepts  || []
    const relations = artifact.proposals?.ontology_relations || []
    const allIds = [
      ...concepts.map((c) => c.local_concept_id),
      ...relations.map((r) => r.relation_id),
    ]
    setSelected((prev) => {
      // Si tout est sélectionné → tout désélectionner, sinon tout sélectionner
      const allSelected = allIds.every((id) => prev.has(id))
      return new Set(allSelected ? [] : allIds)
    })
  }, [artifact])

  // ── Lancement de l'analyse ────────────────────────────────────────────────
  const runPropose = useCallback(async () => {
    if (!question.trim()) return
    setPhase('running')
    setError('')
    setProgress(0)
    setArtifact(null)
    setSelected(new Set())
    setResult(null)

    try {
      // Utilise parsePICOT pour extraire les termes PICOT de la question libre
      const parsed = parsePICOT(question.trim())
      const body = {
        questions: [
          {
            id: 'q1',
            therapeutic_area: (parsed.therapeutic_areas || [])[0] || 'general',
            picot: {
              population:   parsed.population   ? [parsed.population]   : [],
              intervention: parsed.intervention ? [parsed.intervention] : [],
              comparator:   parsed.comparator   ? [parsed.comparator]   : [],
              outcome:      (parsed.outcomes || []).map((o) => o.label || o.text || String(o)),
            },
          },
        ],
      }

      const { job_id } = await enrichPropose(body)

      // Polling jusqu'à succeeded / failed. job.progress est une fraction 0..1 côté
      // backend → on la convertit en pourcentage pour la barre (0..100).
      let attempts = 0
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        const job = await pollJob(job_id)
        setProgress(Math.round((job.progress ?? 0) * 100))
        if (job.status === 'succeeded') break
        if (job.status === 'failed') throw new Error(job.error || 'Analysis failed')
        if (++attempts > 240) throw new Error('Analysis timed out — please try again')
      }

      const fetched = await fetchEnrichProposals(job_id)
      setArtifact(fetched)

      // Pré-sélectionner tous les éléments proposés
      const p = fetched?.proposals || {}
      const allIds = new Set([
        ...(p.taxonomy_concepts  || []).map((c) => c.local_concept_id),
        ...(p.ontology_relations || []).map((r) => r.relation_id),
      ])
      setSelected(allIds)
      setPhase('review')
    } catch (e) {
      setError(String(e?.message ?? e))
      setPhase('error')
    }
  }, [question])

  // ── Application des propositions sélectionnées ────────────────────────────
  const applySelected = useCallback(async () => {
    if (!artifact) return
    setPhase('applying')
    setError('')

    try {
      const p = artifact.proposals || {}
      const selected_concept_ids = (p.taxonomy_concepts || [])
        .map((c) => c.local_concept_id)
        .filter((id) => selected.has(id))
      const selected_relation_ids = (p.ontology_relations || [])
        .map((r) => r.relation_id)
        .filter((id) => selected.has(id))

      const data = await enrichApply({ proposals: p, selected_concept_ids, selected_relation_ids })
      setResult(data)
      resetSemanticStore()
      await initSemanticStore()
      setPhase('done')
    } catch (e) {
      setError(String(e?.message ?? e))
      setPhase('error')
    }
  }, [artifact, selected])

  // ── Données dérivées pour la phase review ─────────────────────────────────
  const proposals  = artifact?.proposals || {}
  const concepts   = proposals.taxonomy_concepts  || []
  const relations  = proposals.ontology_relations || []

  // Map concept_id → concept_name pour les libellés des relations
  const conceptLabels = {}
  for (const c of concepts) {
    conceptLabels[c.local_concept_id] = c.concept_name
  }

  const selectedConceptCount  = concepts.filter((c) => selected.has(c.local_concept_id)).length
  const selectedRelationCount = relations.filter((r) => selected.has(r.relation_id)).length
  const totalSelected         = selectedConceptCount + selectedRelationCount
  const totalItems            = concepts.length + relations.length
  const allSelected           = totalItems > 0 && totalSelected === totalItems

  // ── Rendu ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-5">

      {/* ── Saisie de la question (toujours visible hors done) ── */}
      {phase !== 'done' && (
        <div className="flex flex-col gap-3">
          <div>
            <label className="mb-1.5 block text-[12px] font-medium text-foreground">
              Clinical question (PICOT)
            </label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={phase === 'running' || phase === 'applying'}
              placeholder="e.g. In adults with type 2 diabetes, does empagliflozin reduce cardiovascular mortality compared with placebo?"
              rows={3}
              className="w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
            />
          </div>
          <button
            onClick={runPropose}
            disabled={!question.trim() || phase === 'running' || phase === 'applying'}
            className="flex items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Sparkles size={13} />
            Run analysis
          </button>
        </div>
      )}

      {/* ── Progression ── */}
      {phase === 'running' && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-[11.5px]">
            <span className="text-muted-foreground">Analysis in progress…</span>
            <span className="font-mono text-muted-foreground">{progress}%</span>
          </div>
          <ProgressBar value={progress} />
        </div>
      )}

      {/* ── Revue des propositions ── */}
      {phase === 'review' && (
        <div className="flex flex-col gap-4">
          {/* En-tête revue */}
          <div className="flex items-center justify-between">
            <p className="text-[11.5px] text-muted-foreground">
              All proposals are pre-selected. Uncheck any you want to skip.
            </p>
            {totalItems > 0 && (
              <button
                onClick={toggleAll}
                className="text-[11px] text-primary hover:underline whitespace-nowrap"
              >
                {allSelected ? 'Deselect all' : 'Select all'}
              </button>
            )}
          </div>

          {/* Résumé de couverture */}
          {artifact?.coverage_summary && (
            <div className="rounded-md border border-border bg-muted/20 px-3 py-2.5 text-[11.5px] text-muted-foreground">
              {artifact.summary || `Coverage: ${JSON.stringify(artifact.coverage_summary)}`}
            </div>
          )}

          {/* Aucune proposition */}
          {totalItems === 0 && (
            <div className="rounded-md border border-border bg-muted/40 px-3 py-4 text-center text-[11.5px] text-muted-foreground">
              No new proposals — the semantic layer may already cover this question,
              or the pre-check rejected conflicting entries.
            </div>
          )}

          {/* Concepts */}
          {concepts.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Concepts
                </span>
                <span className="font-mono text-[9px] text-muted-foreground/60">
                  {selectedConceptCount}/{concepts.length} selected
                </span>
              </div>
              <Card className="gap-0 p-0 overflow-hidden">
                <div className="flex flex-col divide-y divide-border">
                  {concepts.map((c) => (
                    <div key={c.local_concept_id} className="px-3 py-2">
                      <ConceptItem
                        concept={c}
                        checked={selected.has(c.local_concept_id)}
                        onToggle={toggle}
                      />
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}

          {/* Relations */}
          {relations.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  Causal relations
                </span>
                <span className="font-mono text-[9px] text-muted-foreground/60">
                  {selectedRelationCount}/{relations.length} selected
                </span>
              </div>
              <Card className="gap-0 p-0 overflow-hidden">
                <div className="flex flex-col divide-y divide-border">
                  {relations.map((r) => (
                    <div key={r.relation_id} className="px-3 py-2">
                      <RelationItem
                        relation={r}
                        checked={selected.has(r.relation_id)}
                        onToggle={toggle}
                        conceptLabels={conceptLabels}
                      />
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}

          {/* Bouton appliquer */}
          {totalSelected > 0 && (
            <button
              onClick={applySelected}
              className="flex items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-2 text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Apply {totalSelected} proposal{totalSelected !== 1 ? 's' : ''} →
            </button>
          )}
        </div>
      )}

      {/* ── Application en cours ── */}
      {phase === 'applying' && (
        <div className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
          <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          Writing to the semantic layer…
        </div>
      )}

      {/* ── Succès ── */}
      {phase === 'done' && (
        <div className="flex flex-col gap-4">
          <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3.5">
            <div className="text-[12px] font-semibold text-green-800">
              Semantic layer updated
              {result?.new_version ? ` → v${result.new_version}` : ''}
            </div>
            {(result?.concepts_added != null || result?.relations_added != null) && (
              <div className="mt-1 text-[11px] text-green-700">
                {result.concepts_added != null && `+${result.concepts_added} concept${result.concepts_added !== 1 ? 's' : ''}`}
                {result.concepts_added != null && result.relations_added != null && ' · '}
                {result.relations_added != null && `+${result.relations_added} relation${result.relations_added !== 1 ? 's' : ''}`}
              </div>
            )}
            <div className="mt-1.5 text-[10.5px] text-green-600">
              Taxonomic index reloaded — the new entries are available immediately.
            </div>
          </div>
          <button
            onClick={() => {
              setPhase('idle')
              setQuestion('')
              setArtifact(null)
              setSelected(new Set())
              setResult(null)
              setProgress(0)
            }}
            className="rounded-md border border-border px-4 py-2 text-[12.5px] font-medium text-foreground transition-colors hover:bg-muted/50"
          >
            New analysis →
          </button>
        </div>
      )}

      {/* ── Erreur ── */}
      {phase === 'error' && (
        <div className="flex flex-col gap-3">
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-[11.5px] text-destructive">
            {error || 'An unexpected error occurred.'}
          </div>
          <button
            onClick={() => { setPhase('idle'); setError('') }}
            className="rounded-md border border-border px-4 py-2 text-[12.5px] font-medium text-foreground transition-colors hover:bg-muted/50"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  )
}
