export function RequestState({ loading, error, retry }: { loading: boolean; error?: string; retry: () => void }) {
  if (loading) return <div className="state" role="status"><span className="spinner" /> Loading wind data…</div>
  if (error) return <div className="state error" role="alert"><strong>Unable to load this selection</strong><p>{error}</p><button onClick={retry}>Retry request</button></div>
  return null
}
