// cohortData.js — lectures cohorte via le backend FastAPI (JWT Bearer → RLS tenant).
//
// Remplace les anciennes lectures PostgREST directes des vues cockpit
// (`supabase.from('validation_members'/'validation_biomarkers').eq('tenant_id', TENANT_ID)`)
// qui visaient des tables inexistantes avec un tenant codé en dur (bypass RLS).
// Le backend résout le tenant depuis le token ; on récupère TOUTES les colonnes et les
// vues filtrent côté client (timepoint, groupe…). engagement_group est en minuscule.
import { apiJson } from '@/api'

async function resolveCohortName(cohortName) {
  if (cohortName) return cohortName
  const cohorts = await apiJson('/datasets/cohorts').catch(() => [])
  return cohorts?.[0]?.cohort_name ?? null
}

/** { name, members[], biomarkers[] } pour la cohorte donnée (ou la première du tenant). */
export async function fetchCohort(cohortName = '') {
  const name = await resolveCohortName(cohortName)
  if (!name) return { name: null, members: [], biomarkers: [] }
  const enc = encodeURIComponent(name)
  const [members, biomarkers] = await Promise.all([
    apiJson(`/datasets/cohorts/${enc}/members`).catch(() => []),
    apiJson(`/datasets/cohorts/${enc}/biomarkers`).catch(() => []),
  ])
  return { name, members: members ?? [], biomarkers: biomarkers ?? [] }
}

/** Résultats de simulation VALIDATED précalculés (read-model), scopés tenant. */
export async function fetchSimulationResults(cohortName = '') {
  const q = cohortName ? `?cohort_name=${encodeURIComponent(cohortName)}` : ''
  return apiJson(`/simulations/results${q}`).catch(() => [])
}

// engagement_group est minuscule côté backend ('high'/'medium'/'low').
export const engagementGroup = (m) => (m?.engagement_group ?? '').toLowerCase()
export const isHighEngager = (m) => engagementGroup(m) === 'high'
