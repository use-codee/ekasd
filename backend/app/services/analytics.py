"""Pure UTC selection, aggregation and metrics; no file or network access."""

from datetime import UTC, date, datetime, time, timedelta
from math import isfinite

import pandas as pd


class DataError(ValueError):
    pass


BUCKETS = [(0, 12), (12, 24), (24, 36), (36, 48), (48, 72), (72, float("inf"))]


def utc(value) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
        if (
            pd.isna(result)
            or result.tzinfo is None
            or result.utcoffset() != timedelta(0)
        ):
            raise ValueError("explicit UTC required")
        return result.tz_convert("UTC")
    except (ValueError, TypeError) as exc:
        raise DataError(f"Invalid UTC timestamp: {value}") from exc


def normalize(frame: pd.DataFrame, forecast: bool) -> pd.DataFrame:
    cols = ["startTime", "generation"] + (["publishTime"] if forecast else [])
    if not set(cols).issubset(frame.columns):
        raise DataError(f"Required columns: {cols}")
    result = frame.copy(deep=True)
    for name in ["startTime"] + (["publishTime"] if forecast else []):
        result[name] = pd.to_datetime(result[name].map(utc), utc=True)
    try:
        if result.generation.map(lambda v: isinstance(v, bool)).any():
            raise ValueError("boolean generation")
        result["generation"] = pd.to_numeric(result.generation, errors="raise").astype(
            float
        )
        if not result.generation.map(isfinite).all():
            raise ValueError("nonfinite generation")
    except (TypeError, ValueError) as exc:
        raise DataError("Generation must be finite numeric MW") from exc
    start = result.startTime.dt
    if (
        (start.minute % (60 if forecast else 30) != 0)
        | (start.second != 0)
        | (start.microsecond != 0)
        | (start.nanosecond != 0)
    ).any():
        raise DataError("Invalid target timestamp grid")
    keys = ["publishTime", "startTime"] if forecast else ["startTime"]
    result = result.drop_duplicates()
    if result.duplicated(keys).any():
        conflicts = result.loc[result.duplicated(keys, keep=False), keys]
        raise DataError(f"Conflicting duplicate keys: {conflicts.to_dict('records')}")
    return result.sort_values(keys).reset_index(drop=True)


def hourly_actuals(frame: pd.DataFrame) -> pd.DataFrame:
    actual = normalize(frame, False)
    # After grid validation and deduplication, exactly 2 distinct halves are required.
    actual["hour"] = actual.startTime.dt.floor("h")
    grouped = actual.groupby("hour").generation.agg(["count", "mean"])
    return (
        grouped.loc[grouped["count"] == 2, ["mean"]]
        .rename(columns={"mean": "actual_mw"})
        .rename_axis("startTime")
        .reset_index()
    )


def cutoff(day: date, clock: str) -> datetime:
    parsed = time.fromisoformat(clock)
    if (
        len(clock) != 5
        or clock[2] != ":"
        or parsed.tzinfo
        or parsed.second
        or parsed.microsecond
    ):
        raise ValueError("cutoff must be HH:MM")
    return datetime.combine(day - timedelta(days=1), parsed, UTC)


def select_day(
    forecasts: pd.DataFrame, day: date, clock: str = "09:30"
) -> pd.DataFrame:
    return _select_day(normalize(forecasts, True), day, clock)


def _select_day(frame: pd.DataFrame, day: date, clock: str) -> pd.DataFrame:
    limit = cutoff(day, clock)
    hours = pd.date_range(datetime.combine(day, time(), UTC), periods=24, freq="h")
    eligible = frame[
        (frame.publishTime <= limit)
        & (frame.publishTime <= frame.startTime)
        & frame.startTime.isin(hours)
    ]
    latest = eligible.sort_values("publishTime").drop_duplicates(
        "startTime", keep="last"
    )
    selected = (
        pd.DataFrame({"startTime": hours})
        .merge(
            latest[["startTime", "publishTime", "generation"]],
            on="startTime",
            how="left",
        )
        .rename(columns={"generation": "forecast_mw", "publishTime": "publish_time"})
    )
    selected["horizon_hours"] = (
        selected.startTime - selected.publish_time
    ).dt.total_seconds() / 3600
    selected["decision_cutoff"] = pd.Timestamp(limit)
    return selected


