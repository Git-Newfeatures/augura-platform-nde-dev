// apps/web — mode RÉEL uniquement (login Supabase + backend FastAPI).
// Pas de couche mock ici (lucis-dashboard reste la démo). Ce shim conserve l'API
// historique pour ne pas réécrire les ~10 sites d'import : isMockEnabled() renvoie
// toujours false, donc chaque vue prend le chemin réel.
import { useState } from 'react'

export function initAppMode() {}

export function isMockEnabled() {
  return false
}

export function setMockEnabled() {}

export function useMockMode() {
  const [enabled] = useState(false)
  return [enabled, () => {}]
}
