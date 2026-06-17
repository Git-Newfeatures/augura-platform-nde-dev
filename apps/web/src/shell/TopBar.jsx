import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, Bell } from 'lucide-react'
import { supabase } from '@/supabase'
import { apiJson } from '@/api'
import AuguraAdminDashboard from '@/AuguraAdminDashboard'

const NOTIF_LABEL = {
  'study.created': 'Study created',
  'study.updated': 'Study updated',
  'simulation.requested': 'Simulation requested',
  'simulation.bootstrap.succeeded': 'Simulation completed',
  'document.requested': 'Dossier requested',
  'document.generated': 'Dossier ready',
  'cohort.imported': 'Cohort imported',
}
const notifRoute = (t) =>
  t.startsWith('simulation') ? '/runs'
    : t.startsWith('document') ? '/dossiers'
    : t.startsWith('cohort') ? '/datasets'
    : '/studies'
const notifWhen = (iso) => {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  return hrs < 24 ? `${hrs}h ago` : `${Math.round(hrs / 24)}d ago`
}

// Evidence Workspace top bar: brand cluster + center ⌘K search pill + right cluster
// (bell, user pill). Full-bleed sticky frosted 58px header.
export function TopBar({ email = '', onSearch }) {
  const navigate = useNavigate()
  const initial = email ? email[0].toUpperCase() : '·'
  const name = email ? email.split('@')[0] : 'Account'
  const [showAdmin, setShowAdmin] = useState(false)
  const [menu, setMenu] = useState(null) // null | 'bell' | 'account'
  const isAdmin = email.endsWith('@augura.health')
  const [notifs, setNotifs] = useState([])
  useEffect(() => {
    let alive = true
    apiJson('/analytics/activity?limit=8')
      .then((evs) => {
        if (!alive) return
        setNotifs((evs || []).map((e) => ({
          id: e.id,
          title: NOTIF_LABEL[e.event_type] || e.event_type,
          sub: [e.metadata?.name || e.metadata?.cohort_name || e.metadata?.type, notifWhen(e.created_at)]
            .filter(Boolean).join(' · '),
          to: notifRoute(e.event_type),
        })))
      })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  function signOut() {
    setMenu(null)
    supabase.auth.signOut().finally(() => {
      try { sessionStorage.clear() } catch { /* ignore */ }
      window.location.href = '/'
    })
  }

  return (
    <>
    <header className="sticky top-0 z-40 flex h-[58px] items-center gap-3 border-b border-[rgba(0,0,0,0.07)] bg-[rgba(246,244,241,0.85)] px-4 backdrop-blur-[10px] md:gap-[18px] md:px-[22px]">
      {/* Brand — wordmark always visible, module tag hides <lg to free width */}
      <button onClick={() => navigate('/studies')} className="flex shrink-0 cursor-pointer items-center gap-2.5">
        <img src="/augura-wordmark-emerald.svg" alt="Augura" className="h-[17px]" />
        <span className="mx-0.5 hidden h-[18px] w-px bg-[rgba(0,0,0,0.10)] lg:inline-block" />
        <span className="hidden font-mono text-[10.5px] uppercase tracking-[.1em] text-[rgba(0,0,0,0.40)] lg:inline">Module 1 · EGDI</span>
      </button>

      {/* Center search pill (md+): min-w-0 + truncate so it never wraps into a blob */}
      <button
        onClick={onSearch}
        className="mx-auto hidden min-w-0 max-w-[460px] flex-1 cursor-text items-center gap-2.5 rounded-full border border-[rgba(0,0,0,0.10)] bg-white px-3.5 py-2 text-[13.5px] text-[rgba(0,0,0,0.40)] md:flex"
      >
        <Search className="h-4 w-4 shrink-0" />
        <span className="flex-1 truncate text-left">Search studies, datasets, variables…</span>
        <kbd className="hidden shrink-0 rounded-[5px] border border-[rgba(0,0,0,0.10)] px-1.5 py-px font-mono text-[11px] lg:inline">⌘K</kbd>
      </button>
      {/* Mobile spacer keeps the right cluster pinned right when the pill is hidden */}
      <div className="flex-1 md:hidden" />

      {/* Right cluster */}
      <div className="flex shrink-0 items-center gap-2 md:gap-3">
        {/* Compact search trigger below md (replaces the full pill) */}
        <button
          onClick={onSearch}
          aria-label="Search"
          className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-[rgba(0,0,0,0.07)] bg-white text-[rgba(0,0,0,0.55)] md:hidden"
        >
          <Search className="h-[17px] w-[17px]" />
        </button>
        {isAdmin && (
          <button
            onClick={() => setShowAdmin(true)}
            className="hidden rounded-md border border-[rgba(0,0,0,0.10)] bg-white px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-[.08em] text-[rgba(0,0,0,0.45)] sm:block"
          >
            Admin
          </button>
        )}
        {/* Notifications */}
        <div className="relative">
          <button
            onClick={() => setMenu(menu === 'bell' ? null : 'bell')}
            className="relative flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-[rgba(0,0,0,0.07)] bg-white text-[rgba(0,0,0,0.55)]"
            aria-label="Notifications"
          >
            <Bell className="h-[17px] w-[17px]" />
            {notifs.length > 0 && (
              <span className="absolute right-2 top-[7px] h-1.5 w-1.5 rounded-full border-[1.5px] border-white bg-[var(--carmine)]" />
            )}
          </button>
          {menu === 'bell' && (
            <div className="absolute right-0 top-[42px] z-50 w-[290px] rounded-xl border border-border bg-card p-1.5 shadow-lg">
              <div className="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/70">Notifications</div>
              {notifs.length === 0 ? (
                <div className="px-2.5 py-3 text-[13px] text-muted-foreground">You're all caught up.</div>
              ) : (
                notifs.map((n) => (
                  <button
                    key={n.id}
                    onClick={() => { setMenu(null); navigate(n.to) }}
                    className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-muted/50"
                  >
                    <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[#B98900]" />
                    <span className="min-w-0">
                      <span className="block text-[13px] font-medium leading-snug text-foreground">{n.title}</span>
                      <span className="block text-[11.5px] text-muted-foreground">{n.sub}</span>
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Account */}
        <div className="relative">
          <button
            onClick={() => setMenu(menu === 'account' ? null : 'account')}
            className="flex items-center gap-2.5 rounded-full py-1 pl-1 pr-1 transition-colors hover:bg-black/[0.03] sm:pl-3"
          >
            <span className="hidden text-[13.5px] font-medium text-[rgba(0,0,0,0.74)] sm:inline">{name}</span>
            <span className="flex h-[30px] w-[30px] items-center justify-center rounded-full bg-primary text-[12.5px] font-semibold text-white">
              {initial}
            </span>
          </button>
          {menu === 'account' && (
            <div className="absolute right-0 top-[42px] z-50 w-56 rounded-xl border border-border bg-card p-1.5 shadow-lg">
              <div className="px-2.5 py-2">
                <div className="text-[13px] font-medium text-foreground">{name}</div>
                <div className="truncate text-[11.5px] text-muted-foreground">{email}</div>
              </div>
              <div className="my-1 border-t border-border" />
              {isAdmin && (
                <button
                  onClick={() => { setMenu(null); setShowAdmin(true) }}
                  className="w-full rounded-lg px-2.5 py-2 text-left text-[13px] text-foreground transition-colors hover:bg-muted/50"
                >
                  Admin dashboard
                </button>
              )}
              <button
                onClick={signOut}
                className="w-full rounded-lg px-2.5 py-2 text-left text-[13px] text-[#C0392B] transition-colors hover:bg-[#C0392B]/[0.06]"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
    {menu && <div className="fixed inset-0 z-30" onClick={() => setMenu(null)} />}
    {showAdmin && <AuguraAdminDashboard onClose={() => setShowAdmin(false)} />}
    </>
  )
}
