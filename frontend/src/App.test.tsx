import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { QueryClientProvider, focusManager } from '@tanstack/react-query'
import { createQueryClient, requestKey } from './api/queryClient'
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
let testClient: ReturnType<typeof createQueryClient>
beforeEach(() => {
  testClient = createQueryClient()
  vi.clearAllMocks()
  mocked.mockImplementation(async path => (path === 'metadata' ? meta : path.startsWith('forecasts') ? decision : accuracy) as never)
})

afterEach(() => { cleanup(); testClient.clear() })

it('loads metadata, shows decision-only UTC data and accessible publication table', async () => {
  render(<App queryClient={testClient} />)
  expect(await screen.findByText('24 / 24 hours')).toBeInTheDocument()
  expect(screen.getByLabelText('Delivery day')).toHaveAttribute('min', meta.delivery_from)
  expect(screen.getByText('2026-01-01')).toBeInTheDocument()
  expect(screen.getAllByText(/01 Jan 2026, 09:30 UTC/).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByText(/Hourly data/))
  expect(screen.getByRole('columnheader', { name: 'Published UTC' })).toBeInTheDocument()
  expect(screen.queryByRole('columnheader', { name: 'Actual MW' })).not.toBeInTheDocument()
})

it('delivery and cutoff control changes request updated selections', async () => {
  render(<App queryClient={testClient} />)
  await screen.findByLabelText('Delivery day')
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-02-01' } })
  fireEvent.input(screen.getByLabelText('D-1 decision cutoff · UTC'), { target: { value: '10:45' } })
  await waitFor(() => expect(mocked).toHaveBeenLastCalledWith('forecasts?delivery_date=2026-02-01&cutoff_time=10%3A45', expect.any(AbortSignal)))
})

it('shows accuracy metrics, sample counts, breakdowns, context and actual table', async () => {
  render(<App queryClient={testClient} />)
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
  render(<App queryClient={testClient} />)
  await screen.findByText('24 / 24 hours')
  const count = mocked.mock.calls.length
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-02-02' } })
  expect(screen.getByRole('alert')).toHaveTextContent('supported delivery day')
  expect(mocked).toHaveBeenCalledTimes(count)
  expect(screen.queryByText('24 / 24 hours')).not.toBeInTheDocument()
})

