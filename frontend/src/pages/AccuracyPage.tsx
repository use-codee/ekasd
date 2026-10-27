import { useState } from 'react'
import type { Accuracy, Metadata } from '../types/api'
import { query } from '../api/client'
import { number, validClock, validDay } from '../api/format'
import { useRequest } from '../hooks/useRequest'
import { RequestState } from '../components/States'
import { BreakdownChart, WindChart } from '../components/Charts'
import { HourlyTable } from '../components/HourlyTable'

const primaryMetrics = [
  { key: 'mae_mw', label: 'Average miss', technical: 'MAE',
    explanation: 'Average size of the hourly forecast error, regardless of direction.' },
  { key: 'bias_mw', label: 'Over / under-forecast', technical: 'Signed bias', explanation: null },
  { key: 'p90_absolute_error_mw', label: '90th-percentile miss', technical: 'P90 absolute error',
    explanation: 'About 90% of historical hourly errors were no larger than this amount.' },
] as const

function biasExplanation(value: number | null): string {
  if (value === null) return 'Not available for this selection.'
  if (value > 0) return 'Wind was over-forecast by this amount on average.'
  if (value < 0) return 'Wind was under-forecast by this amount on average.'
  return 'Over- and under-forecasts balance on average; individual errors may remain.'
}

export function AccuracyPage({ meta, clock, setClock }: { meta: Metadata; clock: string; setClock: (value: string) => void }) {
  const [first, setFirst] = useState(meta.delivery_from)
  const [last, setLast] = useState(meta.delivery_to)
  const valid = validDay(first, meta.delivery_from, meta.delivery_to) && validDay(last, meta.delivery_from, meta.delivery_to) && first <= last && validClock(clock)
  const { data, ...state } = useRequest<Accuracy>(valid ? query('accuracy', { delivery_from: first, delivery_to: last, cutoff_time: clock }) : null)
  return <>
    <div className="page-heading"><div><p className="kicker">HISTORICAL PERFORMANCE</p><h1>Forecast accuracy</h1></div><p>{meta.source} · {meta.units} · {meta.timezone}</p></div>
    <div className="controls"><label>Delivery from<input type="date" value={first} min={meta.delivery_from} max={meta.delivery_to} onInput={e => setFirst(e.currentTarget.value)} /></label><label>Delivery to<input type="date" value={last} min={meta.delivery_from} max={meta.delivery_to} onInput={e => setLast(e.currentTarget.value)} /></label><label>D-1 decision cutoff · UTC<input type="time" step="60" value={clock} onInput={e => setClock(e.currentTarget.value)} /></label><p className="control-note">Applied separately to each delivery day.<br />Assumed timing, not verified gate closure.</p></div>
    {!valid && <p className="validation" role="alert">Choose an ordered delivery range within {meta.delivery_from}–{meta.delivery_to} and a valid HH:MM cutoff.</p>}
    <RequestState {...state} />
    {data && <>
      <div className="selection-strip"><span>Delivery <strong>{data.delivery_from} – {data.delivery_to}</strong></span><span>D-1 cutoff <strong>{data.cutoff_time} UTC</strong></span><span className="coverage">Paired hours <strong>{data.coverage.paired} / {data.coverage.expected}</strong></span></div>
      <section className="metric-strip" aria-label="Primary accuracy metrics">
        {primaryMetrics.map(({ key, label, technical, explanation }) => {
          const value = data.metrics[key]
          return <div className="metric" key={key}>
            <h2>{label}</h2><span className="metric-technical">{technical}</span>
            <p className="metric-value">{key === 'bias_mw' && value !== null && value > 0 ? '+' : ''}{number(value === 0 ? 0 : value)}{value !== null && <small>MW</small>}</p>
            <span className="metric-count">n = {data.coverage.paired} hours</span>
            <p className="metric-help">{key === 'bias_mw' ? biasExplanation(value) : explanation}</p>
          </div>
        })}
      </section>
      <details className="more-statistics">
        <summary>More statistics</summary>
        <div className="secondary-metrics">
          <div className="metric">
            <h2>RMSE</h2>
            <p className="metric-value">{number(data.metrics.rmse_mw)}{data.metrics.rmse_mw !== null && <small>MW</small>}</p>
            <span className="metric-count">n = {data.coverage.paired} hours</span>
            <p className="metric-help">Gives larger forecast errors more weight.</p>
          </div>
          <div className="metric">
            <h2>MAPE</h2>
            <p className="metric-value">{number(data.metrics.mape_percent)}{data.metrics.mape_percent !== null && <small>%</small>}</p>
            <span className="metric-count">n = {data.metrics.mape_eligible} hours</span>
            <p className="metric-help">Average hourly absolute error as a percentage of actual generation.</p>
            <p className="metric-help">Zero-actual hours excluded from MAPE: {data.metrics.mape_excluded_zero_actual}.</p>
          </div>
        </div>
      </details>
      <div className="coverage-line">Forecasts {data.coverage.forecasts}/{data.coverage.expected} · Actuals {data.coverage.actuals}/{data.coverage.expected} · Paired hours {data.coverage.paired}/{data.coverage.expected} · Excluded pairs {data.coverage.excluded}</div>
      {data.coverage.excluded > 0 && <p className="notice" role="status">Incomplete coverage: {data.coverage.missing_forecasts} missing forecasts; {data.coverage.missing_actuals} missing actuals. Only paired observations enter metrics.</p>}
      <section className="panel"><header className="panel-title"><h2>Forecast versus actual generation</h2><span>Hourly mean actuals · UTC</span></header>
        {data.coverage.forecasts || data.coverage.actuals ? <WindChart slots={data.slots} actual /> : <p className="state">No forecast or actual observations for this selection.</p>}
        <div className="chart-note">Error = forecast − actual. Positive bias means wind was over-forecast. Missing observations remain gaps.</div><HourlyTable slots={data.slots} actual />
      </section>
      <div className="breakdowns"><BreakdownChart title="Error by forecast horizon" groups={data.breakdowns.horizon} /><BreakdownChart title="Error by UTC delivery hour" groups={data.breakdowns.hour} /><BreakdownChart title="Error by delivery day" groups={data.breakdowns.day} /></div>
      <section className="context"><h2>Historical purchasing context</h2><p>{data.buffer.message}</p><p className="limitation">{data.diagnostic_limitation}</p></section>
      <details className="definitions"><summary>Metric definitions and assumptions</summary><p>Average miss (MAE) is mean absolute error; RMSE is the square root of mean squared error; over / under-forecast (signed bias) is mean forecast minus actual. The 90th-percentile miss (P90 absolute error) uses linear percentile interpolation. MAPE is the average of hourly absolute percentage errors: for each paired hour, absolute error divided by absolute actual, times 100. It is not a ratio of aggregated averages. Zero-actual hours are excluded only from MAPE. Null metrics are unavailable. Each hourly actual requires both distinct half-hours. All delivery dates and timestamps are UTC.</p></details>
    </>}
  </>
}
