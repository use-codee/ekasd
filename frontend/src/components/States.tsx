import { utc } from '../api/format'

type RequestStatus = { loading: boolean; error?: string; retry: () => void; hasData?: boolean; busy?: boolean }
export function RequestState({ loading, error, retry, hasData, busy }: RequestStatus) {
  if (loading) return <div className="state" role="status"><span className="spinner" /> Loading wind data… The server may take a moment to wake up.</div>
  if (error) return <div className="state error" role="alert"><strong>{hasData ? 'Could not refresh; showing previously loaded results.' : 'Unable to load this selection'}</strong><p>{error}</p><button disabled={busy} onClick={retry}>Retry request</button></div>
  return null
}

export function RefreshControls({ valid, busy, refreshing, lastFetched, retry }: {
  valid: boolean; busy: boolean; refreshing: boolean; lastFetched: number; retry: () => void
}) {
  return <div className="refresh-controls"><button disabled={!valid || busy} onClick={retry}>Refresh data</button>
    {refreshing && <span role="status">Refreshing…</span>}
    {lastFetched > 0 && <small>Last fetched {utc(new Date(lastFetched).toISOString())} · response received</small>}
  </div>
}
