/**
 * Data-quality Loader — governance rules (read-only).
 *
 * Reads the governed DQ catalogs from the semantic store and joins each
 * constraint to the predicate it binds. Mirrors the taxonomy/ontology loaders:
 * synchronous reads, module-level cache, reset hook.
 *
 * The north-star drill-down spine for DQ is: constraint → predicate · scope ·
 * valid values. Constraints are the primary entity; predicates, table
 * archetypes and valid value sets are reached through (or alongside) them.
 *
 * Exposes:
 *   - constraints       — dq_constraints, each joined to its bound predicate
 *   - predicatesById    — Map keyed by predicate_id (dq_predicates)
 *   - tableArchetypes   — table_archetypes (shapes/roles a table can take)
 *   - validValuesByConcept — taxonomy_dq_valid_values grouped by concept
 */
import { groupRows } from '../utils/csv-parser.js'
import {
  getStoredDqConstraints,
  getStoredDqPredicates,
  getStoredTableArchetypes,
  getStoredDqValidValues,
} from '../lib/semantic-store.js'

let _dq = null

function buildDq() {
  // dq_constraints.operator references dq_predicates.predicate_id.
  const predicates = getStoredDqPredicates().map(row => ({
    id:            row.predicate_id,
    label:         row.label,
    description:   row.description,
    direction_type: row.direction_type,
    review_status: row.review_status,
    version:       row.version,
  }))
  const predicatesById = new Map(predicates.map(p => [p.id, p]))

  const constraints = getStoredDqConstraints().map(row => ({
    id:                      row.constraint_id,
    target_scope:            row.target_scope,
    subject_concept_or_role: row.subject_concept_or_role,
    operator:                row.operator,
    predicate:               predicatesById.get(row.operator) || null,
    object_concept_or_role:  row.object_concept_or_role || undefined,
    parameters:              row.parameters || undefined,
    applies_when:            row.applies_when,
    severity:                row.severity,
    implementation_id:       row.implementation_id,
    evidence_source:         row.evidence_source,
    status:                  row.status,
    version:                 row.version,
  }))

  const tableArchetypes = getStoredTableArchetypes().map(row => ({
    id:                   row.archetype_id,
    name:                 row.archetype_name,
    key_selectors:        String(row.key_selectors || '').split('|').map(s => s.trim()).filter(Boolean),
    semantic_score:       row.semantic_score,
    is_surrogate:         row.is_surrogate,
    description_template: row.description_template,
    review_status:        row.review_status,
    version:              row.version,
    active:               row.active,
  }))

  const validValuesByConcept = groupRows(getStoredDqValidValues(), 'local_concept_id')

  return { constraints, predicates, predicatesById, tableArchetypes, validValuesByConcept }
}

export function getDqGovernance() {
  if (!_dq) _dq = buildDq()
  return _dq
}

export function resetDqLoader() {
  _dq = null
}
