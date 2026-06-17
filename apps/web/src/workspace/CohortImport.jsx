import { useState, useRef } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { apiJson } from '@/api'

// Minimal RFC-4180-ish CSV parser (handles quoted fields, escaped quotes, CRLF).
function parseCSV(text) {
  const rows = []
  let row = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++ }
        else inQuotes = false
      } else field += c
    } else if (c === '"') {
      inQuotes = true
    } else if (c === ',') {
      row.push(field); field = ''
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(field); field = ''
      if (row.some((v) => v !== '')) rows.push(row)
      row = []
    } else {
      field += c
    }
  }
  if (field !== '' || row.length) { row.push(field); if (row.some((v) => v !== '')) rows.push(row) }
  return rows
}

const num = (v) => {
  if (v == null || String(v).trim() === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
const str = (v) => {
  const s = v == null ? '' : String(v).trim()
  return s === '' ? null : s
}

// Expected long-format columns (one row per member × timepoint).
const MEMBER_FIELDS = ['age', 'sex', 'bmi', 'engagement_group', 'country']
const BIOMARKER_FIELDS = ['hba1c_pct', 'ldl_mgdl', 'hs_crp_mgl', 'adherence_pct']

function buildPayload(rows, cohortName) {
  const header = rows[0].map((h) => String(h).trim().toLowerCase())
  const idx = (name) => header.indexOf(name)
  const cMember = idx('member_id')
  const cTime = idx('timepoint_months')
  if (cMember < 0) throw new Error('Missing required column: member_id')

  const memberCols = Object.fromEntries(MEMBER_FIELDS.map((f) => [f, idx(f)]))
  const bioCols = Object.fromEntries(BIOMARKER_FIELDS.map((f) => [f, idx(f)]))

  const membersById = new Map()
  const biomarkers = []
  for (const r of rows.slice(1)) {
    const memberId = str(r[cMember])
    if (!memberId) continue
    if (!membersById.has(memberId)) {
      membersById.set(memberId, {
        member_id: memberId,
        age: memberCols.age >= 0 ? num(r[memberCols.age]) : null,
        sex: memberCols.sex >= 0 ? str(r[memberCols.sex]) : null,
        bmi: memberCols.bmi >= 0 ? num(r[memberCols.bmi]) : null,
        engagement_group: memberCols.engagement_group >= 0 ? str(r[memberCols.engagement_group]) : null,
        country: memberCols.country >= 0 ? str(r[memberCols.country]) : null,
      })
    }
    // A biomarker row needs a timepoint; rows without one only contribute the member.
    if (cTime >= 0 && str(r[cTime]) != null) {
      biomarkers.push({
        member_id: memberId,
        timepoint_months: Math.round(num(r[cTime]) ?? 0),
        hba1c_pct: bioCols.hba1c_pct >= 0 ? num(r[bioCols.hba1c_pct]) : null,
        ldl_mgdl: bioCols.ldl_mgdl >= 0 ? num(r[bioCols.ldl_mgdl]) : null,
        hs_crp_mgl: bioCols.hs_crp_mgl >= 0 ? num(r[bioCols.hs_crp_mgl]) : null,
        adherence_pct: bioCols.adherence_pct >= 0 ? num(r[bioCols.adherence_pct]) : null,
      })
    }
  }
  const members = [...membersById.values()]
  if (members.length === 0) throw new Error('No members found in file')
  return { cohort_name: cohortName, members, biomarkers }
}

export function CohortImport({ onImported }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [cohortName, setCohortName] = useState('')
  const fileRef = useRef(null)

  async function onFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    setMsg(null)
    try {
      const text = await file.text()
      const rows = parseCSV(text)
      if (rows.length < 2) throw new Error('File has no data rows')
      const name = cohortName.trim() || file.name.replace(/\.csv$/i, '').replace(/\s+/g, '_').toLowerCase()
      const payload = buildPayload(rows, name)
      const res = await apiJson('/datasets/cohorts/import', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setMsg(`Imported "${res.cohort_name}" — ${res.members} members, ${res.biomarkers} biomarker rows.`)
      onImported?.(res)
    } catch (err) {
      const m = String(err?.message || '')
      setMsg(m.includes('401') ? 'Session expired — sign in again.' : `Import failed: ${m}`)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="text-xs font-medium">
        <Upload className="h-3.5 w-3.5" /> Import cohort
      </Button>
    )
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2">
        <input
          className="rounded-lg border border-border bg-white px-2.5 py-1.5 text-[12.5px] outline-none focus:border-primary/50"
          placeholder="cohort name (optional)"
          value={cohortName}
          onChange={(e) => setCohortName(e.target.value)}
          disabled={busy}
        />
        <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={onFile} disabled={busy} className="hidden" />
        <Button size="sm" onClick={() => fileRef.current?.click()} disabled={busy} className="text-xs font-medium">
          {busy ? 'Importing…' : 'Choose CSV'}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => { setOpen(false); setMsg(null) }} disabled={busy} className="text-xs">
          Close
        </Button>
      </div>
      <div className="max-w-[420px] text-right text-[11px] text-muted-foreground">
        {msg || 'Long-format CSV: member_id, timepoint_months, age, sex, bmi, engagement_group, country, hba1c_pct, ldl_mgdl, hs_crp_mgl, adherence_pct'}
      </div>
    </div>
  )
}
