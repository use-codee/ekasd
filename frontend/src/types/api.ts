export interface Metadata {
  decision_from: string; decision_to: string; delivery_from: string; delivery_to: string
  default_cutoff: string; timezone: string; source: string; units: string
  assumptions: string[]
  provenance: { built_at: string | null; raw_chunks: number; inputs: Record<string, string> }
}
export interface Coverage {
  expected: number; forecasts: number; actuals: number; paired: number
  missing_forecasts: number; missing_actuals: number; excluded: number
}
export interface Metrics {
  mae_mw: number | null; rmse_mw: number | null; bias_mw: number | null
  mape_percent: number | null; p90_absolute_error_mw: number | null
  mape_eligible: number; mape_excluded_zero_actual: number
}
export interface ForecastSlot {
  startTime: string; forecast_mw: number | null; publish_time: string | null
  horizon_hours: number | null; decision_cutoff: string
}
export interface AccuracySlot extends ForecastSlot { actual_mw: number | null; error_mw: number | null }
export interface Decision {
  delivery_date: string; decision_date: string; cutoff_time: string; cutoff_utc: string
  timezone: string; coverage: Pick<Coverage, 'expected' | 'forecasts' | 'missing_forecasts'>
  slots: ForecastSlot[]; assumptions: string[]
}
export interface Group { label: string; coverage: Coverage; metrics: Metrics }
export interface Accuracy {
  delivery_from: string; delivery_to: string; cutoff_time: string; timezone: string
  coverage: Coverage; metrics: Metrics; slots: AccuracySlot[]
  breakdowns: { hour: Group[]; day: Group[]; horizon: Group[] }
  buffer: { p90_mw: number | null; bias_mw: number | null; sample_count: number; message: string }
  diagnostic_limitation: string
}
