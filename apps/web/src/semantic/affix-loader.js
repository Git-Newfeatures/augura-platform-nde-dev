/**
 * Affix Loader — dimension grammar / affix archetypes (read-only).
 *
 * Reads the governed affix catalogs from the semantic store and joins each
 * archetype to its canonical values and token aliases. Mirrors the
 * taxonomy/ontology loaders: synchronous reads, module-level cache, reset hook.
 *
 * Exposes:
 *   - dimensionKinds       — the structural families (dimension_kinds)
 *   - dimensionKindsById   — Map keyed by dimension_kind_id
 *   - archetypes           — affix_archetypes, each with { values, aliases }
 */
import { groupRows, parseBoolean, parseNumber } from '../utils/csv-parser.js'
import {
  getStoredDimensionKinds,
  getStoredAffixArchetypes,
  getStoredAffixArchetypeValues,
  getStoredAffixArchetypeAliases,
} from '../lib/semantic-store.js'

let _grammar = null

function buildGrammar() {
  const kinds    = getStoredDimensionKinds()
  const values   = groupRows(getStoredAffixArchetypeValues(),  'affix_archetype_id')
  const aliases  = groupRows(getStoredAffixArchetypeAliases(), 'affix_archetype_id')

  const dimensionKinds = kinds.map(row => ({
    id:                    row.dimension_kind_id,
    label:                 row.label,
    description:           row.description,
    value_model:           row.value_model,
    default_comparability: row.default_comparability,
    structural_role:       row.structural_role || undefined,
    review_status:         row.review_status,
    version:               row.version,
    active:                parseBoolean(row.active),
  }))
  const dimensionKindsById = new Map(dimensionKinds.map(k => [k.id, k]))

  const archetypes = getStoredAffixArchetypes().map(row => {
    const id   = row.affix_archetype_id
    const kind = dimensionKindsById.get(row.dimension_kind_id) || null
    return {
      id,
      name:                    row.archetype_name,
      dimension_kind_id:       row.dimension_kind_id,
      dimension_kind_label:    kind ? kind.label : row.dimension_kind_id,
      position:                row.position,
      separator_style:         row.separator_style || undefined,
      value_model:             row.value_model,
      comparability:           row.comparability,
      anchor_concept_id:       row.anchor_concept_id || undefined,
      operator:                row.operator || undefined,
      extraction_rule:         row.extraction_rule || undefined,
      requires_residual_maps:  parseBoolean(row.requires_residual_maps),
      requires_sibling_family: parseBoolean(row.requires_sibling_family),
      evidence_weight:         parseNumber(row.evidence_weight),
      confidence_threshold:    parseNumber(row.confidence_threshold),
      review_status:           row.review_status,
      version:                 row.version,
      active:                  parseBoolean(row.active),
      values: (values.get(id) || []).map(v => ({
        canonical_value: v.canonical_value,
        label:           v.label,
        review_status:   v.review_status,
      })),
      aliases: (aliases.get(id) || []).map(a => ({
        token:           a.token,
        canonical_value: a.canonical_value || undefined,
        source:          a.source,
        review_status:   a.review_status,
      })),
    }
  })

  return { dimensionKinds, dimensionKindsById, archetypes }
}

export function getAffixGrammar() {
  if (!_grammar) _grammar = buildGrammar()
  return _grammar
}

export function resetAffixLoader() {
  _grammar = null
}
