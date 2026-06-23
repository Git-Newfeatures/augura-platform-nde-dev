// Helpers for the intake pipeline (upload → map → DQ), wired to the FastAPI backend.
import { apiFetch, apiJson } from '../api'

// Create ONE dataset from one or more CSV/Excel files (same columns, appended).
export async function uploadDataset(files, { name, studyId } = {}) {
  const fd = new FormData()
  for (const f of Array.from(files || [])) fd.append('files', f)
  if (name) fd.append('name', name)
  if (studyId) fd.append('study_id', studyId)
  const res = await apiFetch('/datasets/upload', { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`upload ${res.status}: ${(await res.text()).slice(0, 300)}`)
  return res.json() // { dataset, columns, files, warnings }
}

// Append more files to an existing dataset → re-profiled { dataset, columns, files, warnings }.
export async function addFiles(id, files) {
  const fd = new FormData()
  for (const f of Array.from(files || [])) fd.append('files', f)
  const res = await apiFetch(`/datasets/${id}/files`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`add files ${res.status}: ${(await res.text()).slice(0, 300)}`)
  return res.json()
}

export const removeFile = (id, fileId) =>
  apiJson(`/datasets/${id}/files/${fileId}`, { method: 'DELETE' })
export const listFiles = (id) => apiJson(`/datasets/${id}/files`)

// Parse a data dictionary file into a structured data model.
// → { format, source_kind: 'structured' | 'free_form_llm', entries, warnings }.
export async function parseDataDictionary(id, file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await apiFetch(`/datasets/${id}/data-dictionary`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(`data dictionary ${res.status}: ${(await res.text()).slice(0, 300)}`)
  return res.json()
}

export const mapDataset = (id) => apiJson(`/datasets/${id}/map`, { method: 'POST' })
export const runDq = (id) => apiJson(`/datasets/${id}/dq`, { method: 'POST' })
export const getDq = (id) => apiJson(`/datasets/${id}/dq`)
export const listColumns = (id) => apiJson(`/datasets/${id}/columns`)
