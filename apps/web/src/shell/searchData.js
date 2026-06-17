// Search groups for the ⌘K overlay — aggregated live from the backend (studies,
// datasets, dossiers) through the authenticated apiJson helper. Each item is
// { icon, title, sub, to }. Errors degrade to an empty group (overlay shows "No matches").
import { FlaskConical, Database, FileText } from 'lucide-react'
import { apiJson } from '@/api'

const DOC_LABEL = { protocol: 'Study protocol', report: 'Evidence report' }

export async function fetchSearchGroups() {
  const [studies, datasets, documents] = await Promise.all([
    apiJson('/studies').catch(() => []),
    apiJson('/datasets').catch(() => []),
    apiJson('/documents').catch(() => []),
  ])

  const groups = []

  if (studies?.length) {
    groups.push({
      label: 'Studies',
      items: studies.map((s) => ({
        icon: FlaskConical,
        title: s.name,
        sub: s.tagline || s.framework || 'Study',
        to: `/studies/${s.id}`,
      })),
    })
  }

  if (datasets?.length) {
    groups.push({
      label: 'Datasets',
      items: datasets.map((d) => ({
        icon: Database,
        title: d.name,
        sub: d.row_count != null ? `${Number(d.row_count).toLocaleString()} rows` : 'Dataset',
        to: '/datasets',
      })),
    })
  }

  if (documents?.length) {
    groups.push({
      label: 'Dossiers',
      items: documents.map((g) => ({
        icon: FileText,
        title: DOC_LABEL[g.type] || g.type,
        sub: g.status === 'ready' ? 'Ready' : 'Draft',
        to: '/dossiers',
      })),
    })
  }

  return groups
}

// Backward-compatible synchronous accessor (no longer the data source).
export function getSearchGroups() {
  return []
}
