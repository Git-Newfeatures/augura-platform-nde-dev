/**
 * Lexical Normalizer
 * Converts raw column names to a normalized form for fuzzy matching.
 * Uses only pure JavaScript — no external dependencies.
 *
 * Ported verbatim from data-intake-nde (src/semantic/lexical-normalizer.js).
 */

// Common abbreviation expansions
const ABBREV_MAP = {
  // Clinical measurements
  hba1c: 'hemoglobin a1c', a1c: 'hemoglobin a1c', hgba1c: 'hemoglobin a1c',
  sbp: 'systolic blood pressure', dbp: 'diastolic blood pressure',
  tir: 'time in range', tbr: 'time below range', tar: 'time above range',
  bmi: 'body mass index', spo2: 'oxygen saturation',
  ahi: 'apnea hypopnea index', fev1: 'forced expiratory volume',
  fvc: 'forced vital capacity', ktv: 'dialysis adequacy',
  lvef: 'ejection fraction', egfr: 'estimated glomerular filtration rate',
  scr: 'serum creatinine', pth: 'parathyroid hormone',
  ldl: 'low density lipoprotein', hdl: 'high density lipoprotein',
  tg: 'triglycerides', vo2max: 'maximal oxygen uptake',
  mets: 'metabolic equivalents', ewl: 'excess weight loss', twl: 'total weight loss',
  koos: 'knee outcome score', acq: 'asthma control questionnaire',
  qlq: 'quality of life questionnaire', ctcae: 'toxicity grade',
  vas: 'pain analog scale', nrs: 'pain rating scale',
  // Devices / procedures
  tka: 'total knee arthroplasty', tkr: 'total knee replacement',
  rygb: 'gastric bypass', vsg: 'sleeve gastrectomy',
  // Conditions
  af: 'atrial fibrillation', afib: 'atrial fibrillation',
  hf: 'heart failure', chf: 'heart failure',
  osa: 'sleep apnea', cpap: 'positive airway pressure',
  esrd: 'end stage renal disease', copd: 'chronic obstructive pulmonary disease',
  t1d: 'type 1 diabetes', t2d: 'type 2 diabetes',
  t1dm: 'type 1 diabetes', t2dm: 'type 2 diabetes',
  dm: 'diabetes', icm: 'cardiac monitor',
  // NOTE: cgm intentionally NOT expanded — keep as token for exact synonym matching
  hcl: 'closed loop', mdi: 'daily injection',
  ics: 'inhaled corticosteroid', acei: 'ace inhibitor', arb: 'angiotensin blocker',
  scs: 'spinal cord stimulator', npwt: 'negative pressure wound',
  dr: 'diabetic retinopathy', qol: 'quality of life',
  pro: 'patient reported outcome', rpm: 'remote monitoring',
  // Common short forms
  bl: 'baseline', pt: 'patient',
  wt: 'weight', ht: 'height', dx: 'diagnosis', rx: 'medication',
  pct: 'percent', mgdl: 'mg dl', mmol: 'millimol', gdl: 'g dl',
  pgml: 'pg ml', kgm2: 'kg m2',
}

// Patterns to strip from column names (noise tokens)
const NOISE_TOKENS = new Set([
  'value','values','score','scores','result','results','data','var','variable',
  'col','column','field','entry','item','measure','measurement','level',
  'reading','status','flag','indicator','code','cd','id','num','no','n',
  'the','a','an','of','in','at','on','for','and','or','with','per',
])

/**
 * Normalize a raw column name to a clean token string.
 * Steps:
 * 1. Lowercase
 * 2. Replace separators (_, ., -, space) with space
 * 3. Strip special chars except space
 * 4. Expand known abbreviations
 * 5. Remove noise tokens
 * 6. Collapse whitespace
 */
export function normalize(raw) {
  if (!raw || typeof raw !== 'string') return ''

  let s = raw.toLowerCase()

  // Remove common encoding artifacts (e.g. sex..m.f. → sex mf)
  s = s.replace(/\.\./g, ' ')

  // Handle dot-notation timepoints: strip trailing .BL, .3M, .6M, .12M, .24M etc.
  // e.g. cgm_tir.BL → cgm_tir, A1c.3M → A1c
  s = s.replace(/\.(bl|baseline|3m|6m|12m|24m|36m|w0|w2|w4|w8|w12|pre|post|fu)\b/gi, '')

  // Replace separators with spaces
  s = s.replace(/[_.:\-/\\|]/g, ' ')

  // Remove chars that add no semantic value
  s = s.replace(/[^a-z0-9 ]/g, '')

  // Tokenize
  let tokens = s.split(/\s+/).filter(Boolean)

  // Expand abbreviations (expand each token independently)
  tokens = tokens.flatMap(tok => {
    if (ABBREV_MAP[tok]) return ABBREV_MAP[tok].split(' ')
    return [tok]
  })

  // Remove pure numeric tokens and noise
  tokens = tokens.filter(tok => tok && !NOISE_TOKENS.has(tok) && !/^\d+$/.test(tok))

  return tokens.join(' ').trim()
}

/**
 * Produce a bag of character n-grams from a string.
 * Used for fuzzy similarity when exact token match fails.
 */
