import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { request } from './api/client'
import { useRequest } from './hooks/useRequest'
import { utc } from './api/format'
import type { Accuracy, Decision, Metadata } from './types/api'

vi.mock('./api/client', async importOriginal => ({ ...await importOriginal<typeof import('./api/client')>(), request: vi.fn() }))
vi.mock('./components/Charts', () => ({ WindChart: () => <div>Wind chart</div>, BreakdownChart: ({ title }: { title: string }) => <div>{title}</div> }))
const meta: Metadata = { delivery_from: '2026-01-02', delivery_to: '2026-02-01', decision_from: '2026-01-01', decision_to: '2026-01-31', default_cutoff: '09:30', timezone: 'UTC', source: 'Elexon national WIND', units: 'MW', assumptions: [], provenance: { built_at: null, raw_chunks: 64, inputs: {} } }
const slots = Array.from({ length: 24 }, (_, h) => ({ startTime: `2026-01-02T${String(h).padStart(2, '0')}:00:00Z`, forecast_mw: 1000 + h, publish_time: '2026-01-01T09:30:00Z', horizon_hours: 14.5 + h, decision_cutoff: '2026-01-01T09:30:00Z' }))
const decision: Decision = { delivery_date: '2026-01-02', decision_date: '2026-01-01', cutoff_time: '09:30', cutoff_utc: '2026-01-01T09:30:00Z', timezone: 'UTC', coverage: { expected: 24, forecasts: 24, missing_forecasts: 0 }, slots, assumptions: [] }
const accuracy: Accuracy = { delivery_from: meta.delivery_from, delivery_to: meta.delivery_to, cutoff_time: '09:30', timezone: 'UTC', coverage: { expected: 24, forecasts: 24, actuals: 24, paired: 24, missing_actuals: 0, missing_forecasts: 0, excluded: 0 }, metrics: { mae_mw: 100, rmse_mw: 120, bias_mw: 80, mape_percent: 10, p90_absolute_error_mw: 150, mape_eligible: 24, mape_excluded_zero_actual: 0 }, slots: slots.map(s => ({ ...s, actual_mw: 900, error_mw: s.forecast_mw! - 900 })), breakdowns: { hour: [], day: [], horizon: [] }, buffer: { p90_mw: 150, bias_mw: 80, sample_count: 24, message: 'Indicative only: not a calibrated one-sided purchasing guarantee.' }, diagnostic_limitation: 'The cause remains unknown.' }
const mocked = vi.mocked(request)
beforeEach(() => {
  vi.clearAllMocks()
  mocked.mockImplementation(async path => (path === 'metadata' ? meta : path.startsWith('forecasts') ? decision : accuracy) as never)
})

it('loads metadata, shows decision-only UTC data and accessible publication table', async () => {
  render(<App />)
  expect(await screen.findByText('24 / 24 hours')).toBeInTheDocument()
  expect(screen.getByLabelText('Delivery day')).toHaveAttribute('min', meta.delivery_from)
  expect(screen.getByText('2026-01-01')).toBeInTheDocument()
  expect(screen.getAllByText(/01 Jan 2026, 09:30 UTC/).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByText(/Hourly data/))
  expect(screen.getByRole('columnheader', { name: 'Published UTC' })).toBeInTheDocument()
  expect(screen.queryByRole('columnheader', { name: 'Actual MW' })).not.toBeInTheDocument()
})

it('delivery and cutoff control changes request updated selections', async () => {
  render(<App />)
  await screen.findByLabelText('Delivery day')
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-02-01' } })
  fireEvent.input(screen.getByLabelText('D-1 decision cutoff · UTC'), { target: { value: '10:45' } })
  await waitFor(() => expect(mocked).toHaveBeenLastCalledWith('forecasts?delivery_date=2026-02-01&cutoff_time=10%3A45', expect.any(AbortSignal)))
})

