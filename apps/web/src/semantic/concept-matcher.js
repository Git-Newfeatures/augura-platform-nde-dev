/**
 * Concept Matcher
 * Matches a raw column profile (name + data type + samples) to taxonomy concepts.
 * Uses a hybrid pipeline: exact synonym → fuzzy string → heuristic → domain.
 */

import {
  normalize, stringSimilarity, charNgrams, ngramSimilarity,
  isNumericColumn, isCategoricalColumn, isDateColumn,
  numericSummary, missingRate,
} from './lexical-normalizer.js'
import { getTaxonomyIndex, getSynonymLookup, getConceptById } from './taxonomy-loader.js'

// ── Match result structure ────────────────────────────────────────────────────
export function makeCandidateResult(concept, score, method, evidence = []) {
  return {
    concept_id: concept.id,
    concept_label: concept.label,
    concept_domain: concept.domain,
    concept_layer: concept.layer,
    standard_codes: concept.standard_codes || {},
    score,           // 0–1 raw match score
    method,          // 'exact_synonym' | 'fuzzy_label' | 'fuzzy_synonym' | 'heuristic' | 'no_match'
    evidence,        // list of human-readable strings explaining the match
  }
}

// ── Unit and value range heuristics ──────────────────────────────────────────
const UNIT_HINTS = [
  { patterns: ['%', 'pct', 'percent'], domains: ['measurement','device_telemetry','digital_engagement'] },
  { patterns: ['mmhg', 'mm hg', 'blood pressure'], domains: ['measurement'] },
  { patterns: ['mg', 'dl', 'mgdl'], domains: ['measurement'] },
  { patterns: ['mmol'], domains: ['measurement'] },
  { patterns: ['kg', 'lbs', 'pounds'], domains: ['measurement'] },
  { patterns: ['cm', 'meter', 'inches'], domains: ['measurement'] },
  { patterns: ['bpm', 'beats'], domains: ['measurement'] },
  { patterns: ['hours', 'hrs', 'hr'], domains: ['device_telemetry','measurement'] },
  { patterns: ['units', 'iu'], domains: ['drug','device_telemetry'] },
  { patterns: ['count', 'cnt', 'num', 'number'], domains: ['measurement','device_telemetry','digital_engagement'] },
]

// ── Column name patterns that map directly to domains ─────────────────────────
const DOMAIN_PATTERN_MAP = [
  { regex: /\b(app|session|coaching|push|notification|engagement|digital|feature)\b/i, domain: 'digital_engagement' },
  { regex: /\b(cgm|sensor|glucose|pump|bolus|basal|pen|injection)\b/i, domain: 'device_telemetry' },
  { regex: /\b(cpap|apap|bipap|mask|leak|pressure|ahi)\b/i, domain: 'device_telemetry' },
  { regex: /\b(alert|device_alert|rpm|remote|monitor)\b/i, domain: 'device_telemetry' },
  { regex: /\b(inhaler|actuation|puff|adherence)\b/i, domain: 'device_telemetry' },
  { regex: /\b(dialysis|ktv|kt.v|bfr|blood.flow)\b/i, domain: 'device_telemetry' },
  { regex: /\b(seizure|eeg|ictal|wearable|detection)\b/i, domain: 'device_telemetry' },
  { regex: /\b(age|sex|gender|race|ethnic|smoke|smoking)\b/i, domain: 'demographic' },
  { regex: /\b(icd|diagnosis|dx|cpt|ndc|code)\b/i, domain: 'condition' },
  { regex: /\b(drug|medication|rx|dose|inhaler|insulin)\b/i, domain: 'drug' },
  { regex: /\b(hospitali|admission|ed.visit|readmit)\b/i, domain: 'encounter' },
  { regex: /\b(visit|encounter|site|center)\b/i, domain: 'encounter' },
  { regex: /\b(date|time|enroll|start|end|duration)\b/i, domain: 'encounter' },
]

/**
 * Guess the likely domain from a raw column name using pattern matching.
 */
function guessDomain(rawName) {
  for (const { regex, domain } of DOMAIN_PATTERN_MAP) {
    if (regex.test(rawName)) return domain
  }
  return null
}

/**
 * Score a concept against a column profile.
 * Returns a score 0–1 and the method used.
 */
