import { useEffect, useState } from 'react'
import { request } from '../api/client'

export function useRequest<T>(path: string | null) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{ path: string; attempt: number; data?: T; error?: string }>()
  useEffect(() => {
    if (path === null) return
    const controller = new AbortController()
    let active = true
    request<T>(path, controller.signal).then(
      data => { if (active) setState({ path, attempt, data }) },
      error => { if (active) setState({ path, attempt, error: error instanceof Error ? error.message : 'Unable to load data' }) },
    )
    return () => { active = false; controller.abort() }
  }, [path, attempt])
  const current = state?.path === path && state.attempt === attempt ? state : undefined
  return { data: current?.data, error: current?.error, loading: path !== null && !current,
    retry: () => setAttempt(n => n + 1) }
}
