from datetime import date

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from backend.app.services.analytics import (
    DataError,
    breakdowns,
    cutoff,
    evaluate,
    hourly_actuals,
    normalize,
    select_day,
    summary,
)

DAY = date(2026, 1, 2)


def forecasts(rows=()):
    return pd.DataFrame(rows, columns=["startTime", "publishTime", "generation"])


def actuals(rows=()):
    return pd.DataFrame(rows, columns=["startTime", "generation"])


def test_no_future_leakage_exact_cutoff_and_per_hour_selection():
    frame = forecasts(
        [
            ("2026-01-02T00:00Z", "2026-01-01T09:31Z", 999999),
            ("2026-01-02T00:00Z", "2026-01-01T09:30Z", 20),
            ("2026-01-02T00:00Z", "2026-01-01T08:30Z", 10),
            ("2026-01-02T01:00Z", "2026-01-01T08:00Z", 30),
        ]
    )
    before = frame.copy(deep=True)
    selected = select_day(frame, DAY)
    assert len(selected) == 24
    assert selected.forecast_mw.iloc[:2].tolist() == [20, 30]
    assert selected.horizon_hours.iloc[0] == 14.5
    assert select_day(frame, DAY, "09:29").forecast_mw.iloc[0] == 10
    assert select_day(frame, DAY, "00:00").forecast_mw.isna().all()
    assert_frame_equal(frame, before)


def test_horizon_duplicates_missing_and_no_mutation():
    # D-1 cutoff cannot make same-day equality eligible: test normalization/selection
    # of a target before the chosen delivery day defensively too.
    frame = forecasts([("2026-01-02T00:00Z", "2026-01-02T00:00Z", 0)])
    assert select_day(frame, DAY).forecast_mw.isna().all()
    assert len(normalize(frame, True)) == 1
    assert len(normalize(pd.concat([frame, frame]), True)) == 1
    with pytest.raises(DataError, match="Conflicting"):
        normalize(pd.concat([frame, frame.assign(generation=9)]), True)
    negative = forecasts([("2026-01-02T00:00Z", "2026-01-03T00:00Z", 9)])
    assert select_day(negative, DAY).forecast_mw.isna().all()
    joined = evaluate(forecasts(), hourly_actuals(actuals()), DAY, DAY)
    assert len(joined) == 24
    assert summary(joined)["coverage"]["excluded"] == 24


def test_actuals_require_distinct_halves_and_conflicts_fail():
    frame = actuals(
        [
            ("2026-01-02T00:30Z", 20),
            ("2026-01-02T00:00Z", 10),
            ("2026-01-02T00:00Z", 10),
            ("2026-01-02T01:00Z", 50),
        ]
    )
    before = frame.copy(deep=True)
    hourly = hourly_actuals(frame)
    assert hourly.actual_mw.tolist() == [15]
    assert_frame_equal(frame, before)
    with pytest.raises(DataError):
        hourly_actuals(pd.concat([frame, actuals([("2026-01-02T00:00Z", 11)])]))


def test_hand_calculated_metrics_zeros_nulls_and_linear_percentile():
    frame = pd.DataFrame(
        {"forecast_mw": [2.0, 2.0, 8.0, None], "actual_mw": [0.0, 4.0, 4.0, 9.0]}
    )
    result = summary(frame)
    assert result["coverage"] == {
        "expected": 4,
        "forecasts": 3,
        "actuals": 4,
        "paired": 3,
        "missing_forecasts": 1,
        "missing_actuals": 0,
        "excluded": 1,
    }
    m = result["metrics"]
    assert m["mae_mw"] == pytest.approx(8 / 3)
    assert m["bias_mw"] == pytest.approx(4 / 3)
    assert m["rmse_mw"] == pytest.approx(8**0.5)
    assert m["p90_absolute_error_mw"] == pytest.approx(3.6)
    assert m["mape_percent"] == 75
    assert m["mape_eligible"] == 2 and m["mape_excluded_zero_actual"] == 1
    assert (
        summary(pd.DataFrame({"forecast_mw": [1.0], "actual_mw": [0.0]}))["metrics"][
            "mape_percent"
        ]
        is None
    )
    empty = summary(pd.DataFrame())
    assert empty["coverage"]["paired"] == 0 and empty["metrics"]["mae_mw"] is None


def test_bucket_boundaries_include_empty_buckets():
    frame = pd.DataFrame(
        {
            "startTime": pd.date_range("2026-01-02", periods=8, freq="h", tz="UTC"),
            "forecast_mw": [2.0] * 8,
            "actual_mw": [1.0] * 8,
            "horizon_hours": [0, 11.99, 12, 24, 36, 48, 72, 100],
        }
    )
    groups = breakdowns(frame)
    assert [g["coverage"]["paired"] for g in groups["horizon"]] == [2, 1, 1, 1, 1, 2]
    assert len(groups["hour"]) == 24
    assert groups["hour"][-1]["metrics"]["mae_mw"] is None


@pytest.mark.parametrize("clock", ["24:00", "9:30", "09:30:00", "09:30Z", "bad"])
def test_cutoff_validation(clock):
    with pytest.raises(ValueError):
        cutoff(DAY, clock)


@pytest.mark.parametrize("value", ["2026-01-02T00:00", "not-a-date"])
def test_invalid_time_conventions(value):
    with pytest.raises(DataError):
        hourly_actuals(actuals([(value, 1)]))


def test_equal_target_publication_retained_negative_horizon_excluded(monkeypatch):
    from backend.app.services import analytics

    # Exercise the generic eligibility boundary at T itself. Normal D-1 controls
    # put the cutoff before delivery, so zero horizon cannot arise in that UI.
    monkeypatch.setattr(
        analytics, "cutoff", lambda *args: pd.Timestamp("2026-01-02T00:00Z")
    )
    selected = select_day(
        forecasts(
            [
                ("2026-01-02T00:00Z", "2026-01-02T00:00Z", 12),
                ("2026-01-02T00:00Z", "2026-01-02T00:01Z", 999),
            ]
        ),
        DAY,
    )
    assert selected.forecast_mw.iloc[0] == 12
    assert selected.horizon_hours.iloc[0] == 0


@pytest.mark.parametrize("generation", [float("nan"), float("inf"), True])
def test_nonfinite_or_boolean_generation_rejected(generation):
    with pytest.raises(DataError):
        normalize(
            forecasts([("2026-01-02T00:00Z", "2026-01-01T09:30Z", generation)]), True
        )
