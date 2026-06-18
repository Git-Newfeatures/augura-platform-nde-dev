/**
 * PICOT/PECO Parser
 * Extracts structured Population, Intervention/Exposure, Comparator, Outcome, Time
 * from a free-text clinical question.
 * Combines rule-based pattern matching with taxonomy concept matching when the
 * semantic store is loaded (isSemanticStoreReady → getTaxonomyIndex).
 */

import { isSemanticStoreReady } from '../lib/semantic-store.js'
import { getTaxonomyIndex, getSynonymLookup } from './taxonomy-loader.js'
import { normalize } from './lexical-normalizer.js'
import { getCausalOntology } from '../causal/ontology-loader.js'

// ── Keyword dictionaries ──────────────────────────────────────────────────────

const POPULATION_KEYWORDS = [
  'patients','subjects','participants','individuals','adults','children','pediatric',
  'elderly','men','women','with','in','among','who','have','having','diagnosed',
]

const INTERVENTION_PATTERNS = [
  // MedTech devices
  /\b(cgm|continuous glucose monitor)\b/i,
  /\b(cpap|apap|bipap|positive airway pressure)\b/i,
  /\b(implantable cardiac monitor|icm)\b/i,
  /\b(smart inhaler|controller medication|ics|inhaled corticosteroid)\b/i,
  /\b(remote.?patient.?monitoring|rpm)\b/i,
  /\b(heart failure|hf).{0,30}\b(monitor|device|alert)\b/i,
  /\b(dialysis|hemodialysis)\b/i,
  /\b(robotic.?tka|robotic.?assisted|conventional.?tka|total knee)\b/i,
  /\b(bariatric surgery|gastric bypass|sleeve gastrectomy)\b/i,
  /\b(seizure detection|wearable)\b/i,
  /\b(app|application|digital.?health|coaching|engagement)\b/i,
  /\b(smart brace|rom feedback)\b/i,
  /\b(electronic pro|symptom monitoring)\b/i,
  /\b(connected inhaler|monitoring program)\b/i,
  /\b(spinal cord stimulat|scs|high.?density|tonic scs)\b/i,
  /\b(hybrid closed.?loop|hcl|automated insulin)\b/i,
  /\b(smart insulin pen|smart pen)\b/i,
  /\b(ai.?grading|artificial intelligence|ai.?assisted)\b/i,
  /\b(npwt|negative pressure wound)\b/i,
  /\b(cardiac rehab)\b/i,
  // Pharmacological agents
  /\b(loop diuretic|furosemide|bumetanide|torasemide|torsemide)\b/i,
  /\b(ace.?inhibitor|ace.?inhib|ramipril|enalapril|lisinopril|captopril|perindopril|quinapril)\b/i,
  /\b(arb|angiotensin receptor blocker|valsartan|losartan|irbesartan|candesartan|olmesartan)\b/i,
  /\b(nsaid|non.?steroidal anti.?inflam|ibuprofen|naproxen|diclofenac|celecoxib|indomethacin|meloxicam)\b/i,
  /\b(statin|atorvastatin|rosuvastatin|simvastatin|pravastatin)\b/i,
  /\b(anticoagulant|warfarin|apixaban|rivaroxaban|dabigatran|edoxaban)\b/i,
  /\b(beta.?blocker|bisoprolol|carvedilol|metoprolol|nebivolol)\b/i,
  /\b(mineralocorticoid antagonist|spironolactone|eplerenone)\b/i,
  /\b(triple therapy|dual therapy|polypharmacy|co.?prescription)\b/i,
  /\b(sglt.?2|gfz|empagliflozin|dapagliflozin|canagliflozin)\b/i,
  /\b(glp.?1|semaglutide|liraglutide|dulaglutide)\b/i,
]