it('shows accuracy metrics, sample counts, breakdowns, context and actual table', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Accuracy' }))
  expect(await screen.findByText('Signed bias')).toBeInTheDocument()
  const primary = screen.getByRole('region', { name: 'Primary accuracy metrics' })
  expect(within(primary).getAllByRole('heading').map(h => h.textContent)).toEqual([
    'Average miss', 'Over / under-forecast', '90th-percentile miss',
  ])
  expect(within(primary).getByText('MAE')).toBeVisible()
  expect(within(primary).getByText('P90 absolute error')).toBeVisible()
  expect(within(primary).getAllByText('n = 24 hours')).toHaveLength(3)
  expect(within(primary).getByText('Average size of the hourly forecast error, regardless of direction.')).toBeVisible()
  expect(within(primary).getByText('About 90% of historical hourly errors were no larger than this amount.')).toBeVisible()
  const summary = screen.getByText('More statistics')
  expect(summary.closest('details')).not.toHaveAttribute('open')
  expect(screen.getByText('RMSE')).not.toBeVisible()
  expect(screen.getByText('MAPE')).not.toBeVisible()
  fireEvent.click(summary)
  expect(summary.closest('details')).toHaveAttribute('open')
  expect(screen.getByText('RMSE')).toBeVisible()
  expect(screen.getByText('MAPE')).toBeVisible()
  expect(screen.getByText('Gives larger forecast errors more weight.')).toBeVisible()
  expect(screen.getByText('Average hourly absolute error as a percentage of actual generation.')).toBeVisible()
  expect(screen.getByText('Zero-actual hours excluded from MAPE: 0.')).toBeVisible()
  expect(screen.getAllByText('n = 24 hours')).toHaveLength(5)
  fireEvent.click(summary)
  expect(screen.getByText('RMSE')).not.toBeVisible()
  expect(screen.getByText('Error by UTC delivery hour')).toBeInTheDocument()
  expect(screen.getByText('The cause remains unknown.')).toBeInTheDocument()
  fireEvent.click(screen.getByText(/Hourly data/))
  expect(screen.getByRole('columnheader', { name: 'Actual MW' })).toBeInTheDocument()
  fireEvent.input(screen.getByLabelText('Delivery from'), { target: { value: '2026-01-10' } })
  await waitFor(() => expect(mocked).toHaveBeenLastCalledWith('accuracy?delivery_from=2026-01-10&delivery_to=2026-02-01&cutoff_time=09%3A30', expect.any(AbortSignal)))
})

it('does not send malformed or out-of-scope controls', async () => {
  render(<App />)
  await screen.findByText('24 / 24 hours')
  const count = mocked.mock.calls.length
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-02-02' } })
  expect(screen.getByRole('alert')).toHaveTextContent('supported delivery day')
  expect(mocked).toHaveBeenCalledTimes(count)
  expect(screen.queryByText('24 / 24 hours')).not.toBeInTheDocument()
})

