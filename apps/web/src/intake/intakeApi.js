// Helpers pour le pipeline d'intake (upload → map → DQ), câblés sur le backend FastAPI.
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
