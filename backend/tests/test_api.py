from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.data.repository import FileRepository, MemoryRepository
from backend.app.main import create_app
from backend.app.services.analytics import DataError, evaluate, summary


@pytest.fixture
def repo():
    return FileRepository()


def empty_repo():
    return MemoryRepository(
        pd.DataFrame(columns=["startTime", "publishTime", "generation"]),
        pd.DataFrame(columns=["startTime", "generation"]),
    )


def test_success_metadata_decision_accuracy_and_no_request_io(repo):
    with patch(
        "socket.create_connection", side_effect=AssertionError("network forbidden")
    ):
        with TestClient(create_app(repo)) as client:
            with (
                patch.object(
                    Path, "read_bytes", side_effect=AssertionError("request file read")
                ),
                patch.object(
                    Path, "read_text", side_effect=AssertionError("request file read")
                ),
                patch(
                    "pandas.read_csv", side_effect=AssertionError("request CSV reload")
                ),
            ):
                metadata = client.get("/api/v1/metadata").json()
                first = client.get("/api/v1/forecasts?delivery_date=2026-01-02").json()
                last = client.get(
                    "/api/v1/forecasts?delivery_date=2026-02-01&cutoff_time=00:00"
                ).json()
                result = client.get("/api/v1/accuracy").json()
                assert client.get("/api/v1/accuracy").json() == result
    assert metadata["delivery_to"] == "2026-02-01"
    assert first["decision_date"] == "2026-01-01"
    assert first["cutoff_utc"] == "2026-01-01T09:30:00Z"
    assert len(first["slots"]) == len(last["slots"]) == 24
    assert "actual_mw" not in first["slots"][0]
    assert len(result["slots"]) == 744
    expected = summary(
        evaluate(repo.forecasts, repo.hourly, date(2026, 1, 2), date(2026, 2, 1))
    )
    assert result["metrics"] == expected["metrics"]
    assert result["coverage"] == expected["coverage"]
    assert "not a calibrated" in result["buffer"]["message"]


@pytest.mark.parametrize(
    "query",
    [
        "/forecasts?delivery_date=no",
        "/forecasts?delivery_date=1767312000",
        "/forecasts?cutoff_time=0١:30",
        "/forecasts?delivery_date=2026-01-01",
        "/forecasts?delivery_date=2026-02-02",
        "/forecasts?cutoff_time=24:00",
        "/forecasts?cutoff_time=9:30",
        "/forecasts?cutoff_time=09:30:00",
        "/forecasts?cutoff_time=09:30Z",
        "/accuracy?delivery_from=2026-02-01&delivery_to=2026-01-02",
        "/accuracy?delivery_to=2026-02-02",
        "/accuracy?cutoff_time=bad",
    ],
)
def test_consistent_validation_envelope(query):
    with TestClient(create_app(empty_repo())) as client:
        response = client.get("/api/v1" + query)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "details" in response.json()["error"]


def test_empty_results_nulls_http_error_and_server_error():
    repo = empty_repo()
    with TestClient(create_app(repo), raise_server_exceptions=False) as client:
        result = client.get("/api/v1/accuracy").json()
        assert result["coverage"]["paired"] == 0
        assert result["metrics"]["mae_mw"] is None
        assert all(
            s["actual_mw"] is None and s["forecast_mw"] is None for s in result["slots"]
        )
        assert client.get("/bad").json()["error"]["code"] == "http_error"
        repo.forecasts = None
        response = client.get("/api/v1/forecasts")
        assert response.status_code == 500
        assert response.json()["error"] == {
            "code": "internal_error",
            "message": "Unable to complete request",
            "details": [],
        }


def test_missing_data_startup_fails_without_network(tmp_path):
    with patch(
        "socket.create_connection", side_effect=AssertionError("network forbidden")
    ):
        with pytest.raises(DataError, match="Cannot load validated local data"):
            with TestClient(create_app(settings=Settings(processed_dir=tmp_path))):
                pass


def test_settings_override_default_cutoff(monkeypatch):
    monkeypatch.setenv("WIND_DEFAULT_CUTOFF", "10:45")
    with TestClient(create_app(empty_repo())) as client:
        assert client.get("/api/v1/metadata").json()["default_cutoff"] == "10:45"
        assert client.get("/api/v1/forecasts").json()["cutoff_time"] == "10:45"
