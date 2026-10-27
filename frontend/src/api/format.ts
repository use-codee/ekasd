export const number = (value: number | null | undefined, digits = 1) =>
  value == null ? 'Unavailable' : new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
export const utc = (value: string | null) => value == null ? 'Unavailable' :
  `${new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value))} UTC`
export const hour = (value: string) => new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value))
export const day = (value: string) => new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: '2-digit', month: 'short' }).format(new Date(value))
export const validClock = (clock: string) => /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(clock)
export const validDay = (value: string, min: string, max: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value < min || value > max) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}
