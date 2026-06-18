/**
 * Confidence Scorer
 * Produces meaningful, evidence-based confidence scores for semantic mappings.
 * Scores are NOT arbitrary — each dimension is computed from observable evidence.
 */

// ── Score dimensions ──────────────────────────────────────────────────────────

/**
 * D1: Semantic similarity strength (from concept-matcher score, 0–1)
 */
function semanticSimilarity(matchScore) {
  return matchScore
}

/**
 * D2: Standard code availability
 * Reward mappings that land on concepts with well-known standard codes.
 */
function standardCodeBonus(concept) {
  const codes = concept.standard_codes || {}
  const n = Object.values(codes).filter(v => v).length
  if (n >= 2) return 1.0
  if (n === 1) return 0.85
  return 0.60
}

/**
 * D3: Data type consistency
 * Penalize type mismatches (numeric column mapped to categorical concept, etc.)
 */
function dataTypeConsistency(profile, concept) {
  const { isNumeric, isCategorical, isDate } = profile
  const domain = concept.domain

  // Date columns should map to temporal or encounter
  if (isDate && !['encounter','temporal','study_construct'].includes(domain)) return 0.5
  if (isDate && ['encounter','temporal','study_construct'].includes(domain)) return 1.0

  // Numeric columns should map to measurement, device_telemetry, digital_engagement, biomarker
  const numericDomains = ['measurement','device_telemetry','digital_engagement','biomarker','behavioral','statistical','temporal']
  if (isNumeric && numericDomains.includes(domain)) return 1.0
  if (isNumeric && ['condition','drug','procedure'].includes(domain)) return 0.45

  // Categorical columns map well to condition, drug, demographic, causal_role, study_construct
  const catDomains = ['condition','drug','demographic','causal_role','study_construct','procedure']
  if (isCategorical && catDomains.includes(domain)) return 1.0
  if (isCategorical && domain === 'measurement') return 0.70

  return 0.80 // neutral
}

/**
 * D4: Value range plausibility
 * Check if observed value range is compatible with concept's expected range.
 */
function valueRangePlausibility(numSummary, concept) {
  if (!numSummary || !concept.value_range) return 0.85 // no info → neutral
  const [vmin, vmax] = concept.value_range
  const { min, max } = numSummary
  const range = vmax - vmin
  const tolerance = range * 0.25

  if (min >= vmin - tolerance && max <= vmax + tolerance) return 1.0
  if (min >= vmin - tolerance * 2 && max <= vmax + tolerance * 2) return 0.75
  if (max < vmin || min > vmax + tolerance * 3) return 0.20 // implausible
  return 0.55
}

/**
 * D5: Missing data impact
 * High missingness reduces our certainty about the mapping.
 */
function missingDataPenalty(missingRate) {
  if (missingRate > 0.60) return 0.60
  if (missingRate > 0.40) return 0.75
  if (missingRate > 0.25) return 0.85
  return 1.0
}

/**
 * D6: Ambiguity penalty
 * If multiple concepts scored similarly, reduce confidence.
 */
function ambiguityPenalty(topCandidates) {
  if (topCandidates.length < 2) return 1.0
  const best = topCandidates[0].score
  const second = topCandidates[1].score
  const gap = best - second
  if (gap < 0.05) return 0.60  // very ambiguous
  if (gap < 0.10) return 0.75
  if (gap < 0.20) return 0.88
  return 1.0
}

/**
 * D7: Method quality bonus
 */
function methodQualityBonus(method) {
  switch (method) {
    case 'exact_synonym': return 1.0
    case 'fuzzy_label':   return 0.92
    case 'fuzzy_synonym': return 0.85
    case 'heuristic':     return 0.70
    case 'no_match':      return 0.30
    default:              return 0.70
  }
}

// ── Dimension weights ─────────────────────────────────────────────────────────
const WEIGHTS = {
  semantic:    0.30,
  methodQual:  0.20,
  ambiguity:   0.18,
  dataType:    0.14,
  valueRange:  0.10,
  stdCode:     0.05,
  missingData: 0.03,
}

