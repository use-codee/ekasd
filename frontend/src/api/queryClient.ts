import { QueryCache, QueryClient } from '@tanstack/react-query'
import type { Metadata } from '../types/api'

export const requestKey = (path: string | null) => ['api', path] as const
const datasetQuery = (path: unknown) => typeof path === 'string' && /^(forecasts|accuracy)\?/.test(path)

export function createQueryClient() {
  let inputChecksums: string | undefined
  const client = new QueryClient({
    defaultOptions: { queries: { staleTime: 5 * 60_000, gcTime: 30 * 60_000, retry: false } },
    queryCache: new QueryCache({ onSuccess(data, query) {
      if (query.queryKey[1] !== 'metadata') return
      const inputs = (data as Metadata).provenance.inputs
      const checksums = JSON.stringify(Object.entries(inputs).sort(([a], [b]) => a.localeCompare(b)))
      if (inputChecksums !== undefined && checksums !== inputChecksums) {
        void client.invalidateQueries({ predicate: q => datasetQuery(q.queryKey[1]) }, { cancelRefetch: false })
      }
      inputChecksums = checksums
    } }),
  })
  return client
}
