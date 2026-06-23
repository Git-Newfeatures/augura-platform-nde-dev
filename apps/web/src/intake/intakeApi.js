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

// Upload multiple files — one dataset per file. Sequential (avoids N concurrent
// multipart POSTs to Modal) and deterministic for progress. An error on one file
// does not stop the others. Returns { ok: [results], failed: [{ name, message }] }.
export async function uploadDatasets(files, { studyId, onProgress } = {}) {
  const list = Array.from(files || [])
  const ok = []
  const failed = []
  for (let i = 0; i < list.length; i++) {
    const file = list[i]
    onProgress?.(i, list.length, file.name)
    try {
      ok.push(await uploadDataset(file, { studyId }))
    } catch (e) {
      failed.push({ name: file.name, message: String(e?.message || e) })
    }
  }
  onProgress?.(list.length, list.length, null)
  return { ok, failed }
}

export const mapDataset = (id) => apiJson(`/datasets/${id}/map`, { method: 'POST' })
export const runDq = (id) => apiJson(`/datasets/${id}/dq`, { method: 'POST' })
export const getDq = (id) => apiJson(`/datasets/${id}/dq`)
export const listColumns = (id) => apiJson(`/datasets/${id}/columns`)