/**
 * Compute a composite confidence score for a mapping.
 *
 * @param {Object} bestCandidate - Top match from concept-matcher
 * @param {Object} profile - Column profile (isNumeric, numSummary, missingRate, etc.)
 * @param {Array}  topCandidates - All top-N candidates (for ambiguity)
 * @param {Object} concept - Full concept object from taxonomy
 * @returns {{ score: number, breakdown: Object, label: string }}
 */
export function computeConfidence(bestCandidate, profile, topCandidates, concept) {
  if (!bestCandidate || bestCandidate.method === 'no_match' || bestCandidate.score < 0.15) {
    return {
      score: 0.0,
      label: 'Unmapped',
      breakdown: {},
      notes: ['No adequate concept match found'],
    }
  }

  const d = {
    semantic:    semanticSimilarity(bestCandidate.score),
    methodQual:  methodQualityBonus(bestCandidate.method),
    ambiguity:   ambiguityPenalty(topCandidates),
    dataType:    dataTypeConsistency(profile, concept),
    valueRange:  valueRangePlausibility(profile.numSummary, concept),
    stdCode:     standardCodeBonus(concept),
    missingData: missingDataPenalty(profile.missing || 0),
  }

  let weighted = 0
  for (const [k, v] of Object.entries(d)) {
    weighted += v * WEIGHTS[k]
  }

  const score = Math.min(1, Math.max(0, weighted))

  return {
    score: +score.toFixed(3),
    label: confidenceLabel(score),
    breakdown: Object.fromEntries(Object.entries(d).map(([k, v]) => [k, +v.toFixed(3)])),
    notes: buildNotes(d, profile, bestCandidate),
  }
}

function confidenceLabel(score) {
  if (score >= 0.80) return 'High'
  if (score >= 0.60) return 'Medium'
  if (score >= 0.40) return 'Low'
  if (score > 0.0)   return 'Very Low'
  return 'Unmapped'
}

function buildNotes(d, profile, best) {
  const notes = []
  if (d.ambiguity < 0.70) notes.push('Multiple similar concepts — mapping is ambiguous')
  if (d.dataType < 0.60)  notes.push(`Data type mismatch: column appears ${profile.isNumeric ? 'numeric' : profile.isCategorical ? 'categorical' : 'unknown'} but concept domain suggests otherwise`)
  if (d.valueRange < 0.50) notes.push(`Value range outside expected bounds`)
  if (d.missingData < 0.80) notes.push(`High missingness (${((profile.missing || 0) * 100).toFixed(0)}%) reduces reliability`)
  if (d.stdCode < 0.70)   notes.push('No standard vocabulary code — Augura extension concept')
  if (best.method === 'heuristic') notes.push('Mapping based on heuristic inference — verify manually')
  if (best.method === 'exact_synonym') notes.push('Exact synonym match')
  return notes
}

/**
 * Aggregate column-level confidences into a dataset-level mapping score.
 */
export function datasetMappingScore(columnMappings) {
  const mapped = columnMappings.filter(m => m.confidence.score > 0)
  const total = columnMappings.length
  if (!total) return { mappingRate: 0, avgConfidence: 0, highConfidenceRate: 0 }

  const mappingRate = mapped.length / total
  const avgConfidence = mapped.reduce((s, m) => s + m.confidence.score, 0) / (mapped.length || 1)
  const highConf = mapped.filter(m => m.confidence.score >= 0.80).length
  const highConfidenceRate = mapped.length ? highConf / mapped.length : 0

  return {
    mappingRate: +mappingRate.toFixed(3),
    avgConfidence: +avgConfidence.toFixed(3),
    highConfidenceRate: +highConfidenceRate.toFixed(3),
    mappedCount: mapped.length,
    totalCount: total,
    unmappedCount: total - mapped.length,
  }
}
