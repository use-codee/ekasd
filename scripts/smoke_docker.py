"""Run with: docker compose exec -T backend python - < scripts/smoke_docker.py.

Uses only the container's standard library. No host Python or outbound access.
"""

import json
import math
import re
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.request import urlopen

BASE = "http://frontend:8080"


def get(path: str):
    with urlopen(BASE + path, timeout=15) as response:
        return response.read(), response.headers


def api(path: str):
    body, headers = get("/api/v1/" + path)
    assert "application/json" in headers["Content-Type"]
    return json.loads(body)


def expect_error(path: str, status: int, json_error: bool = False) -> None:
    try:
        get(path)
    except HTTPError as exc:
        assert exc.code == status, (path, exc.code)
        body = exc.read()
        if json_error:
            assert "application/json" in exc.headers["Content-Type"]
            assert "error" in json.loads(body)
        else:
            assert b'<div id="root"' not in body
    else:
        raise AssertionError(f"Expected {status}: {path}")


def main() -> None:
    html, headers = get("/")
    assert b'<div id="root"' in html
    assert b"@vite/client" not in html and b".tsx" not in html
    assert "no-store" in headers["Cache-Control"]
    asset = re.search(rb'src="([^"]+\.js)"', html)
    assert asset
    _, headers = get(asset.group(1).decode())
    assert "immutable" in headers["Cache-Control"]
    assert api("health") == {"status": "ok"}
    metadata = api("metadata")
    assert metadata["delivery_from"] == "2026-01-02"
    assert metadata["delivery_to"] == "2026-02-01"
    for day in ("2026-01-02", "2026-02-01"):
        result = api(f"forecasts?delivery_date={day}&cutoff_time=09:30")
        expected = [
            datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(hours=h)
            for h in range(24)
        ]
        assert [
            datetime.fromisoformat(s["startTime"].replace("Z", "+00:00"))
            for s in result["slots"]
        ] == expected
        assert all("actual_mw" not in slot for slot in result["slots"])
    default = api("forecasts?delivery_date=2026-01-02&cutoff_time=09:30")
    earlier = api("forecasts?delivery_date=2026-01-02&cutoff_time=00:00")
    assert earlier["coverage"]["forecasts"] == 22
    assert default["slots"][0]["publish_time"] != earlier["slots"][0]["publish_time"]
    accuracy = api(
        "accuracy?delivery_from=2026-01-02&delivery_to=2026-02-01&cutoff_time=09:30"
    )
    assert len(accuracy["slots"]) == accuracy["coverage"]["paired"] == 744
    for key, expected in {
        "mae_mw": 2013.008064516129,
        "rmse_mw": 2505.943149370381,
        "bias_mw": 1729.9314516129032,
        "p90_absolute_error_mw": 4143.85,
        "mape_percent": 21.61015681846638,
    }.items():
        assert math.isclose(accuracy["metrics"][key], expected, rel_tol=1e-10), key
    expect_error("/api/v1/forecasts?cutoff_time=25:00", 422, json_error=True)
    expect_error("/api/v1/does-not-exist", 404, json_error=True)
    expect_error("/assets/missing.js", 404)
    expect_error("/missing.css", 404)
    spa, headers = get("/review-route")
    assert spa == html and "no-store" in headers["Cache-Control"]
    print(
        "PASS: built UI, asset caching, health/metadata, first/last days, changed cutoff,"
    )
    print("744-pair baseline, JSON failures, missing assets and separate SPA fallback.")
    print(
        json.dumps(
            {"coverage": accuracy["coverage"], "metrics": accuracy["metrics"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
