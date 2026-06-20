import { useState } from 'react'
import { Target, Search as SearchIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SubTabs } from '@/cockpit/SubTabs'
import { WorkspacePage } from '@/workspace/WorkspacePage'
import { useCollection } from '@/workspace/dataClient'
import { Loading } from '@/workspace/CollectionStates'
import { openSearch } from '@/shell/searchBus'
import { AdHocQuery } from '@/workspace/literature/AdHocQuery'
import { SemanticSearch } from '@/workspace/literature/SemanticSearch'

export function CorpusPage() {
  const { data: sources, loading } = useCollection('corpus_sources')
  const total = sources.reduce((sum, s) => sum + (s.count || 0), 0)
  const [sub, setSub] = useState('query')

  return (
    <WorkspacePage
      eyebrow="Evidence base"
      title="Literature"
      sub={
        loading
          ? 'Loading…'
          : total
            ? `${total.toLocaleString()} indexed documents across ${sources.length} sources`
            : 'Tenant-wide evidence knowledge base'
      }
      action={<Button variant="outline" onClick={openSearch}>Search</Button>}
    >
      {loading && sources.length === 0 ? (
        <Loading />
      ) : (
        <>
          <SubTabs
            tabs={[
              { id: 'query',   label: 'Ad-hoc query',  icon: <SearchIcon size={14} /> },
              { id: 'matches', label: 'Study matches', icon: <Target size={14} /> },
            ]}
            active={sub}
            onChange={setSub}
          />
          {sub === 'query' && <AdHocQuery />}
          {sub === 'matches' && <SemanticSearch />}
        </>
      )}
    </WorkspacePage>
  )
}