function scoreConceptForColumn(concept, profile) {
  const { normName, domainHint, numSummary, isNumeric } = profile

  // Fast exact synonym lookup
  const synonymLookup = getSynonymLookup()
  if (synonymLookup.has(normName) && synonymLookup.get(normName).includes(concept.id)) {
    return { score: 0.95, method: 'exact_synonym', evidence: [`Exact synonym match: "${normName}"`] }
  }

  // Fuzzy label match
  const labelSim = stringSimilarity(normName, concept._normLabel)
  if (labelSim > 0.85) {
    return {
      score: labelSim * 0.92,
      method: 'fuzzy_label',
      evidence: [`Label similarity ${(labelSim * 100).toFixed(0)}%: "${concept._normLabel}"`],
    }
  }

  // Fuzzy synonym match — check each synonym
  let bestSynSim = 0
  let bestSyn = ''
  for (const syn of concept._normSynonyms) {
    const sim = stringSimilarity(normName, syn)
    if (sim > bestSynSim) { bestSynSim = sim; bestSyn = syn }
  }
  if (bestSynSim > 0.75) {
    return {
      score: bestSynSim * 0.88,
      method: 'fuzzy_synonym',
      evidence: [`Synonym similarity ${(bestSynSim * 100).toFixed(0)}%: "${bestSyn}"`],
    }
  }

  // Domain-weighted boost for partial matches
  if (domainHint && concept.domain === domainHint && (labelSim > 0.5 || bestSynSim > 0.5)) {
    const domainScore = Math.max(labelSim, bestSynSim) * 0.75
    return {
      score: domainScore,
      method: 'heuristic',
      evidence: [`Domain-boosted match (${domainHint}): similarity ${(Math.max(labelSim, bestSynSim) * 100).toFixed(0)}%`],
    }
  }

  // Value range check for measurements
  if (isNumeric && numSummary && concept.value_range && concept.domain === 'measurement') {
    const [vmin, vmax] = concept.value_range
    if (numSummary.min >= vmin - 5 && numSummary.max <= vmax + 20) {
      const partialScore = Math.max(labelSim, bestSynSim)
      if (partialScore > 0.35) {
        return {
          score: partialScore * 0.65,
          method: 'heuristic',
          evidence: [
            `Value range check: observed [${numSummary.min}, ${numSummary.max}] within expected [${vmin}, ${vmax}]`,
            `Partial label similarity: ${(partialScore * 100).toFixed(0)}%`,
          ],
        }
      }
    }
  }

  // Fall-through — low score
  const fallback = Math.max(labelSim, bestSynSim)
  return {
    score: fallback * 0.5,
    method: fallback > 0.3 ? 'heuristic' : 'no_match',
    evidence: fallback > 0.3 ? [`Weak similarity: ${(fallback * 100).toFixed(0)}%`] : [],
  }
}

/**
 * Main entry: match a single column to taxonomy concepts.
 * Returns top-N candidates sorted by score descending.
 */
export function matchColumn(colName, samples = [], topN = 5) {
  const normName = normalize(colName)
  const isNumeric = isNumericColumn(samples)
  const isCategorical = isCategoricalColumn(samples)
  const isDate = isDateColumn(samples)
  const numSummary = isNumeric ? numericSummary(samples) : null
  const domainHint = guessDomain(colName)
  const missing = missingRate(samples)

  const profile = { normName, domainHint, numSummary, samples, isNumeric, isCategorical, isDate, missing }

  const concepts = getTaxonomyIndex()
  const candidates = []

  // First: exact synonym lookup (fast path)
  const synonymLookup = getSynonymLookup()
  const exactMatches = synonymLookup.get(normName) || []

  for (const cid of exactMatches) {
    const concept = getConceptById(cid)
    if (concept) {
      candidates.push(makeCandidateResult(concept, 0.95, 'exact_synonym',
        [`Exact synonym match: "${normName}"`]))
    }
  }

  // If we have exact matches, no need to scan everything
  if (candidates.length === 0) {
    // Fuzzy scan — limit to reasonable candidates using n-gram pre-filter
    const queryNg = charNgrams(normName)
    const prescored = concepts
      .map(concept => {
        const preScore = ngramSimilarity(queryNg, concept._labelNgrams)
        return { concept, preScore }
      })
      .filter(({ preScore }) => preScore > 0.15)
      .sort((a, b) => b.preScore - a.preScore)
      .slice(0, 60) // limit full scoring to top 60 pre-candidates

    for (const { concept } of prescored) {
      const { score, method, evidence } = scoreConceptForColumn(concept, profile)
      if (score > 0.20) {
        candidates.push(makeCandidateResult(concept, score, method, evidence))
      }
    }
  }

  // Deduplicate by concept_id, keep highest score
  const deduped = new Map()
  for (const c of candidates) {
    if (!deduped.has(c.concept_id) || deduped.get(c.concept_id).score < c.score) {
      deduped.set(c.concept_id, c)
    }
  }

  const sorted = [...deduped.values()].sort((a, b) => b.score - a.score)
  return sorted.slice(0, topN)
}

/**
 * Returns the structural dq_column_role for a matched concept, or null.
 * Layer 0 concepts carry authoritative dq_column_role values; this function
 * surfaces them for callers that need a role string without the full concept.
 * The old regex-based classifyColumnRole() has been removed — L0 synonym
 * matching in the standard pipeline now handles all structural role detection.
 */
export function getColumnRole(matchedConcept) {
  return matchedConcept?.dq_column_role ?? null
}
