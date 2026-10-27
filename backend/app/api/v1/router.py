from fastapi import APIRouter

from backend.app.api.v1.accuracy import router as accuracy_router
from backend.app.api.v1.forecasts import router as forecast_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.metadata import router as metadata_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)

router.include_router(metadata_router)
router.include_router(forecast_router)
router.include_router(accuracy_router)
