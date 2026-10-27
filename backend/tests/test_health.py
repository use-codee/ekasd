import pandas as pd
from fastapi.testclient import TestClient

from backend.app.data.repository import MemoryRepository
from backend.app.main import create_app


def health_app():
    return create_app(
        MemoryRepository(
            pd.DataFrame(columns=["startTime", "publishTime", "generation"]),
            pd.DataFrame(columns=["startTime", "generation"]),
        )
    )


def test_health_returns_typed_liveness_response() -> None:
    with TestClient(health_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_local_frontend_origin_is_allowed() -> None:
    with TestClient(health_app()) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
