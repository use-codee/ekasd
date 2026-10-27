import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '../api/client'
import { requestKey } from '../api/queryClient'
import type { Metadata } from '../types/api'

export function useRequest<T>(path: string | null) {
  const client = useQueryClient()
  const result = useQuery({ queryKey: requestKey(path), enabled: path !== null,
    queryFn: ({ signal }) => request<T>(path!, signal) })
  const [manualPath, setManualPath] = useState<string | null>(null)
  const refresh = async () => {
    if (path === null || result.isFetching || manualPath === path) return
    setManualPath(path)
    try {
      // Start this selection immediately; metadata invalidation joins in-flight requests.
      await Promise.all([
        result.refetch({ cancelRefetch: false }),
        path === 'metadata' ? Promise.resolve() : client.fetchQuery({
          queryKey: requestKey('metadata'), staleTime: 0,
          queryFn: ({ signal }) => request<Metadata>('metadata', signal),
        }).catch(() => undefined), // App displays metadata refresh failures without hiding the workspace.
      ])
    } finally { setManualPath(null) }
  }
  const enabled = path !== null
  return {
    data: enabled ? result.data : undefined,
    error: enabled && result.error ? result.error.message : undefined,
    loading: enabled && result.isPending,
    refreshing: enabled && (result.isFetching || manualPath === path) && result.data !== undefined,
    busy: enabled && (result.isFetching || manualPath === path),
    lastFetched: enabled ? result.dataUpdatedAt : 0,
    hasData: enabled && result.data !== undefined,
    retry: refresh,
  }
}
