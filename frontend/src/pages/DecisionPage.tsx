import { useState } from 'react'
import type { Decision, Metadata } from '../types/api'
import { query } from '../api/client'
import { number, utc, validClock, validDay } from '../api/format'
import { useRequest } from '../hooks/useRequest'
import { RequestState } from '../components/States'
import { WindChart } from '../components/Charts'
import { HourlyTable } from '../components/HourlyTable'

export function DecisionPage({ meta, clock, setClock }: { meta: Metadata; clock: string; setClock: (value: string) => void }) {
  const [delivery, setDelivery] = useState(meta.delivery_from)
  const valid = validDay(delivery, meta.delivery_from, meta.delivery_to) && validClock(clock)
  const { data, ...state } = useRequest<Decision>(valid ? query('forecasts', { delivery_date: delivery, cutoff_time: clock }) : null)
  const publications = data?.slots.map(s => s.publish_time).filter((v): v is string => v !== null).sort() ?? []
  return <>
    <div className="page-heading"><div><p className="kicker">HISTORICAL DECISION</p><h1>Wind available at the cutoff</h1></div><p>{meta.source} · {meta.units} · {meta.timezone}</p></div>
    <div className="controls"><label>Delivery day<input type="date" value={delivery} min={meta.delivery_from} max={meta.delivery_to} onInput={e => setDelivery(e.currentTarget.value)} /></label><label>D-1 decision cutoff · UTC<input type="time" step="60" value={clock} onInput={e => setClock(e.currentTarget.value)} /></label><p className="control-note">Decision dates {meta.decision_from}–{meta.decision_to}<br />Cutoff is assumed decision timing, not verified gate closure.</p></div>
    {!valid && <p role="alert" className="validation">Choose a supported delivery day and a cutoff in HH:MM format.</p>}
    <RequestState {...state} />
    {data && <>
      <div className="selection-strip"><span>Decision date <strong>{data.decision_date}</strong></span><span>Information cutoff <strong>{utc(data.cutoff_utc)}</strong></span><span className="coverage">Forecast coverage <strong>{data.coverage.forecasts} / {data.coverage.expected} hours</strong></span></div>
      {data.coverage.missing_forecasts > 0 && <p role="status" className="notice">{data.coverage.missing_forecasts} forecast hours unavailable. Gaps are preserved.</p>}
      <section className="panel"><header className="panel-title"><h2>Day-ahead wind forecast</h2><span>Delivery {data.delivery_date} · UTC</span></header>
        {data.coverage.forecasts ? <WindChart slots={data.slots} /> : <p className="state">No eligible forecasts for this cutoff.</p>}
        <div className="chart-note"><span>Latest eligible publication selected independently for each hour.</span><span>Publication range: {publications.length ? `${utc(publications[0])} – ${utc(publications.at(-1)!)}` : 'Unavailable'}</span></div>
        <HourlyTable slots={data.slots} />
      </section>
      <div className="method-note"><strong>Read this view</strong><p>Forecasts use only publications available by the D-1 cutoff. Each target timestamp begins a one-hour interval. Horizon is measured from its selected publication, not the cutoff. No actual generation is shown here.</p><span>Horizon range: {number(data.slots.reduce<number | null>((v, s) => s.horizon_hours == null ? v : v == null ? s.horizon_hours : Math.min(v, s.horizon_hours), null))}–{number(data.slots.reduce<number | null>((v, s) => s.horizon_hours == null ? v : v == null ? s.horizon_hours : Math.max(v, s.horizon_hours), null))} h</span></div>
    </>}
  </>
}
