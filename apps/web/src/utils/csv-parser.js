/**
 * Minimal RFC4180-style CSV parser for bundled standards files.
 * Supports quoted fields, escaped quotes, commas, and embedded newlines.
 */

export function parseCsv(text) {
  const rows = []
  let row = []
  let field = ''
  let inQuotes = false

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    const next = text[i + 1]

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"'
        i += 1
      } else if (ch === '"') {
        inQuotes = false
      } else {
        field += ch
      }
      continue
    }

    if (ch === '"') {
      inQuotes = true
    } else if (ch === ',') {
      row.push(field)
      field = ''
    } else if (ch === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else if (ch !== '\r') {
      field += ch
    }
  }

  if (field || row.length) {
    row.push(field)
    rows.push(row)
  }

  if (rows.length === 0) return []

  const headers = rows[0].map(h => h.trim())
  return rows.slice(1)
    .filter(values => values.some(value => value.trim() !== ''))
    .map(values => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ''])))
}

export function parseNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function parseBoolean(value) {
  return String(value).trim().toLowerCase() !== 'false'
}

export function splitList(value) {
  return String(value || '')
    .split(';')
    .map(v => v.trim())
    .filter(Boolean)
}

export function groupRows(rows, key) {
  const grouped = new Map()
  for (const row of rows) {
    const value = row[key]
    if (!grouped.has(value)) grouped.set(value, [])
    grouped.get(value).push(row)
  }
  return grouped
}
