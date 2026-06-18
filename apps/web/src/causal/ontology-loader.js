/**
 * Loads the reviewed causal relation graph, evidence, and qualifiers.
 * Reads from Supabase semantic schema (via semantic-store).
 */

import { groupRows, parseBoolean } from '../utils/csv-parser.js'
import {
  getStoredOntologyRelations,
  getStoredCausalPredicates,
  getStoredOntologyEvidence,
  getStoredOntologyQualifiers,
} from '../lib/semantic-store.js'

let _ontology = null

function buildIndexes(rels) {
  const bySubject = new Map()
  const byObject  = new Map()
  const byId      = new Map()
  for (const rel of rels) {
    byId.set(rel.id, rel)
    if (!bySubject.has(rel.subject_concept_id)) bySubject.set(rel.subject_concept_id, [])
    bySubject.get(rel.subject_concept_id).push(rel)
    if (!byObject.has(rel.object_concept_id)) byObject.set(rel.object_concept_id, [])
    byObject.get(rel.object_concept_id).push(rel)
  }
  return { bySubject, byObject, byId }
}

function buildOntology() {
  const relations    = getStoredOntologyRelations()
  const causalPreds  = getStoredCausalPredicates()
  const evidence     = groupRows(getStoredOntologyEvidence(),   'relation_id')
  const qualifiers   = groupRows(getStoredOntologyQualifiers(), 'relation_id')

  const predicateMap = Object.fromEntries(
    causalPreds.map(predicate => [predicate.predicate_id, predicate]),
  )

  const causalRelations = relations
    .filter(row => parseBoolean(row.active))
    .map(row => {
      const predMeta = predicateMap[row.predicate] || null
      return {
        id:                 row.relation_id,
        subject_concept_id: row.subject_concept_id,
        predicate:          row.predicate,
        predicate_meta:     predMeta,
        object_concept_id:  row.object_concept_id,
        polarity:           row.polarity,
        default_strength:   row.default_strength,
        default_temporal_lag: row.default_temporal_lag,
        mechanism_summary:  row.mechanism_summary,
        review_status:      row.review_status,
        version:            row.version,
        evidence: (evidence.get(row.relation_id) || []).map(e => ({
          id:          e.evidence_id,
          source_type: e.source_type,
          citation:    e.citation_or_url,
          summary:     e.evidence_summary,
          population:  e.population_notes,
          strength:    e.evidence_strength,
        })),
        qualifiers: (qualifiers.get(row.relation_id) || []).map(q => ({
          id:                q.qualifier_id,
          type:              q.qualifier_type,
          value:             q.qualifier_value,
          effect:            q.qualifier_effect,
          is_hard_constraint: parseBoolean(q.is_hard_constraint),
          notes:             q.notes,
        })),
      }
    })

  return {
    relations: causalRelations,
    ...buildIndexes(causalRelations),
    predicates: predicateMap,
  }
}

export function getCausalOntology() {
  if (!_ontology) _ontology = buildOntology()
  return _ontology
}

export function resetOntologyLoader() {
  _ontology = null
}

export function getCausalSubgraph(conceptIds, { hops = 1 } = {}) {
  return _subgraph(getCausalOntology(), conceptIds, hops)
}

function _subgraph(idx, conceptIds, hops) {
  const seedSet = new Set(conceptIds)
  const seen    = new Set()
  const result  = []

  function collect(ids) {
    const next = new Set()
    for (const id of ids) {
      for (const rel of (idx.bySubject?.get(id) || [])) {
        if (!seen.has(rel.id)) { seen.add(rel.id); result.push(rel); next.add(rel.object_concept_id) }
      }
      for (const rel of (idx.byObject?.get(id) || [])) {
        if (!seen.has(rel.id)) { seen.add(rel.id); result.push(rel); next.add(rel.subject_concept_id) }
      }
    }
    return next
  }

  let frontier = seedSet
  for (let h = 0; h <= hops; h++) {
    const next = collect(frontier)
    if (h < hops) frontier = next
  }
  return result
}
