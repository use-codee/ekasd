import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, BarChart, Bar } from 'recharts'
import type { AccuracySlot, ForecastSlot, Group } from '../types/api'
import { day, hour, number, utc } from '../api/format'

function WindTooltip({ active, payload }: { active?: boolean; payload?: readonly { payload?: ForecastSlot & Partial<AccuracySlot> }[] }) {
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  return <div className="tooltip"><strong>{utc(row.startTime)}</strong><dl>
    <dt>Forecast</dt><dd>{number(row.forecast_mw)} MW</dd>
    {'actual_mw' in row && <><dt>Actual</dt><dd>{number(row.actual_mw)} MW</dd></>}
    <dt>Published</dt><dd>{utc(row.publish_time)}</dd>
    <dt>Horizon</dt><dd>{number(row.horizon_hours)} h</dd>
  </dl></div>
}
export function WindChart({ slots, actual = false }: { slots: ForecastSlot[] | AccuracySlot[]; actual?: boolean }) {
  const multiple = slots.length > 24
  return <div className="chart" role="img" aria-label={`${actual ? 'Forecast versus actual' : 'Decision forecast'} wind generation in MW by UTC hour. Values and publications available in the hourly table below.`}>
    <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 900, height: 300 }}>
      <LineChart data={slots} margin={{ top: 16, right: 16, bottom: 12, left: 12 }} accessibilityLayer>
        <CartesianGrid stroke="#e4e8ef" vertical={false} />
        <XAxis dataKey="startTime" tickFormatter={v => multiple ? day(v) : hour(v)} minTickGap={45} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis width={60} tickFormatter={v => `${number(v / 1000, 1)}k`} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} label={{ value: 'MW', position: 'insideTopLeft', offset: -12, fontSize: 11 }} />
        <Tooltip content={<WindTooltip />} />
        <Legend verticalAlign="top" align="right" iconType="plainline" wrapperStyle={{ fontSize: 12, paddingBottom: 14 }} />
        <Line name="Forecast" dataKey="forecast_mw" type="linear" stroke="#2758be" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
        {actual && <Line name="Actual" dataKey="actual_mw" type="linear" stroke="#576979" strokeDasharray="5 3" strokeWidth={1.5} dot={false} connectNulls={false} isAnimationActive={false} />}
      </LineChart>
    </ResponsiveContainer>
  </div>
}
export function BreakdownChart({ title, groups }: { title: string; groups: Group[] }) {
  const data = groups.map(g => ({ label: g.label, mae: g.metrics.mae_mw, count: g.coverage.paired, bias: g.metrics.bias_mw }))
  return <section className="panel breakdown"><header className="panel-title"><h3>{title}</h3><span>MAE · MW</span></header>
    <div className="small-chart" role="img" aria-label={`${title}: mean absolute error in MW. Accessible values in the breakdown table.`}>
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 360, height: 180 }}>
        <BarChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 0 }} accessibilityLayer>
          <CartesianGrid stroke="#e4e8ef" vertical={false} />
          <XAxis dataKey="label" tickFormatter={v => /^2026-/.test(v) ? v.slice(8) : v.replace(':00', '')} tick={{ fontSize: 10 }} minTickGap={12} axisLine={false} tickLine={false} />
          <YAxis width={45} tick={{ fontSize: 10 }} tickFormatter={v => `${number(v / 1000, 1)}k`} axisLine={false} tickLine={false} />
          <Tooltip formatter={v => `${number(typeof v === 'number' ? v : null)} MW`} labelFormatter={(_, payload) => { const p = payload?.[0]?.payload; return p ? `${p.label} · n=${p.count} · bias ${number(p.bias)} MW` : '' }} />
          <Bar dataKey="mae" name="MAE" fill="#5276bb" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
    <details><summary>View values and sample counts</summary><div className="table-scroll"><table><caption>{title} statistics</caption><thead><tr><th>Bucket / UTC</th><th>MAE MW</th><th>Bias MW</th><th>Pairs</th></tr></thead><tbody>{groups.map(g => <tr key={g.label}><th>{g.label}</th><td>{number(g.metrics.mae_mw)}</td><td>{number(g.metrics.bias_mw)}</td><td>{g.coverage.paired}</td></tr>)}</tbody></table></div></details>
  </section>
}
