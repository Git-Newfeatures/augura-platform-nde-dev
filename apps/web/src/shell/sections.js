import {
  ClipboardList,
  Database,
  Library,
  Variable,
  Settings2,
  FileText,
} from 'lucide-react'

// Single source of truth for the top-level workspace navigation.
// `subtle` dims the tab (see sketch).
export const WORKSPACE_SECTIONS = [
  { id: 'studies',   label: 'Studies',            path: '/studies',   icon: ClipboardList },
  { id: 'datasets',  label: 'Data',               path: '/datasets',  icon: Database },
  { id: 'intake',    label: 'Intake',             path: '/intake',    icon: FileText },
  { id: 'corpus',    label: 'Literature',         path: '/corpus',    icon: Library },
  { id: 'variables', label: 'Variables & Models', path: '/variables', icon: Variable },
  { id: 'runs',      label: 'Audit',              path: '/runs',      icon: Settings2, subtle: true },
  { id: 'dossiers',  label: 'Dossiers',           path: '/dossiers',  icon: FileText },
]
