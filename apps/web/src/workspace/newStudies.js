// newStudies.js — local store for studies created via the New-study flow.
// Persists in localStorage so a created study keeps its identity across reloads and
// shows up on the dashboard (works in both demo and real mode). A production build
// would insert a `studies` row instead; this keeps the flow functional without a backend.
const KEY = 'augura_new_studies'

export function slugify(name) {
  return (
    String(name || '')
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '') || 'study'
  )
}

export function getNewStudies() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}')
  } catch {
    return {}
  }
}

export function getNewStudy(id) {
  return getNewStudies()[id] || null
}

export function addNewStudy(study) {
  const all = getNewStudies()
  all[study.id] = { ...study, createdAt: study.createdAt ?? Date.now() }
  try {
    localStorage.setItem(KEY, JSON.stringify(all))
  } catch {
    /* localStorage unavailable — the navigate still works, just not persisted */
  }
  return all[study.id]
}
