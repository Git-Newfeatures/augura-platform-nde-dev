# Subsystem A5 — Intake wizard UI (additive) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Frontend slice. **Additive** — new files + one route line + one nav entry; does NOT modify existing `ExcelUpload`/`DatasetVerification`/`DatasetsPage` (avoids collision with concurrent frontend work).

**Goal:** A self-contained intake wizard at `/intake` (Upload → Mapping → DQ) wired to the new backend endpoints `POST /datasets/upload`, `POST /datasets/{id}/map`, `POST/GET /datasets/{id}/dq`, via a small api-client helper layer.

**Context:** the data-intake backend (A2 upload, A3 DQ, A4 mapping) is built + validated, but nothing in the frontend calls it. `api.js` already supports `FormData` multipart (keeps the browser boundary). The app router is `App.jsx` `<Routes>` inside `<AppShell/>`. Nav is `shell/sections.js` `WORKSPACE_SECTIONS`.

**Conventions:** scoped `git add`; commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Match the platform's Tailwind style (reference `workspace/DatasetsPage.jsx` / `ui/` components for class conventions). Run web build from `apps/web` (`npm run build`).

---

## File Structure
| File | Responsibility |
|------|----------------|
| `apps/web/src/intake/intakeApi.js` (create) | helper fns: `uploadDataset`, `mapDataset`, `runDq`, `getDq`, `listColumns` |
| `apps/web/src/views/intake/IntakeApp.jsx` (create) | wizard shell + step state |
| `apps/web/src/views/intake/IntakeUpload.jsx` (create) | step 1: file → upload |
| `apps/web/src/views/intake/IntakeMapping.jsx` (create) | step 2: run map + show proposals |
| `apps/web/src/views/intake/IntakeDQ.jsx` (create) | step 3: run DQ + show score/findings |
| `apps/web/src/App.jsx` (modify) | add `<Route path="/intake" element={<IntakeApp/>} />` |
| `apps/web/src/shell/sections.js` (modify) | add an "Intake" nav entry |

---

## Task 1: api helper layer + wizard components

**Files:** `intake/intakeApi.js`, `views/intake/IntakeApp.jsx`, `views/intake/IntakeUpload.jsx`, `views/intake/IntakeMapping.jsx`, `views/intake/IntakeDQ.jsx`

- [ ] **Step 1: `apps/web/src/intake/intakeApi.js`** (reuses `api.js` — `apiFetch` for multipart, `apiJson` for JSON):
```js
// Helpers for the intake pipeline (upload → map → DQ), wired to the FastAPI backend.
import { apiFetch, apiJson } from '../api'

export async function uploadDataset(file, { name, studyId } = {}) {
  const fd = new FormData()
  fd.append('file', file)
  if (name) fd.append('name', name)
  if (studyId) fd.append('study_id', studyId)
  const res = await apiFetch('/datasets/upload', { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`upload ${res.status}: ${(await res.text()).slice(0, 300)}`)
  return res.json() // { dataset, columns }
}

export const mapDataset = (id) => apiJson(`/datasets/${id}/map`, { method: 'POST' })
export const runDq = (id) => apiJson(`/datasets/${id}/dq`, { method: 'POST' })
export const getDq = (id) => apiJson(`/datasets/${id}/dq`)
export const listColumns = (id) => apiJson(`/datasets/${id}/columns`)
```

- [ ] **Step 2: `views/intake/IntakeUpload.jsx`**:
```jsx
import { useState } from 'react'
import { uploadDataset } from '../../intake/intakeApi'

export default function IntakeUpload({ onUploaded }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true); setError(null)
    try {
      const result = await uploadDataset(file)
      onUploaded(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-1 text-lg font-semibold">1 · Upload a dataset</h2>
      <p className="mb-4 text-sm text-muted-foreground">CSV or XLSX. Parsed and profiled server-side.</p>
      <input type="file" accept=".csv,.xlsx" disabled={busy} onChange={handleFile}
        className="block text-sm" />
      {busy && <p className="mt-3 text-sm text-muted-foreground">Uploading & profiling…</p>}
      {error && <p className="mt-3 text-sm text-[#C0392B]">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 3: `views/intake/IntakeMapping.jsx`**:
```jsx
import { useEffect, useState } from 'react'
import { mapDataset } from '../../intake/intakeApi'

