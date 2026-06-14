// Tiny event bus so any surface can open the ⌘K search overlay (owned by AppShell).
const EVT = 'augura:open-search'
export function openSearch() {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(EVT))
}
export function onOpenSearch(handler) {
  if (typeof window === 'undefined') return () => {}
  window.addEventListener(EVT, handler)
  return () => window.removeEventListener(EVT, handler)
}