it('shows loading, request errors and retries the failed request', async () => {
  mocked.mockResolvedValueOnce(meta).mockRejectedValueOnce(new Error('Backend unavailable')).mockResolvedValueOnce(decision)
  render(<App />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading')
  expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Retry request' }))
  expect(await screen.findByText('24 / 24 hours')).toBeInTheDocument()
})

it('shows empty decision and incomplete/null accuracy without invented zero metrics', async () => {
  const emptyDecision = { ...decision, coverage: { expected: 24, forecasts: 0, missing_forecasts: 24 }, slots: slots.map(s => ({ ...s, forecast_mw: null, publish_time: null, horizon_hours: null })) }
  const emptyAccuracy = { ...accuracy, coverage: { expected: 24, forecasts: 0, actuals: 0, paired: 0, missing_actuals: 24, missing_forecasts: 24, excluded: 24 }, metrics: { mae_mw: null, rmse_mw: null, bias_mw: null, mape_percent: null, p90_absolute_error_mw: null, mape_eligible: 0, mape_excluded_zero_actual: 0 }, slots: emptyDecision.slots.map(s => ({ ...s, actual_mw: null, error_mw: null })) }
  mocked.mockImplementation(async path => (path === 'metadata' ? meta : path.startsWith('forecasts') ? emptyDecision : emptyAccuracy) as never)
  render(<App />)
  expect(await screen.findByText('No eligible forecasts for this cutoff.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Accuracy' }))
  expect(await screen.findByText('No forecast or actual observations for this selection.')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Incomplete coverage')
  const primary = screen.getByRole('region', { name: 'Primary accuracy metrics' })
  expect(within(primary).getAllByText('Unavailable')).toHaveLength(3)
  fireEvent.click(screen.getByText('More statistics'))
  expect(screen.getAllByText('Unavailable').filter(e => e.closest('.metric')).length).toBe(5)
})

function Probe({ path }: { path: string }) {
  const state = useRequest<string>(path)
  return <p>{state.loading ? 'Loading' : state.data}</p>
}
it('aborts superseded requests and ignores late stale responses', async () => {
  let oldResolve!: (value: string) => void
  let newResolve!: (value: string) => void
  mocked.mockImplementation(path => new Promise(resolve => { if (path === 'old') oldResolve = resolve; else newResolve = resolve }) as never)
  const { rerender } = render(<Probe path="old" />)
  const oldSignal = mocked.mock.calls[0][1]
  rerender(<Probe path="new" />)
  expect(oldSignal.aborted).toBe(true)
  await act(async () => newResolve('New selection'))
  expect(screen.getByText('New selection')).toBeInTheDocument()
  await act(async () => oldResolve('Stale selection'))
  expect(screen.queryByText('Stale selection')).not.toBeInTheDocument()
  expect(screen.getByText('New selection')).toBeInTheDocument()
})

describe('UTC formatting', () => {
  it('uses UTC explicitly regardless of local display timezone', () => {
    expect(utc('2026-01-01T23:30:00Z')).toBe('01 Jan 2026, 23:30 UTC')
    expect(utc(null)).toBe('Unavailable')
  })
})


it.each([
  [80, '+80.0', 'Wind was over-forecast by this amount on average.'],
  [-80, '-80.0', 'Wind was under-forecast by this amount on average.'],
  [0, '0.0', 'Over- and under-forecasts balance on average; individual errors may remain.'],
  [null, 'Unavailable', 'Not available for this selection.'],
] as const)('presents bias %s with the correct sign and explanation', async (bias, value, explanation) => {
  const result = { ...accuracy, metrics: { ...accuracy.metrics, bias_mw: bias, mape_eligible: 23, mape_excluded_zero_actual: 1 } }
  mocked.mockImplementation(async path => (path === 'metadata' ? meta : path.startsWith('forecasts') ? decision : result) as never)
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Accuracy' }))
  const heading = await screen.findByRole('heading', { name: 'Over / under-forecast' })
  const metric = within(heading.parentElement!)
  expect(metric.getByText(explanation)).toBeVisible()
  const displayedValue = metric.getByText(value, { exact: false, selector: '.metric-value' })
  expect(displayedValue).toHaveTextContent(bias === null ? 'Unavailable' : `${value}MW`)
  expect(metric.queryByText('MW')).toBe(bias === null ? null : displayedValue.querySelector('small'))
  for (const text of [
    'Wind was over-forecast by this amount on average.',
    'Wind was under-forecast by this amount on average.',
    'Over- and under-forecasts balance on average; individual errors may remain.',
  ]) {
    if (text !== explanation) expect(metric.queryByText(text)).not.toBeInTheDocument()
  }
  const exclusions = screen.getByText('Zero-actual hours excluded from MAPE: 1.')
  expect(exclusions).not.toBeVisible()
  fireEvent.click(screen.getByText('More statistics'))
  expect(exclusions).toBeVisible()
  expect(screen.getByText('n = 23 hours')).toBeVisible()
})
