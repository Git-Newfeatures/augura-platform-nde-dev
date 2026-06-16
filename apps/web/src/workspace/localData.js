// localData.js — items added via the "Add …" buttons on the library pages
// (datasets, variables, corpus sources, dossiers, runs). Persisted in localStorage
// so they survive reloads and show up alongside the demo fixtures / Supabase rows.
// Demo-friendly; a production build would POST to the backend instead.
const KEY = 'augura_local_data'
export const DATA_CHANGED_EVENT = 'augura:data-changed'

function readAll() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}')
  } catch {
    return {}
  }
}

/** Items the user added to a collection (newest first). Always an array. */
export function getLocalItems(collection) {
  const all = readAll()
  return Array.isArray(all[collection]) ? all[collection] : []
}

/** Add an item to a collection, persist, and notify open views to re-read. */
export function addLocalItem(collection, item) {
  const all = readAll()
  const list = Array.isArray(all[collection]) ? all[collection] : []
  all[collection] = [item, ...list]
  try {
    localStorage.setItem(KEY, JSON.stringify(all))
  } catch {
    /* localStorage unavailable — the add still works for this render, just not persisted */
  }
  try {
    window.dispatchEvent(new Event(DATA_CHANGED_EVENT))
  } catch {
    /* no window (SSR) — ignore */
  }
  return item
}

// Short unique-ish id for a freshly-added row (used as the React key).
export function localId(prefix = 'item') {
  return `${prefix}-${Date.now().toString(36)}${Math.floor(performance.now()).toString(36)}`
}
