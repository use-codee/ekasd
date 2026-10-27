"""Read-only integrity audit and isolated network-disabled cache rebuilds."""

import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.data.cleaning import (  # noqa: E402
    ACTUAL_COLUMNS,
    FORECAST_COLUMNS,
    clean,
    timestamp,
)
from backend.app.data.ingestion import build, quality_report  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root: Path) -> dict:
    """Independently check every raw pair and stored CSV before any rebuild."""
    errors = []
    manifest = json.loads((root / "data/processed/manifest.json").read_text())
    expected_paths = set()
    for dataset, first, days in (
        ("WINDFOR", date(2025, 12, 30), 33),
        ("FUELHH", date(2026, 1, 2), 31),
    ):
        for n in range(days):
            day = first + timedelta(days=n)
            relative = f"data/raw/{dataset.lower()}/{day}.json"
            expected_paths.add(relative)
            path = root / relative
            if dataset == "WINDFOR":
                params = {
                    "publishDateTimeFrom": f"{day}T00:00:00Z",
                    "publishDateTimeTo": f"{day + timedelta(days=1)}T00:00:00Z",
                }
            else:
                params = {
                    "settlementDateFrom": str(day),
                    "settlementDateTo": str(day),
                    "fuelType": "WIND",
                }
            try:
                body = json.loads(path.read_bytes(), parse_float=Decimal)
                meta = json.loads(path.with_suffix(".meta.json").read_text())
                assert isinstance(body, list) and all(isinstance(r, dict) for r in body)
                assert meta["sha256"] == sha(path), "raw SHA-256 mismatch"
                assert type(meta["records"]) is int and meta["records"] == len(body)
                assert meta["params"] == params, "query window mismatch"
                endpoint = (
                    f"https://data.elexon.co.uk/bmrs/api/v1/datasets/{dataset}/stream"
                )
                assert meta["endpoint"] == endpoint, "endpoint mismatch"
                downloaded = datetime.fromisoformat(
                    meta["downloaded_at"].replace("Z", "+00:00")
                )
                assert downloaded.tzinfo and downloaded.utcoffset() == timedelta(0)
                assert downloaded <= datetime.now(UTC), "future download time"
                entries = [c for c in manifest["chunks"] if c["path"] == relative]
                assert len(entries) == 1, "manifest missing/duplicate raw provenance"
                assert all(entries[0][key] == value for key, value in meta.items()), (
                    "manifest/sidecar provenance mismatch"
                )
            except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
                errors.append(f"{relative}: {exc}")
    if (
        len(manifest["chunks"]) != 64
        or {c["path"] for c in manifest["chunks"]} != expected_paths
    ):
        errors.append("manifest must account for exactly the 64 expected raw paths")
    for filename in ("forecasts.csv", "actuals_half_hourly.csv"):
        try:
            path = root / "data/processed" / filename
            spec = manifest["artifacts"][filename]
            assert sha(path) == spec["sha256"], "processed SHA-256 mismatch"
            assert path.stat().st_size == spec["bytes"], "processed size mismatch"
        except (OSError, KeyError, AssertionError) as exc:
            errors.append(f"{filename}: {exc}")
    if errors:
        raise AssertionError("Integrity audit failed:\n" + "\n".join(errors))
    return manifest


def verify(root: Path) -> dict:
    original = audit(root)
    with tempfile.TemporaryDirectory(prefix="elexon-verify-") as directory:
        isolated = Path(directory)
        # Copy, never symlink, so rebuild code cannot write into the real cache.
        shutil.copytree(root / "data/raw", isolated / "data/raw")
        with (
            patch("httpx.Client.get", side_effect=AssertionError("HTTP forbidden")),
            patch(
                "socket.create_connection",
                side_effect=AssertionError("Network forbidden"),
            ),
            patch("socket.socket", side_effect=AssertionError("Socket forbidden")),
        ):
            for offline in (False, True, True):
                rebuilt = build(isolated, offline=offline)
                assert rebuilt["artifacts"] == original["artifacts"]
                assert rebuilt["quality"] == original["quality"]
                assert all(c["state"] == "reused" for c in rebuilt["chunks"])
                assert [
                    {k: v for k, v in c.items() if k != "state"}
                    for c in original["chunks"]
                ] == [
                    {k: v for k, v in c.items() if k != "state"}
                    for c in rebuilt["chunks"]
                ]
        # Local generated documentation is optional in a clean source checkout.
        # When present, it must still match the stored manifest's run state.
        report = root / "docs/data-quality.md"
        if report.exists():
            assert report.read_text() == quality_report(original)
    for filename, dataset, columns in (
        ("forecasts.csv", "WINDFOR", FORECAST_COLUMNS),
        ("actuals_half_hourly.csv", "FUELHH", ACTUAL_COLUMNS),
    ):
        with (root / "data/processed" / filename).open(newline="") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == columns
            records = list(reader)
        for row in records:
            row["dataset"] = dataset
            if dataset == "FUELHH":
                row["settlementPeriod"] = int(row["settlementPeriod"])
        cleaned, counts = clean(records, dataset)
        assert len(cleaned) == len(records)
        assert counts["duplicates_collapsed"] == counts["negative_horizon"] == 0
        keys = [
            (timestamp(row["startTime"]), timestamp(row["publishTime"]))
            if dataset == "WINDFOR"
            else (timestamp(row["startTime"]),)
            for row in records
        ]
        assert keys == sorted(set(keys))
        # Independent full UTC grid, computed from stored CSVs rather than manifest counts.
        step = 60 if dataset == "WINDFOR" else 30
        expected = {
            datetime(2026, 1, 2, tzinfo=UTC) + timedelta(minutes=step * n)
            for n in range(744 if dataset == "WINDFOR" else 1488)
        }
        assert {key[0] for key in keys} == expected, f"{dataset}: target coverage gap"
    assert audit(root) == original
    return original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Read-only raw/processed integrity audit",
    )
    args = parser.parse_args()
    manifest = audit(ROOT) if args.audit_only else verify(ROOT)
    print("PASS: 64 raw bodies/provenance and both stored CSV checksums verified.")
    if not args.audit_only:
        print("PASS: read-only verification; isolated default + two offline builds;")
        print("HTTP/sockets blocked, CSV hashes and download provenance unchanged;")
        print("1488 actual half-hours and 744 forecast target hours, no gaps.")
    print(json.dumps(manifest["artifacts"], indent=2))


if __name__ == "__main__":
    main()
