// Shared loading / empty rendering for demo-gated workspace collections.
export { EmptyState } from '@/components/EmptyState'

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center rounded-xl border border-dashed border-border bg-card px-8 py-16 text-sm text-muted-foreground">
      {label}
    </div>
  )
}