const OUTCOME_PATTERNS = [
  { regex: /\b(hba1c|a1c|glycated hemoglobin)\b/i, concept: 'L1_M001', label: 'HbA1c' },
  { regex: /\b(time.?in.?range|tir)\b/i, concept: 'L1_M002', label: 'Time in Range' },
  { regex: /\b(hypoglycemia|time.?below.?range|tbr)\b/i, concept: 'L1_M003', label: 'Time Below Range' },
  { regex: /\b(systolic blood pressure|sbp|blood pressure)\b/i, concept: 'L1_M008', label: 'Systolic BP' },
  { regex: /\b(ahi|apnea.?hypopnea|residual ahi)\b/i, concept: 'L2_DT004', label: 'Residual AHI' },
  { regex: /\b(koos|functional outcome|knee function)\b/i, concept: 'L1_PRO001', label: 'KOOS Score' },
  { regex: /\b(exacerbation|flare).{0,20}(asthma|copd)\b/i, concept: 'L1_O003', label: 'Exacerbation' },
  { regex: /\b(copd|exacerbation).{0,20}(hospitali|rate)\b/i, concept: 'L1_O002', label: 'COPD Exacerbation' },
  { regex: /\b(hospitali|admission|unplanned)\b/i, concept: 'L1_E001', label: 'Hospitalization' },
  { regex: /\b(stroke|cva|cerebrovascular)\b/i, concept: 'L1_C005', label: 'Stroke' },
  { regex: /\b(mortality|death|survival)\b/i, concept: 'L1_O001', label: 'Mortality' },
  { regex: /\b(kt.?v|dialysis adequacy)\b/i, concept: 'L1_M023', label: 'Kt/V' },
  { regex: /\b(weight|ewl|excess weight|bmi)\b/i, concept: 'L1_M043', label: 'Weight Loss / EWL' },
  { regex: /\b(diabetes remission|glycemic remission)\b/i, concept: 'L1_O005', label: 'Diabetes Remission' },
  { regex: /\b(seizure frequency|seizure rate|seizure count)\b/i, concept: 'L1_M045', label: 'Seizure Frequency' },
  { regex: /\b(healing|time.?to.?heal|wound heal)\b/i, concept: 'L1_O004', label: 'Wound Healing' },
  { regex: /\b(referral|missed referral|delayed referral)\b/i, concept: 'L1_O007', label: 'Referral' },
  { regex: /\b(quality of life|qol|eortc|qlq)\b/i, concept: 'L1_PRO006', label: 'Quality of Life' },
  { regex: /\b(acq|asthma control)\b/i, concept: 'L1_PRO005', label: 'ACQ-5' },
  { regex: /\b(rom|flexion|range of motion)\b/i, concept: 'L1_M036', label: 'ROM — Flexion' },
  { regex: /\b(vo2|maximal oxygen|aerobic capacity)\b/i, concept: 'L1_M033', label: 'VO2max' },
  { regex: /\b(postprandial|post.?meal|2.?hour glucose|ppg)\b/i, concept: 'L1_O006', label: 'Postprandial Glucose' },
  { regex: /\b(pain|nrs|vas|pain score)\b/i, concept: 'L1_M039', label: 'Pain Score' },
  { regex: /\b(50.?percent|50%.?reduction|pain response)\b/i, concept: 'L1_M039', label: 'Pain Response (50%)' },
  // Bleeding / haemostasis
  { regex: /\b(major bleed|bleed|hemorrhage|haemorrhage|intracranial|gi bleed|gastrointestinal bleed|isth)\b/i, concept: 'ENRC_20260614_120', label: 'Major Bleeding Event' },
  // Cardiac rhythm
  { regex: /\b(af detection|atrial fibrillation detection|icm.detected)\b/i, concept: 'ENRC_20260614_121', label: 'AF Detection Rate' },
  { regex: /\b(anticoagulation initiation|time to anticoag)\b/i, concept: 'ENRC_20260614_122', label: 'Time to Anticoagulation' },
  // Adherence outcomes
  { regex: /\b(medication adherence|drug adherence|adherence rate|mpr|pdc)\b/i, concept: 'ENRC_20260614_126', label: 'Medication Adherence Rate' },
  { regex: /\b(inhaler adherence|inhaler compliance|controller adherence)\b/i, concept: 'ENRC_20260614_123', label: 'Inhaler Adherence Rate' },
  // Nephrology / renal
  { regex: /\b(egfr|gfr|glomerular filtration rate|renal function|kidney function)\b/i, concept: 'L1_M021', label: 'eGFR' },
  { regex: /\b(creatinine|serum creatinine)\b/i, concept: 'L1_M022', label: 'Serum Creatinine' },
  { regex: /\b(esrd|end.?stage renal|renal replacement therapy|dialysis initiation)\b/i, concept: 'L1_C010', label: 'ESRD' },
  { regex: /\b(proteinuria|albuminuria|urine albumin|uacr|microalbumin)\b/i, concept: 'ENRC_20260614_110', label: 'Proteinuria / Albuminuria' },
  // Cardiology
  { regex: /\b(lvef|ejection fraction|left ventricular)\b/i, concept: 'L1_M006', label: 'LVEF' },
  { regex: /\b(bnp|nt.?probnp|natriuretic peptide)\b/i, concept: 'L1_M007', label: 'BNP / NT-proBNP' },
  { regex: /\b(heart failure event|hf hospitali|hf admission)\b/i, concept: 'L1_C003', label: 'Heart Failure' },
  { regex: /\b(major adverse cardiovascular|mace|cv event|cardiovascular death)\b/i, concept: 'L1_C005', label: 'MACE' },
  // Metabolic / labs
  { regex: /\b(uric acid|gout|hyperuricemia)\b/i, concept: 'ENRC_20260614_107', label: 'Serum Uric Acid' },
  { regex: /\b(insulin resistance|homa.?ir|homa)\b/i, concept: 'ENRC_20260614_115', label: 'Insulin Resistance (HOMA-IR)' },
]

