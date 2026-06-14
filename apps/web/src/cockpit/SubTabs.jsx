import { cn } from '@/lib/utils'

// Secondary tab bar shown INSIDE a workflow step (mirrors the sketch's sub-tabs,
// e.g. Verification → Population / Outcomes / Intervention / Missing data).
// tabs: [{ id, label, icon?, badge? }]
export function SubTabs({ tabs, active, onChange, className }) {
  return (
    <div className={cn('mb-5 flex flex-wrap gap-0.5 border-b border-border', className)}>
      {tabs.map((t) => {
        const on = active === t.id
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={cn(
              '-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3.5 py-2 text-[12.5px] font-medium transition-colors',
              on
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.icon}
            {t.label}
            {t.badge != null && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-px text-[10px] font-semibold',
                  on ? 'bg-secondary text-primary' : 'bg-muted text-muted-foreground',
                )}
              >
                {t.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
