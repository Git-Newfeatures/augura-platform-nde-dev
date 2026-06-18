/**
 * Taxonomy Loader — reads from Supabase semantic schema (via semantic-store).
 *
 * Exposes three distinct data sets:
 *   1. Concept index — all active taxonomy concepts (L0, L1, L2)
 *   2. Unit profiles — per-concept allowed units with UCUM codes and aliases
 *   3. Conversion rules — governed unit transformation equations
 */
import { normalize, charNgrams } from './lexical-normalizer.js'
import { getDecimalScaleFactor, parseScalableUnit } from './unit-scaling.js'
import { groupRows, parseBoolean, parseNumber } from '../utils/csv-parser.js'
import {
  getStoredConcepts,
  getStoredSynonyms,
  getStoredStandardCodes,
  getStoredTherapeuticAreas,
  getStoredTaxonomyRelationships,
  getStoredDqValidValues,
  getStoredMeasurementUnits,
  getStoredUnitConversions,
} from '../lib/semantic-store.js'

let _index       = null
let _synLookup   = null
let _unitProfiles = null
let _conversions  = null

// ── Concept index ─────────────────────────────────────────────────────────────

function buildConceptsFromStore() {
  const concepts          = getStoredConcepts()
  const synonyms          = groupRows(getStoredSynonyms(),                 'local_concept_id')
  const standardCodes     = groupRows(getStoredStandardCodes(),            'local_concept_id')
  const therapeuticAreas  = groupRows(getStoredTherapeuticAreas(),         'local_concept_id')
  const relationships     = groupRows(getStoredTaxonomyRelationships(),    'from_concept_id')
  const validValues       = groupRows(getStoredDqValidValues(),            'local_concept_id')

  return concepts
    .filter(row => parseBoolean(row.active))
    .map(row => {
      const valueMin   = parseNumber(row.value_min)
      const valueMax   = parseNumber(row.value_max)
      const valueRange = valueMin !== null && valueMax !== null ? [valueMin, valueMax] : undefined

      const codeEntries  = standardCodes.get(row.local_concept_id) || []
      const standard_codes = Object.fromEntries(
        codeEntries
          .filter(code => code.vocabulary_id && code.concept_code)
          .map(code => [code.vocabulary_id.toLowerCase(), code.concept_code])
      )

      const relatedLayer1 = (relationships.get(row.local_concept_id) || [])
        .filter(rel => rel.relationship_type === 'related_layer1')
        .map(rel => rel.to_concept_id)
        .filter(Boolean)

      return {
        id:                        row.local_concept_id,
        label:                     row.concept_name,
        review_section:            row.review_section,
        domain:                    row.augura_domain,
        layer:                     Number(row.layer),
        omop_domain:               row.omop_domain_id,
        omop_target_table:         row.omop_target_table,
        omop_target_concept_field: row.omop_target_concept_field,
        namespace:                 row.namespace || undefined,
        unit:                      row.unit_source_value || undefined,
        value_min:                 valueMin,
        value_max:                 valueMax,
        value_range:               valueRange,
        value_type:                row.value_type || undefined,
        design_rationale:          row.design_rationale || undefined,
        review_status:             row.review_status || undefined,
        version:                   row.version || undefined,
        active:                    parseBoolean(row.active),
        standard_codes,
        synonyms:           (synonyms.get(row.local_concept_id) || []).map(s => s.synonym).filter(Boolean),
        therapeutic_areas:  (therapeuticAreas.get(row.local_concept_id) || []).map(a => a.therapeutic_area).filter(Boolean),
        related_layer1:     relatedLayer1,
        canonical_unit:     row.canonical_unit || undefined,
        temporality:        row.temporality || undefined,
        dq_column_role:     row.dq_column_role || undefined,
        // Standards crosswalks (authoritative for Layer 0 structural concepts)
        fhir_crosswalk:     row.fhir_crosswalk || undefined,
        sdtm_crosswalk:     row.sdtm_crosswalk || undefined,
        // Governance status fields — required by semantic architecture §3 and §3.3
        unit_coverage_status:  row.unit_coverage_status || undefined,
        range_support_status:  row.range_support_status || undefined,
        valid_values:       (validValues.get(row.local_concept_id) || []).map(v => ({
          value:         v.value,
          label:         v.label,
          coding_system: v.coding_system,
        })),
      }
    })
}

/**
 * Clear all derived caches so the next read rebuilds from the updated semantic store.
 * Must be called after resetSemanticStore() + initSemanticStore() to pick up new concepts.
 */
export function resetTaxonomyLoader() {
  _index        = null
  _synLookup    = null
  _unitProfiles = null
  _conversions  = null
}

export function getTaxonomyIndex() {
  if (_index) return _index
  const all = buildConceptsFromStore()
  _index = all.map(c => {
    const normLabel    = normalize(c.label)
    const normSynonyms = (c.synonyms || []).map(s => normalize(s)).filter(Boolean)
    const labelNgrams  = charNgrams(normLabel)
    return { ...c, _normLabel: normLabel, _normSynonyms: normSynonyms, _labelNgrams: labelNgrams, _allNormTokens: [normLabel, ...normSynonyms] }
  })
  return _index
}

export function getConceptById(id) {
  return getTaxonomyIndex().find(c => c.id === id) || null
}

