from datetime import date

from fastapi import APIRouter, Request

from backend.app.data.repository import Repository
from backend.app.schemas.analytics import MetadataResponse

router = APIRouter()
FIRST, LAST = date(2026, 1, 2), date(2026, 2, 1)
ASSUMPTIONS = [
    "D-1 cutoff is assumed decision timing, not a verified market gate closure.",
    "WINDFOR timestamp T identifies the interval [T,T+1h).",
    "All timestamps and delivery hours use UTC.",
]


def repository(request: Request) -> Repository:
    return request.app.state.repository


@router.get("/metadata", response_model=MetadataResponse)
def metadata(request: Request) -> dict:
    return {
        "decision_from": date(2026, 1, 1),
        "decision_to": date(2026, 1, 31),
        "delivery_from": FIRST,
        "delivery_to": LAST,
        "default_cutoff": request.app.state.settings.default_cutoff,
        "timezone": "UTC",
        "source": "Elexon national WIND",
        "units": "MW",
        "assumptions": ASSUMPTIONS,
        "provenance": repository(request).provenance,
    }