const THERAPEUTIC_AREA_MAP = {
  'endocrinology': /\b(diabetes|glucose|hba1c|insulin|cgm|glyc)\b/i,
  'cardiology':    /\b(heart|cardiac|atrial|af|stroke|blood pressure|hf|lvef|bnp|avo2)\b/i,
  'pulmonology':   /\b(asthma|copd|inhaler|lung|fev|cpap|osa|apnea|breathe|respiratory)\b/i,
  'orthopedics':   /\b(knee|tka|joint|orthop|arthroplasty|fracture|rom|brace)\b/i,
  'nephrology':    /\b(kidney|renal|dialysis|egfr|creatinine|esrd|ktv|albumin)\b/i,
  'neurology':     /\b(seizure|epilep|neuro|brain|scs|spinal cord)\b/i,
  'oncology':      /\b(cancer|tumor|oncol|chemotherapy|ctcae|eortc|qol)\b/i,
  'wound_care':    /\b(wound|ulcer|heal|npwt|dressing)\b/i,
  'ophthalmology': /\b(retinal|eye|vision|diabetic retinopathy|grading)\b/i,
  'metabolic':     /\b(bariatric|obesity|weight|bmi|sleeve|bypass|metabolic)\b/i,
  'rehabilitation':/\b(rehab|physiotherap|physical therapy|cardiac rehab|recovery)\b/i,
  'pain':          /\b(pain|nrs|vas|analges|opioid|scs|stimulat|crps|fbss)\b/i,
  'hypertension':  /\b(hypertension|blood pressure|sbp|dbp|antihypertensive)\b/i,
  'arrhythmia':    /\b(atrial fibrillation|afib|af|icm|cardiac monitor)\b/i,
}

