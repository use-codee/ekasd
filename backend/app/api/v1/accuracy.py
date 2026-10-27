from fastapi import APIRouter, Request

from backend.app.api.v1.forecasts import Cutoff, DateParam, validate_range
from backend.app.api.v1.metadata import FIRST, LAST, repository
from backend.app.schemas.analytics import AccuracyResponse
from backend.app.services.analytics import breakdowns, evaluate, records, summary
from backend.app.services.buffer import explain

router = APIRouter()
LIMITATION = (
    "The cause of the forecast bias remains unknown. Alignment tests are diagnostic "
    "only; production values are not shifted or scaled. This wind-only sample does "
    "not establish curtailment or provide an optimal purchasing recommendation."
)


@router.get("/accuracy", response_model=AccuracyResponse)
def accuracy(
    request: Request,
    delivery_from: DateParam = FIRST,
    delivery_to: DateParam = LAST,
    cutoff_time: Cutoff | None = None,
) -> dict:
    validate_range(delivery_from, delivery_to)
    clock = cutoff_time or request.app.state.settings.default_cutoff
    repo = repository(request)
    frame = evaluate(repo.forecasts, repo.hourly, delivery_from, delivery_to, clock)
    result = summary(frame)
    return {
        "delivery_from": delivery_from,
        "delivery_to": delivery_to,
        "cutoff_time": clock,
        **result,
        "slots": records(frame),
        "breakdowns": breakdowns(frame),
        "buffer": explain(result, str(delivery_from), str(delivery_to), clock),
        "diagnostic_limitation": LIMITATION,
    }
