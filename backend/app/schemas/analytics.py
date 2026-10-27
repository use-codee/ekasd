from datetime import date, datetime

from pydantic import BaseModel, FiniteFloat


class Coverage(BaseModel):
    expected: int
    forecasts: int
    actuals: int
    paired: int
    missing_forecasts: int
    missing_actuals: int
    excluded: int


class Metrics(BaseModel):
    mae_mw: FiniteFloat | None
    rmse_mw: FiniteFloat | None
    bias_mw: FiniteFloat | None
    mape_percent: FiniteFloat | None
    p90_absolute_error_mw: FiniteFloat | None
    mape_eligible: int
    mape_excluded_zero_actual: int


class ForecastSlot(BaseModel):
    startTime: datetime
    forecast_mw: FiniteFloat | None
    publish_time: datetime | None
    horizon_hours: FiniteFloat | None
    decision_cutoff: datetime


class AccuracySlot(ForecastSlot):
    actual_mw: FiniteFloat | None
    error_mw: FiniteFloat | None


class DecisionCoverage(BaseModel):
    expected: int
    forecasts: int
    missing_forecasts: int


class DecisionResponse(BaseModel):
    delivery_date: date
    decision_date: date
    cutoff_time: str
    cutoff_utc: datetime
    timezone: str = "UTC"
    coverage: DecisionCoverage
    slots: list[ForecastSlot]
    assumptions: list[str]


class Breakdown(BaseModel):
    label: str
    coverage: Coverage
    metrics: Metrics


class Breakdowns(BaseModel):
    hour: list[Breakdown]
    day: list[Breakdown]
    horizon: list[Breakdown]


class Buffer(BaseModel):
    p90_mw: FiniteFloat | None
    bias_mw: FiniteFloat | None
    sample_count: int
    message: str


class AccuracyResponse(BaseModel):
    delivery_from: date
    delivery_to: date
    cutoff_time: str
    timezone: str = "UTC"
    coverage: Coverage
    metrics: Metrics
    slots: list[AccuracySlot]
    breakdowns: Breakdowns
    buffer: Buffer
    diagnostic_limitation: str


class Provenance(BaseModel):
    built_at: datetime | None
    raw_chunks: int
    inputs: dict[str, str]


class MetadataResponse(BaseModel):
    decision_from: date
    decision_to: date
    delivery_from: date
    delivery_to: date
    default_cutoff: str
    timezone: str
    source: str
    units: str
    assumptions: list[str]
    provenance: Provenance
