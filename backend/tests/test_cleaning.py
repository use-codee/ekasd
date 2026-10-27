from datetime import UTC, datetime
from decimal import Decimal

import pytest

from backend.app.data.cleaning import QualityError, clean, coverage, timestamp


def forecast(**updates):
    return {
        "dataset": "WINDFOR",
        "publishTime": "2026-01-01T09:30:00Z",
        "startTime": "2026-01-02T00:00:00Z",
        "generation": 123,
        **updates,
    }


def actual(**updates):
    return {
        "dataset": "FUELHH",
        "startTime": "2026-01-02T00:00:00Z",
        "settlementDate": "2026-01-02",
        "settlementPeriod": 1,
        "fuelType": "WIND",
        "generation": 123,
        **updates,
    }


@pytest.mark.parametrize("dataset,factory", [("WINDFOR", forecast), ("FUELHH", actual)])
def test_identical_duplicates_collapse_and_conflicts_stop(dataset, factory):
    rows, counts = clean([factory(), factory()], dataset)
    assert len(rows) == 1
    assert counts["duplicates_collapsed"] == 1
    with pytest.raises(QualityError, match="conflicting duplicates"):
        clean([factory(), factory(generation=999)], dataset)


@pytest.mark.parametrize(
    "change",
    [
        {"startTime": "2026-01-02T00:00:00"},
        {"startTime": "2026-01-02T00:30:00Z"},
        {"publishTime": "bad"},
        {"generation": "NaN"},
        {"generation": "Infinity"},
        {"generation": True},
        {"generation": None},
        {"generation": "abc"},
        {"dataset": "OTHER"},
        {"startTime": "2026-01-02T00:00:00+01:00"},
    ],
)
def test_invalid_forecasts_block_publication(change):
    with pytest.raises(QualityError, match="invalid rows"):
        clean([forecast(**change)], "WINDFOR")


def test_boundaries_order_zero_horizon_and_decimal_precision():
    records = [
        forecast(publishTime="2025-12-29T23:59:59Z"),
        forecast(publishTime="2026-02-01T00:00:00Z", startTime="2026-02-01T01:00:00Z"),
        forecast(
            publishTime="2025-12-30T00:00:00Z",
            generation=Decimal("1.123456789123456789"),
        ),
        forecast(startTime="2026-01-01T00:00:00Z"),  # negative horizon before delivery
        forecast(publishTime="2026-01-02T00:00:00Z", generation=0),
        forecast(startTime="2026-02-02T00:00:00Z"),
        forecast(startTime="2026-02-01T23:00:00Z", generation=-1),
        forecast(startTime="2026-01-01T23:00:00Z"),
    ]
    rows, counts = clean(records, "WINDFOR")
    assert counts["outside_publication"] == 2
    assert counts["negative_horizon"] == 1
    assert counts["outside_delivery"] == 2
    assert counts["processed_rows"] == 3
    assert rows[0]["generation"] == Decimal("1.123456789123456789")
    assert rows[1]["generation"] == 0
    assert counts["negative_generation"] == 1
    assert rows == sorted(rows, key=lambda row: (row["startTime"], row["publishTime"]))


def test_each_daily_publication_window_is_half_open():
    lower = timestamp("2026-01-01T00:00:00Z")
    upper = timestamp("2026-01-02T00:00:00Z")
    rows, counts = clean(
        [forecast(publishTime="2026-01-02T00:00:00Z")], "WINDFOR", [(lower, upper)]
    )
    assert rows == []
    assert counts["outside_publication"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"settlementDate": "2026-01-03"},
        {"settlementPeriod": 2},
        {"settlementPeriod": True},
        {"fuelType": "GAS"},
        {"startTime": "2026-01-02T00:15:00Z"},
    ],
)
def test_invalid_actual_metadata(change):
    with pytest.raises(QualityError):
        clean([actual(**change)], "FUELHH")


def test_actual_gap_not_hidden_by_duplicate_and_midnight_period_valid():
    rows, counts = clean(
        [
            actual(),
            actual(),
            actual(
                startTime="2026-02-01T23:30:00Z",
                settlementDate="2026-02-01",
                settlementPeriod=48,
            ),
        ],
        "FUELHH",
    )
    result = coverage(rows, 30)
    assert counts["duplicates_collapsed"] == 1
    assert result["expected"] == 1488
    assert result["observed"] == 2
    assert "2026-01-02T00:30:00Z" in result["missing"]
    assert rows[0]["startTime"] == datetime(2026, 1, 2, tzinfo=UTC)
