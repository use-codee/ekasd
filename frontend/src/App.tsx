import { useState } from 'react'
import type { Metadata } from './types/api'
import { useRequest } from './hooks/useRequest'
import { RequestState } from './components/States'
import { DecisionPage } from './pages/DecisionPage'
import { AccuracyPage } from './pages/AccuracyPage'

function Workspace({ meta }: { meta: Metadata }) {
  const [view, setView] = useState<'decision' | 'accuracy'>('decision')
  const [clock, setClock] = useState(meta.default_cutoff)
  return <>
    <header className="topbar"><div className="brand"><span className="brand-mark" aria-hidden="true">≋</span><strong>Wind Decision</strong></div><nav aria-label="Main navigation"><button aria-current={view === 'decision' ? 'page' : undefined} onClick={() => setView('decision')}>Decision</button><button aria-current={view === 'accuracy' ? 'page' : undefined} onClick={() => setView('accuracy')}>Accuracy</button></nav><span className="source">{meta.source} <span>{meta.timezone}</span></span></header>
    <main>{view === 'decision' ? <DecisionPage meta={meta} clock={clock} setClock={setClock} /> : <AccuracyPage meta={meta} clock={clock} setClock={setClock} />}</main>
    <footer>Elexon WINDFOR / FUELHH WIND <span>Historical decision analysis · All times UTC</span></footer>
  </>
}
export default function App() {
  const { data, ...state } = useRequest<Metadata>('metadata')
  if (!data) return <main><h1>Wind Decision</h1><RequestState {...state} /></main>
  return <Workspace meta={data} />
}
