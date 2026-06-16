import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ArrowRight } from 'lucide-react'
import { getSearchGroups } from './searchData'

// ⌘K search overlay: scrim + card, autofocus input, grouped results, live filter,
// navigate-on-click. Closes on scrim click (Esc is handled by AppShell).
export function SearchOverlay({ onClose }) {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [q, setQ] = useState('')

  useEffect(() => { inputRef.current?.focus() }, [])

  const groups = getSearchGroups()
  const ql = q.toLowerCase()
  const filtered = groups
    .map((g) => ({ ...g, items: g.items.filter((it) => !q || (it.title + it.sub).toLowerCase().includes(ql)) }))
    .filter((g) => g.items.length)

  function go(to) { navigate(to); onClose() }

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-[80] flex items-start justify-center bg-[rgba(15,14,12,0.34)] pt-[12vh] backdrop-blur-[2px]"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[620px] max-w-[92vw] overflow-hidden rounded-[18px] border border-[rgba(0,0,0,0.07)] bg-white shadow-[0_12px_36px_rgba(0,0,0,0.13)]"
      >
        <div className="flex items-center gap-3 border-b border-[rgba(0,0,0,0.07)] px-5 py-4">
          <Search className="h-[19px] w-[19px] text-[rgba(0,0,0,0.40)]" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search studies, datasets, variables, documents…"
            className="flex-1 bg-transparent text-[16px] text-foreground outline-none placeholder:text-[rgba(0,0,0,0.40)]"
          />
          <kbd className="rounded-[5px] border border-[rgba(0,0,0,0.10)] px-1.5 py-0.5 font-mono text-[11px] text-[rgba(0,0,0,0.40)]">esc</kbd>
        </div>
        <div className="max-h-[420px] overflow-y-auto px-2 pb-3 pt-2">
          {filtered.map((g) => (
            <div key={g.label} className="mt-2">
              <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[.1em] text-[rgba(0,0,0,0.40)]">
                {g.label}
              </div>
              {g.items.map((it) => {
                const Icon = it.icon
                return (
                  <button
                    key={it.title}
                    onClick={() => go(it.to)}
                    className="flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition-colors hover:bg-[#F6F4F1]"
                  >
                    <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[7px] border border-[rgba(0,0,0,0.07)] bg-[#F6F4F1] text-[rgba(0,0,0,0.55)]">
                      <Icon className="h-[15px] w-[15px]" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[14px] font-medium text-foreground">{it.title}</div>
                      <div className="truncate text-[12px] text-[rgba(0,0,0,0.55)]">{it.sub}</div>
                    </div>
                    <ArrowRight className="h-[15px] w-[15px] shrink-0 text-[rgba(0,0,0,0.28)]" />
                  </button>
                )
              })}
            </div>
          ))}
          {!filtered.length && (
            <div className="p-7 text-center text-[14px] text-[rgba(0,0,0,0.40)]">No matches</div>
          )}
        </div>
      </div>
    </div>
  )
}