def evaluate(
    forecasts: pd.DataFrame,
    hourly: pd.DataFrame,
    first: date,
    last: date,
    clock: str = "09:30",
) -> pd.DataFrame:
    normalized = normalize(forecasts, True)
    selected = pd.concat(
        [
            _select_day(normalized, d.date(), clock)
            for d in pd.date_range(first, last, freq="D")
        ],
        ignore_index=True,
    )
    joined = selected.merge(hourly, on="startTime", how="left", validate="one_to_one")
    joined["error_mw"] = joined.forecast_mw - joined.actual_mw
    return joined


def summary(frame: pd.DataFrame) -> dict:
    forecasts = frame.get("forecast_mw", pd.Series(dtype=float))
    actuals = frame.get("actual_mw", pd.Series(dtype=float))
    valid_f = forecasts.map(lambda v: pd.notna(v) and isfinite(v))
    valid_a = actuals.map(lambda v: pd.notna(v) and isfinite(v))
    paired = pd.DataFrame({"forecast_mw": forecasts, "actual_mw": actuals}).loc[
        valid_f & valid_a
    ]
    error = paired.forecast_mw - paired.actual_mw
    absolute = error.abs()
    mape = paired.loc[paired.actual_mw != 0]
    n = len(paired)
    return {
        "coverage": {
            "expected": len(frame),
            "forecasts": int(valid_f.sum()),
            "actuals": int(valid_a.sum()),
            "paired": n,
            "missing_forecasts": int((~valid_f).sum()),
            "missing_actuals": int((~valid_a).sum()),
            "excluded": len(frame) - n,
        },
        "metrics": {
            "mae_mw": float(absolute.mean()) if n else None,
            "rmse_mw": float((error.pow(2).mean()) ** 0.5) if n else None,
            "bias_mw": float(error.mean()) if n else None,
            "mape_percent": float(
                (
                    (mape.forecast_mw - mape.actual_mw).abs() / mape.actual_mw.abs()
                ).mean()
                * 100
            )
            if len(mape)
            else None,
            "p90_absolute_error_mw": float(
                absolute.quantile(0.9, interpolation="linear")
            )
            if n
            else None,
            "mape_eligible": len(mape),
            "mape_excluded_zero_actual": n - len(mape),
        },
    }


def breakdowns(frame: pd.DataFrame) -> dict:
    hours = frame.startTime.dt.hour
    days = frame.startTime.dt.strftime("%Y-%m-%d")
    return {
        "hour": [
            {"label": f"{h:02d}:00", **summary(frame.loc[hours == h])}
            for h in range(24)
        ],
        "day": [
            {"label": d, **summary(frame.loc[days == d])} for d in sorted(days.unique())
        ],
        "horizon": [
            {
                "label": f"[{lo},{hi if isfinite(hi) else '+infinity'}) h",
                **summary(
                    frame.loc[(frame.horizon_hours >= lo) & (frame.horizon_hours < hi)]
                ),
            }
            for lo, hi in BUCKETS
        ],
    }


def records(frame: pd.DataFrame) -> list[dict]:
    return [
        {
            k: None
            if pd.isna(v)
            else v.isoformat().replace("+00:00", "Z")
            if isinstance(v, (datetime, pd.Timestamp))
            else float(v)
            if isinstance(v, (int, float))
            else v
            for k, v in row.items()
        }
        for row in frame.to_dict("records")
    ]


def correlation(frame: pd.DataFrame) -> float | None:
    paired = frame[["forecast_mw", "actual_mw"]].dropna()
    if (
        len(paired) < 2
        or paired.forecast_mw.nunique() < 2
        or paired.actual_mw.nunique() < 2
    ):
        return None
    value = float(paired.forecast_mw.corr(paired.actual_mw))
    return value if isfinite(value) else None
