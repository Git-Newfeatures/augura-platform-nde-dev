import { useState } from 'react'
import {
  Database,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { useStudyNav } from '@/workspace/useStudyNav'
import { Loading, EmptyState } from '@/workspace/CollectionStates'

// status → Badge props
function StatusBadge({ d }) {
  if (d.state === 'verified') {
    return (
      <Badge variant="secondary" className="text-primary">
        Verified
      </Badge>
    )
  }
  if (d.state === 'flag') {
    return (
      <Badge
        variant="outline"
        className="text-[#B98900] border-[#B98900]/30"
      >
        {d.flags ?? 2} flags
      </Badge>
    )
  }
  if (d.state === 'draft') {
    return (
      <Badge
        variant="outline"
        className="text-[#3172B0] border-[#3172B0]/30"
      >
        Draft
      </Badge>
    )
  }
  // locked
  return (
    <Badge variant="outline" className="text-muted-foreground">
      Locked
    </Badge>
  )
}

// ── Dataset detail (inline view that replaces the list) ───────────────────────
function DatasetDetail({ d, onBack, onOpenStudy }) {
  return (
    <div className="flex flex-col gap-4">
      {/* Back + study link */}
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-[12.5px] font-medium text-primary transition-colors hover:text-primary/80"
        >
          <ArrowLeft size={14} /> Back to datasets
        </button>
        <Button variant="outline" size="sm" onClick={onOpenStudy} className="text-xs font-medium">
          Open study <ExternalLink className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Dataset header + inline profile stats */}
      <Card className="gap-0 rounded-xl border p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3.5">
            <span className="flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[9px] border border-border bg-secondary text-muted-foreground">
              <Database size={17} />
            </span>
            <div className="min-w-0">
              <div className="font-mono text-sm text-foreground">{d.name}</div>
              <div className="mt-0.5 text-[12px] text-muted-foreground/70">
                {d.study} · updated {d.when}
              </div>
            </div>
          </div>
          <StatusBadge d={d} />
        </div>
        <div className="mt-4 flex flex-wrap gap-x-7 gap-y-2 border-t border-border pt-3.5">
          {[
            ['Rows', d.rows, 'text-foreground'],
            ['Columns', d.cols, 'text-foreground'],
          ].map(([label, value, tone]) => (
            <div key={label} className="flex items-baseline gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">{label}</span>
              <span className={`text-[13px] font-semibold ${tone}`}>{value}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Detailed dataset metadata (privacy, mapping, validation, lineage) is not
          wired to a live source yet — show an honest empty state. */}
      <EmptyState
        icon={Database}
        title="No detailed metadata yet"
        subtitle="Detailed dataset metadata will appear here once available."
      />
    </div>
  )
}

export function DatasetsPage() {
  const { data: datasets, loading } = useCollection('datasets')
  const { openStudy } = useStudyNav()
  const [selectedDataset, setSelectedDataset] = useState(null)

  // Detail view replaces the list (sketch: "← Back to datasets" header).
  if (selectedDataset) {
    return (
      <WorkspacePage
        eyebrow="Library · Cohorts"
        title="Dataset"
        sub={`${selectedDataset.name} · ${selectedDataset.rows} rows · ${selectedDataset.cols} cols`}
      >
        <DatasetDetail
          d={selectedDataset}
          onBack={() => setSelectedDataset(null)}
          onOpenStudy={() => openStudy(selectedDataset.study)}
        />
      </WorkspacePage>
    )
  }

  return (
    <WorkspacePage
      eyebrow="Library · Cohorts"
      title="Data"
      sub={loading ? 'Loading…' : `${datasets.length} dataset${datasets.length === 1 ? '' : 's'} across your studies`}
    >
      {loading ? (
        <Loading />
      ) : datasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets yet"
          subtitle="Datasets registered against your studies will appear here. Connect a data source to get started."
        />
      ) : (
        <Card className="gap-0 px-[18px] py-1">
          {datasets.map((d, i) => (
            <div
              key={d.id}
              onClick={() => setSelectedDataset(d)}
              className={`flex cursor-pointer items-center gap-3.5 py-[15px] transition-colors hover:bg-muted/30 ${i === datasets.length - 1 ? '' : 'border-b border-border'}`}
            >
              {/* Icon chip */}
              <span className="flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-[9px] border border-border bg-secondary text-muted-foreground">
                <Database size={17} />
              </span>
              {/* Name + meta */}
              <div className="min-w-0 flex-1">
                <div className="font-mono text-sm text-foreground">{d.name}</div>
                <div className="mt-0.5 text-[12px] text-muted-foreground/70">
                  {d.study} · updated {d.when}
                </div>
              </div>
              {/* Rows × cols */}
              <div className="w-32 flex-shrink-0 text-right font-mono text-[12.5px] text-muted-foreground">
                {d.rows} rows · {d.cols} cols
              </div>
              {/* Status badge */}
              <div className="flex w-24 flex-shrink-0 justify-end">
                <StatusBadge d={d} />
              </div>
              {/* Arrow */}
              <ArrowRight size={15} className="flex-shrink-0 text-muted-foreground/30" />
            </div>
          ))}
        </Card>
      )}
    </WorkspacePage>
  )
}
