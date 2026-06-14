import { ClipboardList, Database, Variable } from 'lucide-react'
import { isMockEnabled } from '@/mocks/mockMode'
import { getAllStudies } from '@/cockpit/cockpitData'

// Search groups for the ⌘K overlay. These are demo fixtures, so they only appear
// when the Demo-data toggle is ON; with it OFF, search returns no canned results.
// Studies come from the same source as the dashboard (incl. ones you created).
// Each item: { icon, title, sub, to }.
export function getSearchGroups() {
  if (!isMockEnabled()) return []
  return [
    {
      label: 'Studies',
      items: getAllStudies().map((s) => ({
        icon: ClipboardList,
        title: s.name,
        sub: s.tagline,
        to: `/studies/${s.id}`,
      })),
    },
    {
      label: 'Data',
      items: [
        { icon: Database, title: 'lucis_study_cohort', sub: '824 rows · 2 soft flags', to: '/datasets' },
        { icon: Database, title: 'bloomlife_rpm_2025', sub: '1,240 rows · verified', to: '/datasets' },
      ],
    },
    {
      label: 'Variables',
      items: [
        { icon: Variable, title: 'HbA1c_12m', sub: 'Outcome · continuous', to: '/variables' },
        { icon: Variable, title: 'rec_adherence_pct', sub: 'Exposure · primary mechanism', to: '/variables' },
      ],
    },
  ]
}
