// cohortData.js — cohort reads via the FastAPI backend (JWT Bearer → tenant RLS).
//
// Replaces the old direct PostgREST reads of the cockpit views
// (`supabase.from('validation_members'/'validation_biomarkers').eq('tenant_id', TENANT_ID)`)
// which targeted nonexistent tables with a hard-coded tenant (RLS bypass).
// The backend resolves the tenant from the token; we fetch ALL columns and the
// views filter client-side (timepoint, group…). engagement_group is lowercase.
import { apiJson } from '@/api'

async function resolveCohortName(cohortName) {
  if (cohortName) return cohortName
  const cohorts = await apiJson('/datasets/cohorts').catch(() => [])
  return cohorts?.[0]?.cohort_name ?? null
}

/** { name, members[], biomarkers[] } for the given cohort (or the tenant's first one). */
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

/** Precomputed VALIDATED simulation results (read-model), tenant-scoped. */
export async function fetchSimulationResults(cohortName = '') {
  const q = cohortName ? `?cohort_name=${encodeURIComponent(cohortName)}` : ''
  return apiJson(`/simulations/results${q}`).catch(() => [])
}

// engagement_group is lowercase on the backend ('high'/'medium'/'low').
export const engagementGroup = (m) => (m?.engagement_group ?? '').toLowerCase()
export const isHighEngager = (m) => engagementGroup(m) === 'high'
