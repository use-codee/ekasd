import re
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BeforeValidator

from backend.app.api.v1.metadata import ASSUMPTIONS, FIRST, LAST, repository
from backend.app.schemas.analytics import DecisionResponse
from backend.app.services.analytics import cutoff, records, select_day

router = APIRouter()
Cutoff = Annotated[
    str,
    Query(
        pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$",
        description="D-1 UTC time HH:MM, minute precision",
    ),
]


def iso_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
    ):
        raise ValueError("Date must use YYYY-MM-DD")
    return date.fromisoformat(value)


DateParam = Annotated[date, BeforeValidator(iso_date)]


def validate_range(first: date, last: date) -> None:
    if first > last or first < FIRST or last > LAST:
        raise HTTPException(
            422, f"Delivery dates must be ordered within {FIRST}–{LAST}, inclusive"
        )


@router.get("/forecasts", response_model=DecisionResponse)
def forecasts(
    request: Request,
    delivery_date: DateParam = FIRST,
    cutoff_time: Cutoff | None = None,
) -> dict:
    validate_range(delivery_date, delivery_date)
    clock = cutoff_time or request.app.state.settings.default_cutoff
    frame = select_day(repository(request).forecasts, delivery_date, clock)
    available = int(frame.forecast_mw.notna().sum())
    return {
        "delivery_date": delivery_date,
        "decision_date": delivery_date - timedelta(days=1),
        "cutoff_time": clock,
        "cutoff_utc": cutoff(delivery_date, clock),
        "coverage": {
            "expected": 24,
            "forecasts": available,
            "missing_forecasts": 24 - available,
        },
        "slots": records(frame),
        "assumptions": ASSUMPTIONS,
    }
