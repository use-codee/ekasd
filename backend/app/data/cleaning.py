"""Deterministic validation for the fixed January decision-date scope."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

PUB_FROM = datetime(2025, 12, 30, tzinfo=UTC)
PUB_TO = datetime(2026, 2, 1, tzinfo=UTC)
DELIVERY_FROM = datetime(2026, 1, 2, tzinfo=UTC)
DELIVERY_TO = datetime(2026, 2, 2, tzinfo=UTC)
FORECAST_COLUMNS = ["publishTime", "startTime", "generation"]
ACTUAL_COLUMNS = [
    "startTime",
    "settlementDate",
    "settlementPeriod",
    "fuelType",
    "generation",
]


class QualityError(ValueError):
    """Validation failed; processed artifacts must not be published."""


def stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError("timestamp must have an explicit UTC offset")
    return result.astimezone(UTC)


def generation(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal, float)):
        raise ValueError("generation must be numeric")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("generation must be numeric") from exc
    if not result.is_finite():
        raise ValueError("generation must be finite")
    return result


def grid(value: datetime, minutes: int) -> None:
    if value.minute % minutes or value.second or value.microsecond:
        raise ValueError(f"startTime must be on the {minutes}-minute grid")


def clean(
    records: list[dict],
    dataset: str,
    publication_bounds: list[tuple[datetime, datetime]] | None = None,
) -> tuple[list[dict], dict]:
    """Order: schema, publication bounds, duplicates, horizon, delivery scope."""
    forecast = dataset == "WINDFOR"
    counts: Counter = Counter(raw_rows=len(records))
    invalid: Counter = Counter()
    parsed: list[tuple[int, dict]] = []
    if publication_bounds is not None and len(publication_bounds) != len(records):
        raise QualityError("Publication provenance must cover every source row")
    for index, row in enumerate(records):
        try:
            if not isinstance(row, dict) or row["dataset"] != dataset:
                raise ValueError("dataset mismatch")
            start = timestamp(row["startTime"])
            grid(start, 60 if forecast else 30)
            item = {"startTime": start, "generation": generation(row["generation"])}
            if forecast:
                item["publishTime"] = timestamp(row["publishTime"])
            else:
                if row["fuelType"] != "WIND":
                    raise ValueError("fuelType must be WIND")
                day = date.fromisoformat(row["settlementDate"])
                period = row["settlementPeriod"]
                if (
                    type(period) is not int
                    or period != start.hour * 2 + 1 + (start.minute // 30)
                    or day != start.date()
                ):
                    raise ValueError("settlement metadata does not match startTime")
                item.update(
                    settlementDate=day, settlementPeriod=period, fuelType="WIND"
                )
            parsed.append((index, item))
        except (KeyError, TypeError, ValueError) as exc:
            invalid[str(exc)] += 1
            if counts["invalid_schema"] < 5:
                counts[f"invalid_example_row_{index}"] += 1
            counts["invalid_schema"] += 1
    counts["schema_valid"] = len(parsed)
    # Invalid source records block publication, rather than silently reducing coverage.
    if invalid:
        raise QualityError(
            f"{dataset}: {counts['invalid_schema']} invalid rows: {invalid}"
        )
    bounded = []
    for index, item in parsed:
        lower, upper = (
            publication_bounds[index] if publication_bounds else (PUB_FROM, PUB_TO)
        )
        if forecast and not (
            PUB_FROM <= item["publishTime"] < PUB_TO
            and lower <= item["publishTime"] < upper
        ):
            counts["outside_publication"] += 1
        else:
            bounded.append(item)
    unique: dict[Any, dict] = {}
    conflicts = []
    for item in bounded:
        key = (
            (item["publishTime"], item["startTime"]) if forecast else item["startTime"]
        )
        if key in unique:
            if unique[key] != item:
                conflicts.append(str(key))
            else:
                counts["duplicates_collapsed"] += 1
        else:
            unique[key] = item
    if conflicts:
        raise QualityError(
            f"{dataset}: {len(conflicts)} conflicting duplicates: {conflicts}"
        )
    result = []
    for item in unique.values():
        if forecast and item["publishTime"] > item["startTime"]:
            counts["negative_horizon"] += 1
        elif not DELIVERY_FROM <= item["startTime"] < DELIVERY_TO:
            counts["outside_delivery"] += 1
        else:
            result.append(item)
    result.sort(
        key=lambda item: (
            (item["startTime"], item["publishTime"])
            if forecast
            else (item["startTime"],)
        )
    )
    for item in result:
        if item["generation"] < 0:
            counts["negative_generation"] += 1
    counts["processed_rows"] = len(result)
    for key in (
        "invalid_schema",
        "outside_publication",
        "duplicates_collapsed",
        "negative_horizon",
        "outside_delivery",
        "negative_generation",
        "conflicting_duplicates",
    ):
        counts.setdefault(key, 0)
    assert counts["raw_rows"] == sum(
        counts[key]
        for key in (
            "invalid_schema",
            "outside_publication",
            "duplicates_collapsed",
            "negative_horizon",
            "outside_delivery",
            "processed_rows",
        )
    )
    return result, dict(counts)


def coverage(rows: list[dict], step: int) -> dict:
    expected = {
        DELIVERY_FROM + timedelta(minutes=step * n)
        for n in range(
            int((DELIVERY_TO - DELIVERY_FROM).total_seconds() // (step * 60))
        )
    }
    observed = {row["startTime"] for row in rows}
    return {
        "expected": len(expected),
        "observed": len(observed),
        "missing": [stamp(t) for t in sorted(expected - observed)],
    }
