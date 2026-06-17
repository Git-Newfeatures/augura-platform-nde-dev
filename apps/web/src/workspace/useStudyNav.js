// useStudyNav — shared navigation for library surfaces so every "action" routes
// into the study workflow (unified flow). Targets the first available study,
// else starts a new study.
import { useNavigate } from 'react-router-dom'
import { useCollection } from './dataClient'
import { slugify } from '@/lib/utils'

export function useStudyNav() {
  const navigate = useNavigate()
  const { data: studies } = useCollection('studies')
  const firstId = studies[0]?.id

  return {
    navigate,
    studies,
    /** Open a workflow step on the first study, else start a new study. */
    openStep: (view) =>
      navigate(firstId ? `/studies/${firstId}/workflow/${view}` : '/studies/new'),
    /** Open a study by id or name; falls back to the first study. */
    openStudy: (nameOrId) => {
      const slug = slugify(nameOrId)
      const match = studies.find((s) => s.id === slug || s.id === nameOrId)
      const id = match?.id || firstId
      navigate(id ? `/studies/${id}` : '/studies/new')
    },
    newStudy: () => navigate('/studies/new'),
  }
}
