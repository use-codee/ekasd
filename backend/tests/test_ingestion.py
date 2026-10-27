import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from backend.app.data import ingestion as ing
from backend.app.data.cleaning import QualityError


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_429_retry_after_then_transient_503_then_success():
    statuses = iter([429, 503, 200])
    waits = []

    def handler(request):
        return httpx.Response(next(statuses), headers={"Retry-After": "9"}, json=[])

    with client_for(handler) as client:
        assert ing.fetch(client, "WINDFOR", "day", {}, sleep=waits.append) == b"[]"
    assert waits == [9, 9]
    assert ing.retry_delay("999", 1) == 30
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=15))
    assert 13 <= ing.retry_delay(future, 1) <= 15
    assert ing.retry_delay("invalid", 2) == 2


def test_network_retry_and_exhaustion():
    attempts = []
    waits = []

    def handler(request):
        attempts.append(request)
        raise httpx.ReadTimeout("timeout", request=request)

    with client_for(handler) as client, pytest.raises(ing.IngestionError):
        ing.fetch(client, "FUELHH", "day", {}, sleep=waits.append)
    assert len(attempts) == 4
    assert waits == [1, 2, 4]


def test_network_failure_recovers():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("connection lost", request=request)
        return httpx.Response(200, json=[])

    with client_for(handler) as client:
        ing.fetch(client, "WINDFOR", "day", {}, sleep=lambda _: None)
    assert len(calls) == 2


@pytest.mark.parametrize("status,expected", [(400, 1), (401, 1), (404, 1), (503, 4)])
def test_permanent_failure_and_exhausted_server_retries(status, expected):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    with client_for(handler) as client, pytest.raises(ing.IngestionError):
        ing.fetch(client, "WINDFOR", "day", {}, sleep=lambda _: None)
    assert len(calls) == expected


def test_invalid_json_response_not_cached(tmp_path):
    with client_for(
        lambda r: httpx.Response(200, content=b'{"error": "bad"}')
    ) as client:
        with pytest.raises(ing.IngestionError, match="JSON array"):
            ing.raw_chunk(tmp_path, *ing.windows()[0], client, False, False)
    assert not list(tmp_path.rglob("*.json"))


def test_raw_bytes_cache_reuse_refresh_and_original_provenance(tmp_path):
    chunk = ing.windows()[0]
    body = b"[ ]\n"
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=body)

    with client_for(handler) as client:
        _, first = ing.raw_chunk(tmp_path, *chunk, client, False, False)
        _, reused = ing.raw_chunk(tmp_path, *chunk, None, False, True)
        _, refreshed = ing.raw_chunk(tmp_path, *chunk, client, True, False)
    assert (tmp_path / first["path"]).read_bytes() == body
    assert first["downloaded_at"] == reused["downloaded_at"]
    assert reused["state"] == "reused"
    assert refreshed["state"] == "downloaded"
    assert len(calls) == 2
    (tmp_path / first["path"]).write_bytes(b"[]")
    with pytest.raises(ing.IngestionError, match="Corrupt/incomplete"):
        ing.raw_chunk(tmp_path, *chunk, None, False, True)


def test_offline_missing_and_incomplete_cache(tmp_path):
    chunk = ing.windows()[0]
    with pytest.raises(ing.IngestionError, match="missing raw chunk"):
        ing.raw_chunk(tmp_path, *chunk, None, False, True)
    path = tmp_path / "data/raw/windfor/2025-12-30.json"
    ing.atomic(path, b"[]")
    with pytest.raises(ing.IngestionError, match="Corrupt/incomplete"):
        ing.raw_chunk(tmp_path, *chunk, None, False, True)


def test_incomplete_download_keeps_processed_output(tmp_path):
    path = tmp_path / "data/processed/forecasts.csv"
    ing.atomic(path, b"previous valid cache")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[]) if len(calls) == 1 else httpx.Response(400)

    with client_for(handler) as client, pytest.raises(ing.IngestionError):
        ing.build(tmp_path, client=client)
    assert path.read_bytes() == b"previous valid cache"
    assert (tmp_path / "data/raw/windfor/2025-12-30.json").exists()


def test_failed_cleaning_keeps_all_processed_output(tmp_path, monkeypatch):
    window = (
        "WINDFOR",
        "2026-01-01",
        {
            "publishDateTimeFrom": "2026-01-01T00:00:00Z",
            "publishDateTimeTo": "2026-01-02T00:00:00Z",
        },
    )
    monkeypatch.setattr(ing, "windows", lambda: [window])
    path = tmp_path / "data/processed/forecasts.csv"
    ing.atomic(path, b"previous valid cache")
    with client_for(
        lambda r: httpx.Response(200, json=[{"dataset": "WINDFOR"}])
    ) as client:
        with pytest.raises(QualityError):
            ing.build(tmp_path, client=client)
    assert path.read_bytes() == b"previous valid cache"


