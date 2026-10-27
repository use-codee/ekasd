import type { AccuracySlot, ForecastSlot } from '../types/api'
import { number, utc } from '../api/format'
export function HourlyTable({ slots, actual = false }: { slots: ForecastSlot[] | AccuracySlot[]; actual?: boolean }) {
  return <details className="hourly"><summary>Hourly data · {slots.length} UTC slots <span>Publication and horizon for each hour</span></summary>
    <div className="table-scroll"><table><caption>Hourly wind generation, MW. Missing observations are unavailable.</caption><thead><tr><th scope="col">Delivery hour UTC</th><th scope="col">Forecast MW</th>{actual && <><th scope="col">Actual MW</th><th scope="col">Error MW</th></>}<th scope="col">Published UTC</th><th scope="col">Horizon h</th></tr></thead>
      <tbody>{slots.map(s => <tr key={s.startTime}><th scope="row">{utc(s.startTime)}</th><td>{number(s.forecast_mw)}</td>{actual && <><td>{number((s as AccuracySlot).actual_mw)}</td><td>{number((s as AccuracySlot).error_mw)}</td></>}<td>{utc(s.publish_time)}</td><td>{number(s.horizon_hours)}</td></tr>)}</tbody></table></div>
  </details>
}
