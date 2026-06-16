export function EmptyState({ icon: Icon, title, subtitle, cta }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card px-8 py-16 text-center">
      {Icon && <Icon className="mb-3 h-8 w-8 text-muted-foreground/60" />}
      <div className="text-sm font-semibold text-foreground">{title}</div>
      {subtitle && (
        <div className="mt-1 max-w-sm text-xs text-muted-foreground">{subtitle}</div>
      )}
      {cta && <div className="mt-4">{cta}</div>}
    </div>
  )
}