def test_offline_rebuild_identical_csv_and_zero_http(tmp_path, monkeypatch):
    # All 64 inputs accounted for, tiny deterministic synthetic source arrays.
    with client_for(lambda r: httpx.Response(200, json=[])) as client:
        original = ing.build(tmp_path, client=client)

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline/cache reuse attempted HTTP")

    monkeypatch.setattr(httpx.Client, "get", forbidden)
    rebuilt = ing.build(tmp_path, offline=True)
    reused = ing.build(tmp_path)
    assert original["artifacts"] == rebuilt["artifacts"] == reused["artifacts"]
    assert len(rebuilt["chunks"]) == 64
    assert all(c["state"] == "reused" for c in rebuilt["chunks"])
    assert [c["downloaded_at"] for c in original["chunks"]] == [
        c["downloaded_at"] for c in rebuilt["chunks"]
    ]
    manifest = json.loads((tmp_path / "data/processed/manifest.json").read_text())
    assert manifest["quality"]["actual_coverage"]["observed"] == 0
    assert len(manifest["quality"]["actual_coverage"]["missing"]) == 1488


def test_processed_write_error_rolls_back(tmp_path, monkeypatch):
    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    ing.atomic(first, b"old first")
    ing.atomic(second, b"old second")
    original = ing.atomic

    def fail_second(path: Path, body: bytes):
        if path == second:
            raise OSError("disk error")
        original(path, body)

    monkeypatch.setattr(ing, "atomic", fail_second)
    with pytest.raises(OSError):
        ing.publish({first: b"new first", second: b"new second"})
    assert first.read_bytes() == b"old first"
    assert second.read_bytes() == b"old second"


@pytest.mark.parametrize("content", [b"{bad json", b"[", b"null", b"\xff"])
def test_offline_corrupt_json_has_clear_error(tmp_path, content):
    chunk = ing.windows()[0]
    with client_for(lambda r: httpx.Response(200, json=[])) as client:
        _, meta = ing.raw_chunk(tmp_path, *chunk, client, False, False)
    (tmp_path / meta["path"]).write_bytes(content)
    with pytest.raises(ing.IngestionError, match="Corrupt/incomplete"):
        ing.raw_chunk(tmp_path, *chunk, None, False, True)


def test_invalid_provenance_rejected(tmp_path):
    chunk = ing.windows()[0]
    with client_for(lambda r: httpx.Response(200, json=[])) as client:
        _, meta = ing.raw_chunk(tmp_path, *chunk, client, False, False)
    (tmp_path / meta["path"]).with_suffix(".meta.json").write_text("[]")
    with pytest.raises(ing.IngestionError, match="provenance must be an object"):
        ing.raw_chunk(tmp_path, *chunk, None, False, True)


def test_focused_repair_only_redownloads_invalid_chunk(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    with client_for(handler) as client:
        original = ing.build(tmp_path, client=client)
        damaged = tmp_path / original["chunks"][1]["path"]
        damaged.write_bytes(b"[ ]")
        requests.clear()
        repaired = ing.build(tmp_path, repair=True, client=client)
    assert len(requests) == 1
    assert repaired["chunks"][1]["state"] == "downloaded"
    assert sum(c["state"] == "reused" for c in repaired["chunks"]) == 63
    assert repaired["artifacts"] == original["artifacts"]
    assert all(
        a["downloaded_at"] == b["downloaded_at"]
        for i, (a, b) in enumerate(
            zip(original["chunks"], repaired["chunks"], strict=True)
        )
        if i != 1
    )


def test_verifier_failure_does_not_rewrite_cache(tmp_path):
    from scripts.verify_elexon_cache import verify

    with client_for(lambda r: httpx.Response(200, json=[])) as client:
        ing.build(tmp_path, client=client)
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    # Rebuilding succeeds; real coverage assertion fails for this empty fixture.
    # The old verifier overwrote manifest/report before reaching that assertion.
    with pytest.raises(AssertionError, match="target coverage gap"):
        verify(tmp_path)
    assert before == {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }


def test_verifier_rejects_damaged_processed_file_without_repairing_it(tmp_path):
    from scripts.verify_elexon_cache import verify

    with client_for(lambda r: httpx.Response(200, json=[])) as client:
        ing.build(tmp_path, client=client)
    path = tmp_path / "data/processed/forecasts.csv"
    path.write_bytes(b"damaged")
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    with pytest.raises(AssertionError, match="processed SHA-256 mismatch"):
        verify(tmp_path)
    assert before == {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