it('shows loading, request errors and retries the failed request', async () => {
  mocked.mockResolvedValueOnce(meta).mockRejectedValueOnce(new Error('Backend unavailable')).mockResolvedValueOnce(decision)
  render(<App queryClient={testClient} />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading')
  expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Retry request' }))
  expect(await screen.findByText('24 / 24 hours')).toBeInTheDocument()
})

it('shows empty decision and incomplete/null accuracy without invented zero metrics', async () => {
  const emptyDecision = { ...decision, coverage: { expected: 24, forecasts: 0, missing_forecasts: 24 }, slots: slots.map(s => ({ ...s, forecast_mw: null, publish_time: null, horizon_hours: null })) }
  const emptyAccuracy = { ...accuracy, coverage: { expected: 24, forecasts: 0, actuals: 0, paired: 0, missing_actuals: 24, missing_forecasts: 24, excluded: 24 }, metrics: { mae_mw: null, rmse_mw: null, bias_mw: null, mape_percent: null, p90_absolute_error_mw: null, mape_eligible: 0, mape_excluded_zero_actual: 0 }, slots: emptyDecision.slots.map(s => ({ ...s, actual_mw: null, error_mw: null })) }
  mocked.mockImplementation(async path => (path === 'metadata' ? meta : path.startsWith('forecasts') ? emptyDecision : emptyAccuracy) as never)
  render(<App queryClient={testClient} />)
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
  const createQueryClientForProbe = testClient
  const { rerender } = render(<QueryClientProvider client={createQueryClientForProbe}><Probe path="old" /></QueryClientProvider>)
  const oldSignal = mocked.mock.calls[0][1]
  rerender(<QueryClientProvider client={createQueryClientForProbe}><Probe path="new" /></QueryClientProvider>)
  expect(oldSignal.aborted).toBe(true)
  await act(async () => newResolve('New selection'))
  expect(await screen.findByText('New selection')).toBeInTheDocument()
  await act(async () => oldResolve('Stale selection'))
  expect(screen.queryByText('Stale selection')).not.toBeInTheDocument()
  expect(await screen.findByText('New selection')).toBeInTheDocument()
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
  render(<App queryClient={testClient} />)
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


it('reuses completed queries and preserves independent dates and shared cutoff', async () => {
  render(<App queryClient={testClient} />)
  await screen.findByText('24 / 24 hours')
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-01-10' } })
  await screen.findByText('24 / 24 hours')
  fireEvent.click(screen.getByRole('button', { name: 'Accuracy' }))
  await screen.findByText('Signed bias')
  fireEvent.input(screen.getByLabelText('Delivery from'), { target: { value: '2026-01-12' } })
  await screen.findByText('Signed bias')
  const count = mocked.mock.calls.length
  fireEvent.click(screen.getByRole('button', { name: 'Decision' }))
  expect(screen.getByLabelText('Delivery day')).toHaveValue('2026-01-10')
  expect(screen.getByText('24 / 24 hours')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Accuracy' }))
  expect(screen.getByLabelText('Delivery from')).toHaveValue('2026-01-12')
  expect(mocked).toHaveBeenCalledTimes(count)
  fireEvent.input(screen.getByLabelText('D-1 decision cutoff · UTC'), { target: { value: '10:45' } })
  await screen.findByText('Signed bias')
  fireEvent.click(screen.getByRole('button', { name: 'Decision' }))
  expect(screen.getByLabelText('D-1 decision cutoff · UTC')).toHaveValue('10:45')
})

it('keeps same-query results and disclosures during refresh, updates data, and retains it on failure', async () => {
  render(<App queryClient={testClient} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Accuracy' }))
  await screen.findByText('Signed bias')
  fireEvent.click(screen.getByText('More statistics'))
  let finish!: (value: Accuracy) => void
  mocked.mockImplementation(path => path === 'metadata' ? Promise.resolve(meta) as never : new Promise(resolve => { finish = resolve }) as never)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }))
  expect(screen.getByText('Refreshing…')).toBeVisible()
  expect(screen.getByText('Signed bias')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Refresh data' })).toBeDisabled()
  await act(async () => finish({ ...accuracy, metrics: { ...accuracy.metrics, mae_mw: 321 } }))
  expect(await screen.findByText('321.0')).toBeVisible()
  expect(screen.getByText('More statistics').closest('details')).toHaveAttribute('open')
  expect(screen.getByText(/Last fetched/)).toHaveTextContent('UTC')
  mocked.mockImplementation(path => path === 'metadata' ? Promise.resolve(meta) as never : Promise.reject(new Error('Offline')))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not refresh; showing previously loaded results')
  expect(screen.getByText('321.0')).toBeVisible()
  mocked.mockImplementation(async path => (path === 'metadata' ? meta : accuracy) as never)
  fireEvent.click(screen.getByRole('button', { name: 'Retry request' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
})

it('deduplicates identical observers, reuses fresh keys and revalidates stale focus/remount', async () => {
  const client = testClient
  const tree = (show: boolean) => <QueryClientProvider client={client}>{show && <><Probe path="shared" /><Probe path="shared" /></>}</QueryClientProvider>
  mocked.mockResolvedValue('Result' as never)
  const { rerender, unmount } = render(tree(true))
  await screen.findAllByText('Result')
  expect(mocked).toHaveBeenCalledTimes(1)
  await act(async () => { focusManager.setFocused(false); focusManager.setFocused(true) })
  expect(mocked).toHaveBeenCalledTimes(1)
  rerender(tree(false)); rerender(tree(true))
  expect(mocked).toHaveBeenCalledTimes(1)
  // Advance the successful receipt time rather than waiting five minutes.
  act(() => client.setQueryData(requestKey('shared'), 'Result', { updatedAt: Date.now() - 301_000 }))
  await act(async () => { focusManager.setFocused(false); focusManager.setFocused(true) })
  await waitFor(() => expect(mocked).toHaveBeenCalledTimes(2))
  rerender(tree(false))
  client.setQueryData(requestKey('shared'), 'Result', { updatedAt: Date.now() - 301_000 })
  rerender(tree(true))
  await waitFor(() => expect(mocked).toHaveBeenCalledTimes(3))
  unmount(); client.clear(); focusManager.setFocused(undefined)
})

it('invalidates data only when metadata input checksums change, keeping controls intact', async () => {
  render(<App queryClient={testClient} />)
  await screen.findByText('24 / 24 hours')
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-01-10' } })
  await screen.findByText('24 / 24 hours')
  fireEvent.click(screen.getByRole('button', { name: 'Accuracy' }))
  await screen.findByText('Signed bias')
  mocked.mockImplementation(async path => (path === 'metadata' ? { ...meta, provenance: { ...meta.provenance, built_at: 'changed', inputs: {} } } : path.startsWith('forecasts') ? decision : accuracy) as never)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh data' })).toBeEnabled())
  const forecastCount = () => mocked.mock.calls.filter(([path]) => path.startsWith('forecasts')).length
  const before = forecastCount()
  fireEvent.click(screen.getByRole('button', { name: 'Decision' }))
  expect(forecastCount()).toBe(before)
  expect(screen.getByLabelText('Delivery day')).toHaveValue('2026-01-10')
  fireEvent.click(screen.getByRole('button', { name: 'Accuracy' }))
  mocked.mockImplementation(async path => (path === 'metadata' ? { ...meta, default_cutoff: '12:00', provenance: { ...meta.provenance, inputs: { forecasts: 'changed-hash' } } } : path.startsWith('forecasts') ? decision : accuracy) as never)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh data' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Decision' }))
  await waitFor(() => expect(forecastCount()).toBe(before + 1))
  expect(screen.getByLabelText('Delivery day')).toHaveValue('2026-01-10')
  expect(screen.getByLabelText('D-1 decision cutoff · UTC')).toHaveValue('09:30')
})


it('returns to a cached selection without requesting and hides it for invalid controls', async () => {
  render(<App queryClient={testClient} />)
  await screen.findByText('24 / 24 hours')
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-01-10' } })
  await screen.findByText('24 / 24 hours')
  const count = mocked.mock.calls.length
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-01-02' } })
  expect(screen.getByText('24 / 24 hours')).toBeVisible()
  expect(mocked).toHaveBeenCalledTimes(count)
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '' } })
  expect(screen.queryByText('24 / 24 hours')).not.toBeInTheDocument()
  expect(screen.queryByText(/Last fetched/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Refresh data' })).toBeDisabled()
  expect(mocked).toHaveBeenCalledTimes(count)
})

it('keeps the workspace and controls when metadata refresh fails', async () => {
  render(<App queryClient={testClient} />)
  await screen.findByText('24 / 24 hours')
  fireEvent.input(screen.getByLabelText('Delivery day'), { target: { value: '2026-01-10' } })
  await screen.findByText('24 / 24 hours')
  mocked.mockImplementation(path => path === 'metadata' ? Promise.reject(new Error('Metadata unavailable')) : Promise.resolve(decision) as never)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Metadata unavailable')
  expect(screen.getByLabelText('Delivery day')).toHaveValue('2026-01-10')
  expect(screen.getByText('24 / 24 hours')).toBeVisible()
  mocked.mockImplementation(async path => (path === 'metadata' ? meta : decision) as never)
  fireEvent.click(screen.getByRole('button', { name: 'Retry request' }))
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  expect(screen.getByLabelText('Delivery day')).toHaveValue('2026-01-10')
})