export function getConceptsByDomain(domain) {
  return getTaxonomyIndex().filter(c => c.domain === domain)
}

export function buildSynonymLookup() {
  const map = new Map()
  for (const c of getTaxonomyIndex()) {
    for (const syn of c._allNormTokens) {
      if (!syn) continue
      if (!map.has(syn)) map.set(syn, [])
      map.get(syn).push(c.id)
    }
  }
  return map
}

export function getSynonymLookup() {
  if (!_synLookup) _synLookup = buildSynonymLookup()
  return _synLookup
}

// ── Unit profiles ─────────────────────────────────────────────────────────────

/**
 * Returns a map from concept_id → array of unit profile objects.
 * Each profile describes one allowed unit for that concept.
 */
export function getUnitProfiles() {
  if (_unitProfiles) return _unitProfiles
  const rows = getStoredMeasurementUnits()
  _unitProfiles = new Map()
  for (const row of rows) {
    const cid = row.concept_id
    if (!_unitProfiles.has(cid)) _unitProfiles.set(cid, [])
    _unitProfiles.get(cid).push({
      unit_id:        row.unit_id,
      ucum_code:      row.ucum_code,
      display_label:  row.display_label,
      source_aliases: (row.source_aliases || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean),
      status:         row.status,         // preferred | allowed | deprecated | display_only
      quantity_kind:  row.quantity_kind,
      is_preferred:   parseBoolean(row.is_preferred),
      review_status:  row.review_status,
      version:        row.version,
    })
  }
  return _unitProfiles
}

/** All allowed unit profiles for a given concept_id, or []. */
export function getUnitProfilesForConcept(conceptId) {
  return getUnitProfiles().get(conceptId) || []
}

/** The preferred unit profile for a concept_id, or null. */
export function getPreferredUnit(conceptId) {
  return getUnitProfilesForConcept(conceptId).find(u => u.is_preferred && u.status === 'preferred') || null
}

/**
 * Normalise a raw unit string to a UCUM code for a given concept.
 * Returns { ucum_code, profile } if matched, null if not recognized.
 */
export function normalizeUnit(rawUnit, conceptId) {
  if (!rawUnit) return null
  const normalized = rawUnit.trim().toLowerCase()
  for (const profile of getUnitProfilesForConcept(conceptId)) {
    if (profile.ucum_code.toLowerCase() === normalized) {
      return { ucum_code: profile.ucum_code, profile, match_type: 'explicit', scale_factor: 1 }
    }
    if (profile.display_label.toLowerCase() === normalized) {
      return { ucum_code: profile.ucum_code, profile, match_type: 'explicit', scale_factor: 1 }
    }
    if (profile.source_aliases.includes(normalized)) {
      return { ucum_code: profile.ucum_code, profile, match_type: 'explicit', scale_factor: 1 }
    }
  }

  const parsedSource = parseScalableUnit(rawUnit)
  if (!parsedSource) return null

  const eligibleProfiles = getUnitProfilesForConcept(conceptId)
    .filter(profile => profile.status !== 'deprecated' && profile.status !== 'display_only')
    .sort((left, right) => Number(right.is_preferred) - Number(left.is_preferred))

  for (const profile of eligibleProfiles) {
    const scaleFactor = getDecimalScaleFactor(rawUnit, profile.ucum_code)
    if (scaleFactor != null) {
      return {
        ucum_code: parsedSource.normalized,
        profile,
        match_type: 'decimal_scaled',
        scale_factor: scaleFactor,
        scaled_to_ucum: profile.ucum_code,
      }
    }
  }
  return null
}

// ── Conversion rules ──────────────────────────────────────────────────────────

/**
 * Returns all governed conversion rules.
 * Keyed by (from_ucum + '→' + to_ucum + '|' + concept_id) for fast lookup.
 */
export function getConversionRules() {
  if (_conversions) return _conversions
  const rows = getStoredUnitConversions()
  _conversions = new Map()
  for (const row of rows) {
    // Index by both directions if bidirectional
    const fwd = `${row.from_ucum}→${row.to_ucum}|${row.applicable_concept_id}`
    if (!_conversions.has(fwd)) {
      _conversions.set(fwd, {
        conversion_id:        row.conversion_id,
        from_ucum:            row.from_ucum,
        to_ucum:              row.to_ucum,
        quantity_kind:        row.quantity_kind,
        applicable_concept_id: row.applicable_concept_id,
        conversion_type:      row.conversion_type,
        equation_id:          row.equation_id,
        scale_factor:         parseNumber(row.scale_factor),
        offset:               parseNumber(row.offset),
        precision:            parseNumber(row.precision),
        bidirectional:        parseBoolean(row.bidirectional),
        provenance:           row.provenance,
        review_status:        row.review_status,
      })
    }
  }
  return _conversions
}

/**
 * Find a conversion rule for a (from_ucum, to_ucum, conceptId) triple.
 * Falls back to concept-independent rules when concept-specific one is absent.
 */
export function findConversion(fromUcum, toUcum, conceptId) {
  const rules = getConversionRules()
  return rules.get(`${fromUcum}→${toUcum}|${conceptId}`)
      || rules.get(`${fromUcum}→${toUcum}|`)
      || null
}