export function charNgrams(str, n = 3) {
  const padded = `  ${str}  `
  const grams = new Map()
  for (let i = 0; i <= padded.length - n; i++) {
    const g = padded.slice(i, i + n)
    grams.set(g, (grams.get(g) || 0) + 1)
  }
  return grams
}

/**
 * Cosine similarity between two n-gram maps.
 */
export function ngramSimilarity(a, b) {
  if (!a.size || !b.size) return 0
  let dot = 0, normA = 0, normB = 0
  for (const [g, cnt] of a) {
    normA += cnt * cnt
    if (b.has(g)) dot += cnt * b.get(g)
  }
  for (const [, cnt] of b) normB += cnt * cnt
  if (!normA || !normB) return 0
  return dot / (Math.sqrt(normA) * Math.sqrt(normB))
}

/**
 * Levenshtein distance (normalized 0–1).
 */
export function levenshtein(a, b) {
  const la = a.length, lb = b.length
  if (!la) return lb === 0 ? 1 : 0
  if (!lb) return 0
  const dp = Array.from({ length: la + 1 }, (_, i) => i)
  for (let j = 1; j <= lb; j++) {
    let prev = j
    for (let i = 1; i <= la; i++) {
      const cur = a[i - 1] === b[j - 1]
        ? dp[i - 1]
        : 1 + Math.min(dp[i - 1], dp[i], prev)
      dp[i - 1] = prev
      prev = cur
    }
    dp[la] = prev
  }
  const editDist = dp[la]
  return 1 - editDist / Math.max(la, lb)
}

/**
 * Token Jaccard similarity between two normalized strings.
 */
export function tokenJaccard(a, b) {
  const setA = new Set(a.split(' '))
  const setB = new Set(b.split(' '))
  if (!setA.size && !setB.size) return 1
  let inter = 0
  for (const t of setA) if (setB.has(t)) inter++
  return inter / (setA.size + setB.size - inter)
}

/**
 * Combined string similarity score.
 * Weighted blend of n-gram cosine, token Jaccard, and Levenshtein.
 */
export function stringSimilarity(a, b) {
  if (!a || !b) return 0
  if (a === b) return 1
  const ng = ngramSimilarity(charNgrams(a), charNgrams(b))
  const jac = tokenJaccard(a, b)
  const lev = levenshtein(a, b)
  return 0.45 * ng + 0.35 * jac + 0.20 * lev
}

/**
 * Parse date strings in multiple formats:
 * ISO (2024-01-15), US (01/15/2024), European (15/01/2024)
 * Returns a Date or null.
 */
export function parseDate(s) {
  if (!s || typeof s !== 'string') return null
  // ISO
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return new Date(s)
  // US: MM/DD/YYYY
  const us = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/)
  if (us) return new Date(`${us[3]}-${us[1].padStart(2,'0')}-${us[2].padStart(2,'0')}`)
  // EU: DD/MM/YYYY
  const eu = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/)
  if (eu) return new Date(`${eu[3]}-${eu[2].padStart(2,'0')}-${eu[1].padStart(2,'0')}`)
  return null
}

/**
 * Detect if a column's sample values look like dates.
 */
export function isDateColumn(samples) {
  const attempts = samples.slice(0, 10).filter(Boolean)
  if (!attempts.length) return false
  const parsed = attempts.map(parseDate)
  const valid = parsed.filter(d => d instanceof Date && !isNaN(d))
  return valid.length / attempts.length > 0.7
}

/**
 * Detect if a column looks like a numeric measurement.
 */
export function isNumericColumn(samples) {
  const clean = samples.slice(0, 20).filter(v =>
    v !== null && v !== undefined && v !== '' && v !== 'NA' && v !== '-99' && v !== '999'
  )
  if (!clean.length) return false
  const nums = clean.filter(v => !isNaN(Number(v)))
  return nums.length / clean.length > 0.8
}

/**
 * Detect if a column looks like a categorical/coded field.
 */
export function isCategoricalColumn(samples, threshold = 0.5) {
  const clean = samples.filter(v => v !== null && v !== undefined && v !== '')
  if (!clean.length) return false
  const unique = new Set(clean.map(v => String(v).toLowerCase()))
  return unique.size / clean.length < threshold && unique.size <= 20
}

/**
 * Estimate the missing rate of a column.
 */
export function missingRate(samples) {
  const missing = samples.filter(v =>
    v === null || v === undefined || v === '' ||
    v === 'NA' || v === 'N/A' || v === '-99' || v === '999' ||
    (typeof v === 'string' && v.trim() === '')
  )
  return samples.length ? missing.length / samples.length : 0
}

/**
 * Get a sample of values from a column for profiling.
 */
export function getColumnSamples(rows, colName, maxSamples = 30) {
  return rows.slice(0, maxSamples).map(r => r[colName])
}

/**
 * Summarize numeric samples.
 */
export function numericSummary(samples) {
  const nums = samples
    .filter(v => v !== null && v !== '' && v !== 'NA' && !isNaN(Number(v)) && v !== '-99' && v !== '999')
    .map(Number)
  if (!nums.length) return null
  const sorted = [...nums].sort((a, b) => a - b)
  const mean = nums.reduce((s, v) => s + v, 0) / nums.length
  const min = sorted[0], max = sorted[sorted.length - 1]
  const median = sorted[Math.floor(sorted.length / 2)]
  return { mean: +mean.toFixed(2), min, max, median, n: nums.length }
}