export default function IntakeMapping({ datasetId, onNext }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    mapDataset(datasetId).then(r => live && setResult(r)).catch(e => live && setError(e.message))
    return () => { live = false }
  }, [datasetId])

  if (error) return <p className="text-sm text-[#C0392B]">{error}</p>
  if (!result) return <p className="text-sm text-muted-foreground">Mapping columns to the taxonomy…</p>

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-1 text-lg font-semibold">2 · Concept mapping</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        {result.mapped_count}/{result.total_count} columns matched
        {result.avg_confidence != null && ` · avg confidence ${(result.avg_confidence * 100).toFixed(0)}%`}
      </p>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-muted-foreground">
          <th className="py-1">Column</th><th>Proposed concept</th><th>Confidence</th></tr></thead>
        <tbody>
          {result.columns.map(c => (
            <tr key={c.column} className="border-t border-border">
              <td className="py-1 font-mono">{c.column}</td>
              <td>{c.proposed_canonical_id ?? '—'}</td>
              <td>{c.confidence_label}{c.confidence != null && ` (${(c.confidence * 100).toFixed(0)}%)`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={onNext}
        className="mt-4 rounded-md bg-[#1A6E7A] px-4 py-2 text-sm font-medium text-white">
        Next: Data quality
      </button>
    </div>
  )
}
```

- [ ] **Step 4: `views/intake/IntakeDQ.jsx`**:
```jsx
import { useEffect, useState } from 'react'
import { runDq } from '../../intake/intakeApi'

export default function IntakeDQ({ datasetId }) {
  const [res, setRes] = useState(null)
  const [bundle, setBundle] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    runDq(datasetId)
      .then(r => { if (!live) return; setRes(r); return getDqBundle(datasetId, setBundle) })
      .catch(e => live && setError(e.message))
    return () => { live = false }
  }, [datasetId])

  if (error) return <p className="text-sm text-[#C0392B]">{error}</p>
  if (!res) return <p className="text-sm text-muted-foreground">Running data-quality checks…</p>

  const findings = bundle?.bundle?.provenance ?? []
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="mb-1 text-lg font-semibold">3 · Data quality</h2>
      <p className="mb-4 text-sm">
        Overall score: <span className="font-semibold">{res.overall_score != null ? (res.overall_score * 100).toFixed(0) + '%' : '—'}</span>
        {' · '}status {res.status}
      </p>
      <ul className="space-y-1 text-sm">
        {findings.slice(0, 50).map((f, i) => (
          <li key={i} className="border-t border-border py-1">
            <span className="font-mono text-xs text-muted-foreground">[{f.severity}]</span> {f.message}
          </li>
        ))}
        {findings.length === 0 && <li className="text-muted-foreground">No findings.</li>}
      </ul>
    </div>
  )
}

async function getDqBundle(id, setBundle) {
  const { getDq } = await import('../../intake/intakeApi')
  try { setBundle(await getDq(id)) } catch { /* score already shown from run result */ }
}
```

- [ ] **Step 5: `views/intake/IntakeApp.jsx`** (wizard shell):
```jsx
import { useState } from 'react'
import IntakeUpload from './IntakeUpload'
import IntakeMapping from './IntakeMapping'
import IntakeDQ from './IntakeDQ'

const STEPS = ['upload', 'mapping', 'dq']

export default function IntakeApp() {
  const [step, setStep] = useState('upload')
  const [datasetId, setDatasetId] = useState(null)

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-1 text-xl font-semibold">Data intake</h1>
      <p className="mb-6 text-sm text-muted-foreground">Upload → map to concepts → data-quality report.</p>
      <ol className="mb-6 flex gap-2 text-xs">
        {STEPS.map(s => (
          <li key={s} className={`rounded-full px-3 py-1 ${step === s ? 'bg-[#1A6E7A] text-white' : 'bg-muted text-muted-foreground'}`}>{s}</li>
        ))}
      </ol>
      {step === 'upload' && (
        <IntakeUpload onUploaded={(r) => { setDatasetId(r.dataset.id); setStep('mapping') }} />
      )}
      {step === 'mapping' && datasetId && (
        <IntakeMapping datasetId={datasetId} onNext={() => setStep('dq')} />
      )}
      {step === 'dq' && datasetId && <IntakeDQ datasetId={datasetId} />}
    </div>
  )
}
```

- [ ] **Step 6: build check** — `cd apps/web && npm run build` → succeeds (catches JSX/import errors). Commit:
```bash
git add apps/web/src/intake/intakeApi.js apps/web/src/views/intake/IntakeApp.jsx apps/web/src/views/intake/IntakeUpload.jsx apps/web/src/views/intake/IntakeMapping.jsx apps/web/src/views/intake/IntakeDQ.jsx
git commit -m "feat(web): intake wizard (upload → map → DQ) wired to backend

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: route + nav wiring

**Files:** `App.jsx`, `shell/sections.js`

- [ ] **Step 1:** In `App.jsx`, import `IntakeApp` (`import IntakeApp from './views/intake/IntakeApp'`) and add inside the `<Route element={<AppShell />}>` group: `<Route path="/intake" element={<IntakeApp />} />`.
- [ ] **Step 2:** In `shell/sections.js` `WORKSPACE_SECTIONS`, add an entry `{ id: 'intake', label: 'Intake', path: '/intake', icon: <existing icon import, e.g. UploadCloud or Database> }` — reuse an icon already imported in that file (don't add a new dep). Place it after 'datasets'.
- [ ] **Step 3:** `cd apps/web && npm run build` → succeeds. Commit:
```bash
git add apps/web/src/App.jsx apps/web/src/shell/sections.js
git commit -m "feat(web): mount /intake route + nav entry

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: verification (controller, not a subagent)
- `npm run build` green.
- Preview render: start the web dev server, navigate to `/intake`, screenshot the Upload step (proves the route + wizard render). Full end-to-end (upload→map→dq through a live backend) is out of scope for A5 verification (needs a running API + a file) — note it.

---

## Self-review
- Additive: 5 new files + 2 one-line edits (route, nav). No change to existing dataset UI → no collision with concurrent frontend work.
- Reuses `api.js` (FormData already supported). No new deps.
- Build-verified; preview render confirms UI. E2e deferred (needs running backend).
- Icon in nav must be one already imported in sections.js (no new import churn).
