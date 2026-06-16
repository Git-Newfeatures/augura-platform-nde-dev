// WorkspacePage.jsx — shared header/shell for all list pages (Brick 2g)

export function WorkspacePage({ eyebrow, title, sub, action, children }) {
  return (
    <div className="min-w-0 mx-auto max-w-[1200px] px-5 py-9 pb-24">
      {/* Header */}
      <div className="mb-8 flex flex-wrap items-end justify-between gap-5">
        <div>
          <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-primary">
            {eyebrow}
          </div>
          <h1 className="mt-2 text-[22px] font-semibold leading-[24px] tracking-[-0.02em] text-foreground">
            {title}
          </h1>
          {sub && (
            <p className="mt-1.5 text-sm text-muted-foreground">{sub}</p>
          )}
        </div>
        {action && <div className="flex-shrink-0">{action}</div>}
      </div>
      {children}
    </div>
  )
}
