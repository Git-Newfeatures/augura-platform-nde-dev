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

// Upload de plusieurs fichiers — un dataset par fichier. Séquentiel (évite N POST
// multipart concurrents vers Modal) et déterministe pour la progression. Une erreur
// sur un fichier n'arrête pas les autres. Renvoie { ok: [résultats], failed: [{ name, message }] }.
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
