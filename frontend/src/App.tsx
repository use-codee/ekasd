import { useState } from 'react'
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { createQueryClient } from './api/queryClient'
import type { Metadata } from './types/api'
import { useRequest } from './hooks/useRequest'
import { RequestState } from './components/States'
import { DecisionPage } from './pages/DecisionPage'
import { AccuracyPage } from './pages/AccuracyPage'

function Workspace({ meta, metadataState }: { meta: Metadata; metadataState: ReturnType<typeof useRequest<Metadata>> }) {
  const [view, setView] = useState<'decision' | 'accuracy'>('decision')
  const [clock, setClock] = useState(meta.default_cutoff)
  const [delivery, setDelivery] = useState(meta.delivery_from)
  const [first, setFirst] = useState(meta.delivery_from)
  const [last, setLast] = useState(meta.delivery_to)
  return <>
    <header className="topbar"><div className="brand"><span className="brand-mark" aria-hidden="true">≋</span><strong>Wind Decision</strong></div><nav aria-label="Main navigation"><button aria-current={view === 'decision' ? 'page' : undefined} onClick={() => setView('decision')}>Decision</button><button aria-current={view === 'accuracy' ? 'page' : undefined} onClick={() => setView('accuracy')}>Accuracy</button></nav><span className="source">{meta.source} <span>{meta.timezone}</span></span></header>
    <main>{metadataState.error && <RequestState {...metadataState} />} {view === 'decision' ? <DecisionPage delivery={delivery} setDelivery={setDelivery} meta={meta} clock={clock} setClock={setClock} /> : <AccuracyPage first={first} setFirst={setFirst} last={last} setLast={setLast} meta={meta} clock={clock} setClock={setClock} />}</main>
    <footer>Elexon WINDFOR / FUELHH WIND <span>Historical decision analysis · All times UTC</span></footer>
  </>
}
function Application() {
  const state = useRequest<Metadata>('metadata')
  const { data } = state
  if (!data) return <main><h1>Wind Decision</h1><RequestState {...state} /></main>
  return <Workspace meta={data} metadataState={state} />
}

export default function App({ queryClient }: { queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient())
  return <QueryClientProvider client={client}><Application /></QueryClientProvider>
}
