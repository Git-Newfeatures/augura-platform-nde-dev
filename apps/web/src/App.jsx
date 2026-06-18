import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { supabase } from './supabase'
import AuguraLogin from './AuguraLogin'
import ResetPassword from './ResetPassword'
import LucisApp from './LucisApp'
import { AppShell } from './shell/AppShell'
import { DatasetsPage } from './workspace/DatasetsPage'
import { CorpusPage } from './workspace/CorpusPage'
import { VariablesPage } from './workspace/VariablesPage'
import { CausalModelingPage } from './workspace/CausalModelingPage'
import { SemanticLayerPage } from './workspace/SemanticLayerPage'
import { RunsPage } from './workspace/RunsPage'
import { DossiersPage } from './workspace/DossiersPage'
import { HomePage } from './workspace/HomePage'
import { NewStudyPage } from './workspace/NewStudyPage'
import IntakeApp from './views/intake/IntakeApp'

function AuthenticatedApp() {
  const [session, setSession] = useState(undefined)

  useEffect(() => {
    // One-time cleanup of a legacy session key (formerly run during render).
    sessionStorage.removeItem('lucis_session_v2')

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session ?? null)
    })
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_IN') {
        sessionStorage.clear()
        supabase.from('usage_events').insert({
          user_id: session.user.id,
          event_type: 'login',
          metadata: { route: window.location.pathname },
        }).then(() => {}).catch(() => {})
      }
      setSession(session ?? null)
    })
    return () => subscription.unsubscribe()
  }, [])

  const hash = new URLSearchParams(window.location.hash.slice(1))
  if (hash.get('type') === 'recovery') return <ResetPassword />
  // Login gate: block the app shell until a Supabase session resolves.
  if (session === undefined) return null
  if (!session) return <AuguraLogin onSession={setSession} />

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/studies" replace />} />
        <Route path="/studies" element={<HomePage />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/intake" element={<IntakeApp />} />
        <Route path="/corpus" element={<CorpusPage />} />
        <Route path="/variables" element={<VariablesPage />} />
        <Route path="/causal" element={<CausalModelingPage />} />
        <Route path="/semantic" element={<SemanticLayerPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/dossiers" element={<DossiersPage />} />
        <Route path="/studies/new" element={<NewStudyPage />} />
        <Route path="/studies/:id/*" element={<LucisApp session={session} />} />
      </Route>
      {/* back-compat: old /project/:id links → /studies/:id */}
      <Route path="/project/:id/*" element={<RedirectToStudies />} />
    </Routes>
  )
}

function RedirectToStudies() {
  const { id } = useParams()
  const splat = useParams()['*'] || ''
  return <Navigate replace to={`/studies/${id}${splat ? '/' + splat : ''}`} />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthenticatedApp />
    </BrowserRouter>
  )
}