const CAUSAL_ROLE_MAP = [
  { role: 'exposure', patterns: [
    /\b(does|do|effect of|impact of|using|use of|improve|reduce|whether)\b/i,
    /\b(level of|amount of|frequency of|number of)\b/i,
  ]},
  { role: 'outcome', patterns: [
    /\b(reduce|improve|increase|decrease|lower|higher|better|predict|associated with)\b/i,
    /\b(result in|lead to|produce|achieve)\b/i,
  ]},
]

// ── Taxonomy concept matcher ──────────────────────────────────────────────────

/**
 * Scans the question against all active taxonomy concepts using label/synonym
 * word-boundary matching. Returns only if the semantic store is already loaded —
 * parsePICOT is always synchronous.
 *
 * Concepts with very short labels (< 4 chars) are skipped to avoid noise.
 * Layer 0 (structural/administrative) concepts are excluded.
 */
function matchConceptsFromTaxonomy(question) {
  if (!isSemanticStoreReady()) return []

  const index = getTaxonomyIndex()
  const matched = []
  const seen = new Set()

  for (const concept of index) {
    if (concept.layer === 0) continue
    if (seen.has(concept.id)) continue

    const terms = [concept.label, ...(concept.synonyms || [])].filter(s => s && s.length >= 4)

    for (const term of terms) {
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      if (new RegExp(`\\b${escaped}\\b`, 'i').test(question)) {
        seen.add(concept.id)
        matched.push({
          concept_id: concept.id,
          label:      concept.label,
          layer:      concept.layer,
          domain:     concept.domain,
          source:     'taxonomy',
        })
        break
      }
    }
  }

  return matched
}

// ── PICOT frame detector ──────────────────────────────────────────────────────

/**
 * Parse a free-text clinical question into a structured PICOT frame.
 * When the semantic store is ready, taxonomy concepts are matched and merged
 * into outcomes/taxonomy_concepts so downstream DAG seeding is enriched.
 */
export function parsePICOT(question) {
  const q = question || ''

  // Detect therapeutic areas
  const therapeuticAreas = []
  for (const [area, regex] of Object.entries(THERAPEUTIC_AREA_MAP)) {
    if (regex.test(q)) therapeuticAreas.push(area)
  }

  // Extract likely outcomes from hardcoded patterns
  const outcomes = []
  const outcomeIds = new Set()
  for (const { regex, concept, label } of OUTCOME_PATTERNS) {
    if (regex.test(q)) {
      outcomes.push({ concept_id: concept, label, source: 'pattern' })
      outcomeIds.add(concept)
    }
  }

  // Enrich with taxonomy concepts when the store is loaded
  const taxonomyConcepts = matchConceptsFromTaxonomy(q)
  for (const c of taxonomyConcepts) {
    if (!outcomeIds.has(c.concept_id)) {
      outcomeIds.add(c.concept_id)
      outcomes.push({ concept_id: c.concept_id, label: c.label, source: 'taxonomy' })
    }
  }

  // Detect intervention type
  const interventionType = detectInterventionType(q)

  // Extract temporal window
  const timeWindow = extractTimeWindow(q)

  // Extract population keywords
  const population = extractPopulation(q)

  // Extract comparator
  const comparator = extractComparator(q)

  return {
    raw_question: q,
    therapeutic_areas: therapeuticAreas,
    population,
    intervention: interventionType,
    comparator,
    outcomes,
    taxonomy_concepts: taxonomyConcepts,
    time_window: timeWindow,
    is_causal: isCausalQuestion(q),
    is_predictive: isPredictiveQuestion(q),
    has_dose_response: hasDoseResponse(q),
  }
}

function detectInterventionType(q) {
  for (const pattern of INTERVENTION_PATTERNS) {
    const m = q.match(pattern)
    if (m) return m[0].toLowerCase()
  }
  return null
}

function extractTimeWindow(q) {
  const matches = q.match(/\b(\d+)\s*(day|week|month|year)s?\b/gi) || []
  return matches.map(m => m.toLowerCase())
}

