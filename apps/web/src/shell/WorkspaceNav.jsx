import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { WORKSPACE_SECTIONS } from './sections'
import { cn } from '@/lib/utils'

export function WorkspaceNav() {
  // When the tab strip overflows (tablet), show a right-edge fade so the clipped
  // tab reads as "scroll for more" instead of looking broken.
  const ref = useRef(null)
  const [overflowing, setOverflowing] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const check = () => setOverflowing(el.scrollWidth > el.clientWidth + 1)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <nav
      ref={ref}
      className={cn(
        'no-scrollbar mb-5 flex items-center gap-0.5 overflow-x-auto border-b border-border',
        overflowing && 'scroll-fade-x',
      )}
    >
      {WORKSPACE_SECTIONS.map((s) => {
        const Icon = s.icon
        return (
          <NavLink
            key={s.id}
            to={s.path}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 whitespace-nowrap border-b-2 border-transparent px-[18px] py-[11px] text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
                isActive && 'border-primary font-semibold text-primary',
                s.subtle && !isActive && 'text-muted-foreground/70',
              )
            }
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{s.label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
