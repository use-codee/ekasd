import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.analyze_wind import analyze

ROOT = Path(__file__).resolve().parents[2]
HASHES = {
    "forecasts.csv": "95b8a7f5e5324e9ea76ce9e3e5e24e484ce7dfb532e5d3888b3be2275305f5a0",
    "actuals_half_hourly.csv": (
        "f31240cb6445b32c5743db26ae8239397c588fd7e29bc965e56b5c827bdd5239"
    ),
}


def assert_baseline_matches(actual, expected, path="baseline"):
    """Keep structure/data exact, allowing only tiny numerical rounding drift."""
    assert type(actual) is type(expected), path
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), path
        for key, value in expected.items():
            assert_baseline_matches(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), path
        for index, value in enumerate(expected):
            assert_baseline_matches(actual[index], value, f"{path}[{index}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-12, abs=1e-12), path
    else:
        assert actual == expected, path


def test_baseline_comparison_allows_cross_platform_float_rounding():
    assert_baseline_matches(
        {"shifts": [{"correlation": 0.9314096280658399}]},
        {"shifts": [{"correlation": 0.9314096280658403}]},
    )


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ({"correlation": 0.93}, {"correlation": 0.94}),
        ({"paired": 743}, {"paired": 744}),
        ({"paired": 744.0}, {"paired": 744}),
        ({"checksum": "changed"}, {"checksum": "original"}),
        ({"shifts": []}, {"shifts": [{"correlation": 0.93}]}),
        ({}, {"correlation": 0.93}),
    ],
)
def test_baseline_comparison_still_rejects_changed_results(actual, expected):
    with pytest.raises(AssertionError):
        assert_baseline_matches(actual, expected)


def test_corrected_frozen_full_scope_baseline():
    for name, checksum in HASHES.items():
        assert (
            hashlib.sha256((ROOT / "data/processed" / name).read_bytes()).hexdigest()
            == checksum
        )
    with patch(
        "socket.socket", side_effect=AssertionError("external network forbidden")
    ):
        computed = analyze()
    saved = json.loads(
        (Path(__file__).parent / "fixtures/regression-baseline.json").read_text()
    )
    assert_baseline_matches(computed, saved)
    assert computed["inputs"] == HASHES
    assert computed["coverage"]["expected"] == 24 * 31
    assert computed["coverage"]["paired"] == computed["coverage"]["actuals"] == 744
    assert computed["metrics"]["mae_mw"] == pytest.approx(2013.008064516129)
    assert computed["metrics"]["bias_mw"] == pytest.approx(1729.9314516129032)
    assert computed["horizon_hours"] == [14.5, 37.5]
    assert computed["shift_common_count"] == 738