function extractPopulation(q) {
  const keywords = []
  const conditionPatterns = [
    /patients with ([^,.]+(?:diabetes|heart failure|afib|copd|asthma|epilepsy|obesity|hypertension|stroke|esrd|apnea|pain|t1d|t2d|cancer|ckd|renal|kidney)[^,.]*)/i,
    /(?:adults?|patients?|individuals?).{0,30}with ([^,.]+(?:heart failure|diabetes|hypertension|ckd|renal|kidney|afib|copd|cancer|obesity)[^,.]*)/i,
    /in ([^,.]+(?:pediatric|adult|elderly|older)[^,.]*)\s/i,
  ]
  for (const p of conditionPatterns) {
    const m = q.match(p)
    if (m) keywords.push(m[1].trim())
  }
  return keywords.length ? keywords.join('; ') : 'Not specified'
}

function extractComparator(q) {
  const patterns = [
    /compared to ([^,.?]+)/i,
    /versus ([^,.?]+)/i,
    /vs\.?\s+([^,.?]+)/i,
    /than ([^,.?]+standard[^,.?]*)/i,
  ]
  for (const p of patterns) {
    const m = q.match(p)
    if (m) return m[1].trim()
  }
  return null
}

function isCausalQuestion(q) {
  return /\b(does|do|cause|effect|impact|reduce|improve|prevent|result in|lead to|associated with)\b/i.test(q)
}

function isPredictiveQuestion(q) {
  return /\b(predict|predictor|associated with|marker|indicat)\b/i.test(q)
}

function hasDoseResponse(q) {
  return /\b(dose|level of|amount of|minimum|threshold|higher|lower|more|frequency)\b/i.test(q)
}

// ── Post-Haiku taxonomy lookup ────────────────────────────────────────────────

/**
 * Given a short text string (e.g. "SGLT2 inhibitors", "HbA1c reduction"),
 * returns the best-matching taxonomy concept by scanning all labels/synonyms
 * for a word-boundary match. Returns the longest match to avoid single-word
 * false positives. Minimum term length 6 chars for field-level matching.
 */
export function findConceptInTaxonomy(text) {
  if (!isSemanticStoreReady() || !text) return null
  const index = getTaxonomyIndex()

  // Returns true if this concept_id has at least one causal relation in the ontology.
  // Used to break ties when multiple duplicate concepts share the same label/synonym —
  // we always prefer the one that is actually wired into the causal graph.
  const hasRelations = (id) => {
    const ont = getCausalOntology()
    return !!(ont.bySubject?.has(id) || ont.byObject?.has(id))
  }

  // Exact normalized synonym match — highest priority, same logic as the server-side
  // matchTokens. When multiple concepts share the same normalized synonym (duplicates),
  // prefer the one with causal relations.
  const normText = normalize(text)
  if (normText) {
    const synLookup = getSynonymLookup()
    const ids = synLookup.get(normText)
    if (ids?.length) {
      const bestId = ids.find(id => hasRelations(id)) ?? ids[0]
      const c = index.find(ci => ci.id === bestId)
      if (c) return { concept_id: c.id, label: c.label, domain: c.domain }
    }
  }

  // Fallback: longest word-boundary substring match.
  // Prefer concepts with causal relations as a tiebreaker on equal-length matches.
  let bestMatch = null
  let bestLen = 0
  let bestHasRels = false
  for (const concept of index) {
    if (concept.layer === 0) continue
    const terms = [concept.label, ...(concept.synonyms || [])].filter(s => s && s.length >= 6)
    for (const term of terms) {
      if (term.length < bestLen) continue
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      if (new RegExp(`\\b${escaped}\\b`, 'i').test(text)) {
        const conceptHasRels = hasRelations(concept.id)
        if (term.length > bestLen || (term.length === bestLen && conceptHasRels && !bestHasRels)) {
          bestLen = term.length
          bestMatch = { concept_id: concept.id, label: concept.label, domain: concept.domain }
          bestHasRels = conceptHasRels
        }
      }
    }
  }
  return bestMatch
}

