import { useState } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Check, X, ChevronDown, ChevronRight, ExternalLink, Undo2 } from 'lucide-react'
import { resultId } from './literatureClient'

const pubmedUrl = (pmid) => `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
const doiUrl = (doi) => `https://doi.org/${doi}`
const ctgovUrl = (nct) => `https://clinicaltrials.gov/study/${nct}`

// Dismissed → ligne repliée (conservé pour l'audit). Kept → carte pleine.
// readOnly (snapshot gelé) masque les actions.
export function ResultCard({ result, position, status, onKeep, onDismiss, readOnly }) {
  const [showAbstract, setShowAbstract] = useState(false)
  const isCtgov = result.source === 'ctgov'
  const kept = status === 'kept'
  const dismissed = status === 'dismissed'
  const id = resultId(result)

  if (dismissed && !readOnly) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2">
        <span className="min-w-0 truncate text-[12px] text-muted-foreground">
          Dismissed · <span className="font-mono">{id}</span> — {result.title}
        </span>
        <Button variant="ghost" size="sm" className="h-6 flex-shrink-0 px-2 text-[11px]" onClick={onDismiss}>
          <Undo2 size={12} /> Undo
        </Button>
      </div>
    )
  }

  return (
    <Card className={cn('gap-0 rounded-xl border p-4', kept && 'border-primary/50 bg-secondary/40', dismissed && readOnly && 'opacity-60')}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[11px] font-semibold text-muted-foreground">{position}.</span>
            <h4 className="text-[13.5px] font-semibold leading-snug">
              <a
                href={isCtgov ? ctgovUrl(result.nct_id) : pubmedUrl(result.pmid)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-foreground hover:text-primary hover:underline"
              >
                {result.title}
              </a>
            </h4>
          </div>
          {!isCtgov && result.authors?.length > 0 && (
            <div className="mt-1 truncate text-[11.5px] text-foreground/70">{formatAuthors(result.authors)}</div>
          )}
          <div className="mt-1 text-[11.5px] text-muted-foreground">
            {isCtgov ? (
              <>
                {result.status && <span className="font-medium">{titleCase(result.status)}</span>}
                {result.phase && <> · {result.phase.replace(/PHASE/gi, 'Phase ')}</>}
                {result.interventions?.length ? <> · {result.interventions.slice(0, 3).join(', ')}</> : null}
              </>
            ) : (
              <>
                {result.journal ? <span className="italic">{result.journal}</span> : null}
                {result.publication_date ? ` · ${result.publication_date}` : ''}
              </>
            )}
          </div>
        </div>
        {!readOnly && (
          <div className="flex flex-shrink-0 items-center gap-1.5">
            <Button variant={kept ? 'default' : 'outline'} size="sm" className="h-7 px-2.5 text-[12px]" onClick={onKeep} title={kept ? 'Kept — click to undo' : 'Keep this result'}>
              <Check size={13} /> {kept ? 'Kept' : 'Keep'}
            </Button>
            <Button variant="ghost" size="sm" className="h-7 px-2.5 text-[12px] text-muted-foreground" onClick={onDismiss} title="Dismiss">
              <X size={13} /> Dismiss
            </Button>
          </div>
        )}
        {readOnly && kept && <Badge variant="secondary" className="flex-shrink-0 text-[10.5px] text-primary">Kept</Badge>}
        {readOnly && dismissed && <Badge variant="outline" className="flex-shrink-0 text-[10.5px] text-muted-foreground">Dismissed</Badge>}
      </div>

      {isCtgov && result.conditions?.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {result.conditions.slice(0, 6).map((c) => (
            <Badge key={c} variant="outline" className="text-[10px] font-normal text-muted-foreground">{c}</Badge>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border pt-2.5 text-[11.5px]">
        {result.abstract && (
          <button type="button" onClick={() => setShowAbstract((s) => !s)} className="flex items-center gap-1 font-medium text-primary hover:underline">
            {showAbstract ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {isCtgov ? 'Summary' : 'Abstract'}
          </button>
        )}
        {isCtgov ? (
          <a href={ctgovUrl(result.nct_id)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
            ClinicalTrials.gov <span className="font-mono">{result.nct_id}</span> <ExternalLink size={11} />
          </a>
        ) : (
          <>
            <a href={pubmedUrl(result.pmid)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
              PubMed <span className="font-mono">{result.pmid}</span> <ExternalLink size={11} />
            </a>
            {result.doi && (
              <a href={doiUrl(result.doi)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-muted-foreground hover:text-foreground">
                DOI <ExternalLink size={11} />
              </a>
            )}
          </>
        )}
      </div>

      {result.rationale && (
        <p className="mt-2 rounded-md bg-secondary/30 px-2.5 py-1.5 text-[11.5px] italic leading-relaxed text-muted-foreground">
          <span className="font-medium not-italic text-foreground/70">Why: </span>{result.rationale}
        </p>
      )}
      {showAbstract && result.abstract && (
        <p className="mt-2 text-[12px] leading-relaxed text-foreground/75">{result.abstract}</p>
      )}
    </Card>
  )
}

function titleCase(s) {
  return String(s).toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// Liste d'auteurs : 3 premiers + « et al. » au-delà (forme citation type PubMed).
function formatAuthors(authors) {
  const list = authors.slice(0, 3).join(', ')
  return authors.length > 3 ? `${list}, et al.` : list
}
