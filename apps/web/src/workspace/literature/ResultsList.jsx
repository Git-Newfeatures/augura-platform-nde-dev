import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ResultCard } from './ResultCard'
import { resultId } from './literatureClient'
import { BookOpen, FlaskConical, AlertTriangle, Loader2 } from 'lucide-react'

const SOURCE_META = {
  pubmed: { label: 'PubMed', Icon: BookOpen },
  ctgov: { label: 'ClinicalTrials.gov', Icon: FlaskConical },
}

// Résultats groupés par source (un en-tête par source). `groups` est keyé par
// source → { results, note, error, loading }.
export function ResultsList({ sources, groups, statusFor, onKeep, onDismiss, readOnly }) {
  return (
    <div className="flex flex-col gap-4">
      {sources.map((source) => {
        const g = groups[source] || {}
        const meta = SOURCE_META[source] || { label: source, Icon: BookOpen }
        return (
          <div key={source} className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
              <meta.Icon size={15} className="text-primary" /> {meta.label}
              {g.results?.length > 0 && <Badge variant="secondary" className="font-mono text-[11px] text-primary">{g.results.length}</Badge>}
              {g.loading && <Loader2 size={13} className="animate-spin text-muted-foreground" />}
            </div>

            {g.error ? (
              <Card className="flex flex-row items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-[12px] text-destructive">
                <AlertTriangle size={14} className="mt-px flex-shrink-0" />
                <span>{meta.label} failed: {g.error}</span>
              </Card>
            ) : g.loading ? (
              <Card className="rounded-xl border border-border bg-muted/20 p-3 text-[12px] text-muted-foreground">Searching {meta.label}…</Card>
            ) : g.results?.length ? (
              g.results.map((r, i) => (
                <ResultCard
                  key={resultId(r) || i}
                  result={r}
                  position={i + 1}
                  status={statusFor(resultId(r))}
                  onKeep={() => onKeep(r)}
                  onDismiss={() => onDismiss(r)}
                  readOnly={readOnly}
                />
              ))
            ) : g.note ? (
              <Card className="rounded-xl border border-border bg-muted/20 p-3 text-[12px] text-muted-foreground">{g.note}</Card>
            ) : (
              <Card className="rounded-xl border border-border bg-muted/20 p-3 text-[12px] text-muted-foreground">No results from {meta.label}.</Card>
            )}
          </div>
        )
      })}
    </div>
  )
}
