export async function request<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, { signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}
export function query(endpoint: string, params: Record<string, string>): string {
  return `${endpoint}?${new URLSearchParams(params).toString()}`
}
