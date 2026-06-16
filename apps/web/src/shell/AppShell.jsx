import { useEffect, useState } from 'react'
import { Outlet, useMatch } from 'react-router-dom'
import { supabase } from '@/supabase'
import { TopBar } from './TopBar'
import { WorkspaceNav } from './WorkspaceNav'
import { SearchOverlay } from './SearchOverlay'
import { onOpenSearch } from './searchBus'
import AuguraAssistant from '@/components/AuguraAssistant'

export function AppShell() {
  const [email, setEmail] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? '')
    })
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen((prev) => !prev)
      }
      if (e.key === 'Escape') setSearchOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Any surface can open the search via the search bus (e.g. "Search corpus").
  useEffect(() => onOpenSearch(() => setSearchOpen(true)), [])

  // Inside a specific study (/studies/:id/...) the study workspace owns the
  // second nav row + layout, so hide WorkspaceNav and the library padding.
  // Note: this matches /studies/lucis* but NOT the /studies index.
  const inStudy = useMatch('/studies/:id/*')

  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopBar email={email} onSearch={() => setSearchOpen(true)} />
      {inStudy ? (
        <Outlet />
      ) : (
        <div className="mx-auto max-w-[1280px] px-4 py-5 md:px-6 md:py-6">
          <WorkspaceNav />
          <Outlet />
        </div>
      )}
      {searchOpen && <SearchOverlay onClose={() => setSearchOpen(false)} />}
      <AuguraAssistant />
    </div>
  )
}
