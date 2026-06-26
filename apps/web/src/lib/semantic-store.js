/**
 * Semantic Store
 *
 * Fetches the full Semantic Layer once per session and holds it in
 * module-level memory. Call `initSemanticStore()` early in the app lifecycle
 * (before any component that uses the taxonomy, ontology, or DQ loaders
 * renders). All downstream loaders stay synchronous — they read from this cache.
 *
 * Migration note (from data-intake-nde):
 *   The legacy SPA read the 14 semantic tables straight from Supabase via the
 *   `semantic_read_all` RPC. In this monorepo the front never talks to Postgres
 *   directly — every read crosses the backend (see src/api.js). So the bundle
 *   now arrives through `apiJson('/semantic/bundle')`, tenant-scoped by RLS.
 *
 * Backend contract — `GET /semantic/bundle` returns one JSON object whose keys
 * are the 18 tables below, each an array of rows: taxonomy_concepts,
 * taxonomy_synonyms, taxonomy_standard_codes, taxonomy_therapeutic_areas,
 * taxonomy_relationships, taxonomy_dq_valid_values, taxonomy_measurement_units,
 * unit_conversions, causal_predicates, ontology_relations,
 * ontology_relation_evidence, ontology_relation_qualifiers, dq_constraints,
 * table_archetypes, dimension_kinds, affix_archetypes, affix_archetype_values,
 * affix_archetype_aliases.
 *
 * Fallback: if the fetch fails (no network, backend down, not yet seeded) the
 * store stays null and the loaders throw a clear error rather than silently
 * returning empty data.
 */

import { apiJson } from '@/api'

let _data        = null
let _initPromise = null
let _fetchedAt   = 0

// Re-fetch if the cached copy is older than this. Covers changes applied from
// another tab, the enrichment pipeline, or the CLI between page loads.
const STORE_TTL_MS = 10 * 60 * 1000  // 10 minutes

/**
 * Load the full Semantic Layer from the backend. Idempotent — safe to call
 * repeatedly. Re-fetches automatically when the cached copy is older than
 * STORE_TTL_MS.
 */
export async function initSemanticStore() {
  const now = Date.now()
  if (_data && (now - _fetchedAt) < STORE_TTL_MS) return   // still fresh
  if (_initPromise) return _initPromise                     // fetch already in flight

  _data        = null   // discard stale copy before re-fetching
  _initPromise = (async () => {
    let data
    try {
      data = await apiJson('/semantic/bundle')
    } catch (err) {
      _initPromise = null
      throw new Error(`Semantic store: ${err?.message ?? err}`)
    }
    if (!data || !data.taxonomy_concepts) {
      _initPromise = null
      throw new Error('Semantic store: /semantic/bundle returned empty data')
    }
    _data      = data
    _fetchedAt = Date.now()
  })()

  return _initPromise
}

export function isSemanticStoreReady() {
  return _data !== null
}

function get(table) {
  if (!_data) throw new Error(`Semantic store not ready — call initSemanticStore() first (table: ${table})`)
  return _data[table] ?? []
}

export const getStoredConcepts              = () => get('taxonomy_concepts')
export const getStoredSynonyms              = () => get('taxonomy_synonyms')
export const getStoredStandardCodes         = () => get('taxonomy_standard_codes')
export const getStoredTherapeuticAreas      = () => get('taxonomy_therapeutic_areas')
export const getStoredTaxonomyRelationships = () => get('taxonomy_relationships')
export const getStoredDqValidValues         = () => get('taxonomy_dq_valid_values')
export const getStoredMeasurementUnits      = () => get('taxonomy_measurement_units')
export const getStoredUnitConversions       = () => get('unit_conversions')
export const getStoredOntologyRelations     = () => get('ontology_relations')
export const getStoredCausalPredicates      = () => get('causal_predicates')
export const getStoredOntologyEvidence      = () => get('ontology_relation_evidence')
export const getStoredOntologyQualifiers    = () => get('ontology_relation_qualifiers')
export const getStoredDqConstraints         = () => get('dq_constraints')
export const getStoredTableArchetypes       = () => get('table_archetypes')
// Dimension grammar / affix archetypes (A1).
export const getStoredDimensionKinds        = () => get('dimension_kinds')
export const getStoredAffixArchetypes       = () => get('affix_archetypes')
export const getStoredAffixArchetypeValues  = () => get('affix_archetype_values')
export const getStoredAffixArchetypeAliases = () => get('affix_archetype_aliases')

/**
 * Clear the in-memory cache so the next initSemanticStore() call re-fetches.
 * Used after on-the-fly semantic enrichment to pick up new concepts and
 * relations without a full page reload.
 */
export function resetSemanticStore() {
  _data        = null
  _initPromise = null
  _fetchedAt   = 0   // force immediate re-fetch on next initSemanticStore call
}
