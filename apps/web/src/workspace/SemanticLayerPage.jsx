import { useState, useEffect } from 'react'
import { Library, Network, TriangleAlert } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { SubTabs } from '@/cockpit/SubTabs'
import { Loading, EmptyState } from '@/workspace/CollectionStates'
import { apiJson } from '@/api'

// Couche sémantique (port de la vue /semantic de Nico, recâblée sur le backend
// Quentin) : le catalogue de concepts (GET /semantic/concepts) + l'ontologie
// causale revue (GET /semantic/relations, subsystem B1).

// Renvoie { data, error } pour distinguer « 0 ligne en base » d'un échec réseau /
// 401 / 500 — sinon une erreur ressemble à un état vide et masque la vraie cause.
function useEndpoint(path) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const d = await apiJson(path)
        if (alive) setData(Array.isArray(d) ? d : [])
      } catch (e) {
        if (alive) setError(String(e?.message || e))
      }
    })()
    return () => {
      alive = false
    }
  }, [path])
  return { data, error }
}

function ErrorState({ path, error }) {
  return (
    <EmptyState
      icon={TriangleAlert}
      title="Couldn't load from the backend"
      subtitle={`GET ${path} failed — ${error}`}
    />
  )
}

function Concepts() {
  const { data: concepts, error } = useEndpoint('/semantic/concepts')
  if (error) return <ErrorState path="/semantic/concepts" error={error} />
  if (concepts == null) return <Loading />
  if (concepts.length === 0) {
    return (
      <EmptyState
        icon={Library}
        title="No taxonomy concepts in the live DB"
        subtitle="The endpoint responded with 0 rows. Apply the taxonomy seed (apps/api/supabase/seed.sql) to the live public schema behind Modal."
      />
    )
  }
  return (
    <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Concept</th>
            <th className="px-4 py-2.5 font-medium">Domain</th>
            <th className="px-4 py-2.5 font-medium text-right">Layer</th>
            <th className="px-4 py-2.5 font-medium">Type</th>
            <th className="px-4 py-2.5 font-medium">Unit</th>
            <th className="px-4 py-2.5 font-medium">Role</th>
          </tr>
        </thead>
        <tbody>
          {concepts.map((c) => (
            <tr key={c.local_concept_id} className="border-b border-border/60 last:border-0">
              <td className="px-4 py-2 text-foreground">{c.concept_name}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.augura_domain}</td>
              <td className="px-4 py-2 text-right font-mono text-muted-foreground">{c.layer}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.value_type ?? '—'}</td>
              <td className="px-4 py-2 text-muted-foreground">{c.canonical_unit ?? '—'}</td>
              <td className="px-4 py-2">
                {c.dq_column_role ? (
                  <Badge variant="secondary" className="text-primary">
                    {c.dq_column_role}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function polarityBadge(polarity) {
  const up = polarity === 'increases'
  return (
    <Badge variant="outline" className={up ? 'text-emerald-700' : 'text-amber-700'}>
      {polarity}
    </Badge>
  )
}

function Relations() {
  const { data: relations, error: relError } = useEndpoint('/semantic/relations')
  const { data: concepts, error: cptError } = useEndpoint('/semantic/concepts')
  const error = relError || cptError
  if (error) return <ErrorState path="/semantic/relations" error={error} />
  if (relations == null || concepts == null) return <Loading />
  if (relations.length === 0) {
    return (
      <EmptyState
        icon={Network}
        title="No causal relations in the live DB"
        subtitle="The endpoint responded with 0 rows. Apply the B1 ontology seed (schema + seed + policies) to the live public schema behind Modal."
      />
    )
  }
  const nameOf = Object.fromEntries(concepts.map((c) => [c.local_concept_id, c.concept_name]))
  const label = (id) => nameOf[id] || id
  return (
    <Card className="gap-0 overflow-x-auto rounded-xl border p-0">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.05em] text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Subject</th>
            <th className="px-4 py-2.5 font-medium">Predicate</th>
            <th className="px-4 py-2.5 font-medium">Object</th>
            <th className="px-4 py-2.5 font-medium">Polarity</th>
            <th className="px-4 py-2.5 font-medium">Strength</th>
            <th className="px-4 py-2.5 font-medium">Mechanism</th>
          </tr>
        </thead>
        <tbody>
          {relations.map((r) => (
            <tr key={r.relation_id} className="border-b border-border/60 last:border-0">
              <td className="px-4 py-2 text-foreground">{label(r.subject_concept_id)}</td>
              <td className="px-4 py-2 font-mono text-[11.5px] text-muted-foreground">
                {r.predicate}
              </td>
              <td className="px-4 py-2 text-foreground">{label(r.object_concept_id)}</td>
              <td className="px-4 py-2">{polarityBadge(r.polarity)}</td>
              <td className="px-4 py-2 text-muted-foreground">{r.default_strength}</td>
              <td className="px-4 py-2 text-muted-foreground">{r.mechanism_summary || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

export function SemanticLayerPage() {
  const [sub, setSub] = useState('concepts')
  return (
    <WorkspacePage
      eyebrow="Knowledge"
      title="Semantic layer"
      sub="The governed taxonomy of clinical concepts and the reviewed causal ontology that grounds the DAG generator."
    >
      <SubTabs
        tabs={[
          { id: 'concepts', label: 'Concepts' },
          { id: 'relations', label: 'Causal relations' },
        ]}
        active={sub}
        onChange={setSub}
      />
      {sub === 'concepts' && <Concepts />}
      {sub === 'relations' && <Relations />}
    </WorkspacePage>
  )
}