// ── Intervention concept ID map ───────────────────────────────────────────────
// Maps free-text intervention patterns → taxonomy concept IDs so that
// DagGenerationTab can seed the causal subgraph lookup from the question itself,
// not only from dataset-mapped concepts.

export const INTERVENTION_CONCEPT_PATTERNS = [
  { regex: /\b(cgm|continuous glucose monitor)\b/i,                   concept: 'L2_SC003',           label: 'CGM Use' },
  { regex: /\b(hybrid closed.?loop|hcl|automated insulin delivery)\b/i, concept: 'ENRC_20260614_201', label: 'Hybrid Closed-Loop Insulin Delivery' },
  { regex: /\b(cpap|apap|continuous positive airway pressure)\b/i,    concept: 'ENRC_20260614_202',  label: 'CPAP Therapy' },
  { regex: /\b(implantable cardiac monitor|icm|loop recorder)\b/i,    concept: 'ENRC_20260614_203',  label: 'Implantable Cardiac Monitor' },
  { regex: /\b(smart inhaler|connected inhaler|electronic inhaler)\b/i, concept: 'ENRC_20260614_204', label: 'Smart/Connected Inhaler' },
  { regex: /\b(robotic.?tka|robotic.?assisted tka|robotic knee)\b/i,  concept: 'ENRC_20260614_205',  label: 'Robotic-Assisted TKA' },
  { regex: /\b(remote.?hf monitor|heart failure monitor|remote cardiac monitor)\b/i, concept: 'ENRC_20260614_206', label: 'Remote HF Monitoring' },
  { regex: /\b(spinal cord stim|scs|high.?density scs)\b/i,          concept: 'ENRC_20260614_207',  label: 'Spinal Cord Stimulator (SCS)' },
  { regex: /\b(npwt|negative pressure wound|vacuum.?assisted closure|vac)\b/i, concept: 'ENRC_20260614_208', label: 'NPWT' },
  { regex: /\b(smart.?insulin.?pen|connected.?insulin.?pen)\b/i,      concept: 'ENRC_20260614_209',  label: 'Smart Insulin Pen' },
  { regex: /\b(ai.?retinal|ai.?assisted retinal|automated retinal grading)\b/i, concept: 'ENRC_20260614_210', label: 'AI Retinal Screening' },
  { regex: /\b(bariatric surgery|sleeve gastrectomy|gastric bypass|rygb)\b/i, concept: 'ENRC_20260614_211', label: 'Bariatric Surgery' },
  { regex: /\b(doac|apixaban|rivaroxaban|dabigatran|edoxaban|direct oral anticoag)\b/i, concept: 'ENRC_20260614_212', label: 'Direct Oral Anticoagulant (DOAC)' },
  { regex: /\b(p.?glycoprotein|p.?gp inhibitor|cyp3a4.?inhibitor|clarithromycin|amiodarone|verapamil)\b/i, concept: 'ENRC_20260614_213', label: 'P-gp/CYP3A4 Inhibitor' },
  { regex: /\b(digital cardiac rehab|cardiac rehabilitation program|digital rehab)\b/i, concept: 'ENRC_20260614_214', label: 'Digital Cardiac Rehabilitation' },
  { regex: /\b(wearable.?seizure|seizure.?detect|seizure.?monitor)\b/i, concept: 'ENRC_20260614_215', label: 'Wearable Seizure Detection' },
  { regex: /\b(remote.?patient.?monitor|rpm program|telehealth monitoring)\b/i, concept: 'ENRC_20260614_216', label: 'Remote Patient Monitoring (RPM)' },
  { regex: /\b(high.?flux hemodialysis|high efficiency dialysis|hemo?dialysis)\b/i, concept: 'ENRC_20260614_217', label: 'High-Flux Hemodialysis' },
]
