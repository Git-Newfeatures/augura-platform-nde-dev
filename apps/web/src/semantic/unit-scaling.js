const DECIMAL_PREFIXES = [
  ['da', 1e1],
  ['k', 1e3],
  ['h', 1e2],
  ['d', 1e-1],
  ['c', 1e-2],
  ['m', 1e-3],
  ['u', 1e-6],
  ['n', 1e-9],
  ['p', 1e-12],
]

const PREFIXABLE_UNITS = new Set(['g', 'L', 'm', 'mol', 's'])
const FIXED_UNITS = new Set(['min', 'h', 'd', 'a'])

function normalizeUnitText(value) {
  return String(value || '')
    .trim()
    .replace(/[µμ]/g, 'u')
    .replace(/²/g, '2')
    .replace(/³/g, '3')
    .replace(/\s+/g, '')
}

function parseAtom(rawAtom) {
  const match = rawAtom.match(/^([A-Za-z]+)(-?\d+)?$/)
  if (!match) return null

  const [, symbol, exponentText] = match
  const exponent = exponentText ? Number(exponentText) : 1
  if (!Number.isInteger(exponent)) return null

  if (FIXED_UNITS.has(symbol)) {
    return { base: symbol, factor: 1, exponent }
  }

  if (PREFIXABLE_UNITS.has(symbol)) {
    return { base: symbol, factor: 1, exponent }
  }

  for (const [prefix, factor] of DECIMAL_PREFIXES) {
    if (!symbol.startsWith(prefix)) continue
    const base = symbol.slice(prefix.length)
    if (PREFIXABLE_UNITS.has(base)) {
      return { base, factor, exponent }
    }
  }

  return null
}

function addDimension(dimensions, base, exponent) {
  const next = (dimensions.get(base) || 0) + exponent
  if (next === 0) dimensions.delete(base)
  else dimensions.set(base, next)
}

function parseProduct(value, direction, dimensions) {
  if (!value || value === '1') return 1

  let factor = 1
  for (const rawAtom of value.split(/[.*]/).filter(Boolean)) {
    const atom = parseAtom(rawAtom)
    if (!atom) return null
    const signedExponent = direction * atom.exponent
    addDimension(dimensions, atom.base, signedExponent)
    factor *= atom.factor ** signedExponent
  }
  return factor
}

/**
 * Parse the deliberately supported subset of UCUM needed for decimal-prefix
 * scaling. This excludes bracketed customary units and offset units.
 */
export function parseScalableUnit(rawUnit) {
  const normalized = normalizeUnitText(rawUnit)
  if (!normalized || normalized.includes('[') || normalized.includes(']')) return null

  const parts = normalized.split('/')
  if (parts.length > 2) return null

  const dimensions = new Map()
  const numeratorFactor = parseProduct(parts[0], 1, dimensions)
  if (numeratorFactor == null) return null

  const denominatorFactor = parseProduct(parts[1], -1, dimensions)
  if (denominatorFactor == null) return null

  return {
    normalized,
    factor: numeratorFactor * denominatorFactor,
    dimensions: [...dimensions.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([base, exponent]) => `${base}:${exponent}`)
      .join('|'),
  }
}

/**
 * Return the multiplier that converts a source value into the target unit.
 * For example, g/L -> mg/L returns 1000, while ug/mL -> mg/L returns 1.
 */
export function getDecimalScaleFactor(sourceUnit, targetUnit) {
  const source = parseScalableUnit(sourceUnit)
  const target = parseScalableUnit(targetUnit)
  if (!source || !target || source.dimensions !== target.dimensions) return null

  const scaleFactor = source.factor / target.factor
  return Number.isFinite(scaleFactor) && scaleFactor > 0 ? scaleFactor : null
}

