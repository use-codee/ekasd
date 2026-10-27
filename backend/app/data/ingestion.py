"""Sequential Elexon downloader with verified daily raw cache and offline rebuild."""

import csv
import hashlib
import io
import json
import logging
import os
import tempfile
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from backend.app.data.cleaning import (
    ACTUAL_COLUMNS,
    FORECAST_COLUMNS,
    clean,
    coverage,
    stamp,
    timestamp,
)

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
VERSION = "2.0.0"
LOG = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    pass


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".ingest-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def decode(body: bytes) -> list[dict]:
    try:
        rows = json.loads(body, parse_float=Decimal)
    except (ValueError, UnicodeDecodeError) as exc:
        raise IngestionError(f"Invalid raw JSON: {exc}") from exc
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise IngestionError("Expected a JSON array of source records")
    return rows


def windows() -> list[tuple[str, str, dict]]:
    result = []
    for dataset, first, days in (
        ("WINDFOR", date(2025, 12, 30), 33),
        ("FUELHH", date(2026, 1, 2), 31),
    ):
        for n in range(days):
            day = first + timedelta(days=n)
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
            result.append((dataset, str(day), params))
    return result


def retry_delay(value: str | None, attempt: int) -> float:
    delay = min(2 ** (attempt - 1), 30)
    if value:
        try:
            delay = max(delay, float(value))
        except ValueError:
            try:
                delay = max(
                    delay,
                    (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds(),
                )
            except (ValueError, TypeError, OverflowError):
                pass
    return max(0, min(delay, 30))


def fetch(
    client: httpx.Client, dataset: str, day: str, params: dict, sleep=time.sleep
) -> bytes:
    # Four attempts, 30-second timeout each, <=90 seconds total backoff.
    for attempt in range(1, 5):
        response = None
        try:
            response = client.get(f"{BASE}/{dataset}/stream", params=params, timeout=30)
            LOG.info(
                "dataset=%s window=%s attempt=%s status=%s",
                dataset,
                day,
                attempt,
                response.status_code,
            )
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                raise httpx.HTTPStatusError(
                    "transient response", request=response.request, response=response
                )
            response.raise_for_status()
            decode(response.content)
            return response.content
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            transient = (
                response is None
                or response.status_code == 429
                or response.status_code >= 500
            )
            LOG.warning(
                "dataset=%s window=%s attempt=%s failure=%s", dataset, day, attempt, exc
            )
            if not transient or attempt == 4:
                raise IngestionError(f"{dataset} {day}: request failed: {exc}") from exc
            sleep(
                retry_delay(
                    response.headers.get("Retry-After") if response else None, attempt
                )
            )
    raise AssertionError("unreachable")


def raw_chunk(
    root: Path,
    dataset: str,
    day: str,
    params: dict,
    client: httpx.Client | None,
    refresh: bool,
    offline: bool,
) -> tuple[list, dict]:
    path = root / "data/raw" / dataset.lower() / f"{day}.json"
    meta_path = path.with_suffix(".meta.json")
    if not refresh and (path.exists() or meta_path.exists()):
        try:
            body = path.read_bytes()
            meta = json.loads(meta_path.read_text())
            rows = decode(body)
            if not isinstance(meta, dict):
                raise ValueError("provenance must be an object")
            timestamp(meta["downloaded_at"])
            if (
                meta["sha256"] != digest(body)
                or meta["records"] != len(rows)
                or meta["params"] != params
                or meta["endpoint"] != f"{BASE}/{dataset}/stream"
                or not meta["downloaded_at"]
            ):
                raise ValueError("raw provenance/checksum mismatch")
        except (OSError, ValueError, KeyError, TypeError, IngestionError) as exc:
            raise IngestionError(
                f"Corrupt/incomplete cache {path}; use --refresh: {exc}"
            ) from exc
        state = "reused"
    elif offline:
        raise IngestionError(f"Offline rebuild requires missing raw chunk: {path}")
    else:
        if client is None:
            raise IngestionError("Online download requires an HTTP client")
        body = fetch(client, dataset, day, params)
        rows = decode(body)
        meta = {
            "endpoint": f"{BASE}/{dataset}/stream",
            "params": params,
            "downloaded_at": stamp(datetime.now(UTC)),
            "sha256": digest(body),
            "records": len(rows),
        }
        atomic(path, body)
        atomic(meta_path, json_bytes(meta))
        state = "downloaded"
    LOG.info("dataset=%s window=%s state=%s records=%s", dataset, day, state, len(rows))
    return rows, {**meta, "path": str(path.relative_to(root)), "state": state}


def csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: stamp(value) if isinstance(value, datetime) else value
                for key, value in row.items()
            }
        )
    return buffer.getvalue().encode()


def build(
    root: Path,
    *,
    offline: bool = False,
    refresh: bool = False,
    repair: bool = False,
    client: httpx.Client | None = None,
) -> dict:
    if sum((offline, refresh, repair)) > 1:
        raise IngestionError("--offline, --refresh and --repair are mutually exclusive")
    source: dict[str, list] = {"WINDFOR": [], "FUELHH": []}
    publication_bounds = []
    chunks = []
    for dataset, day, params in windows():
        if repair:
            try:
                rows, meta = raw_chunk(root, dataset, day, params, None, False, True)
            except IngestionError as exc:
                LOG.warning("Repairing dataset=%s window=%s: %s", dataset, day, exc)
                rows, meta = raw_chunk(root, dataset, day, params, client, True, False)
        else:
            rows, meta = raw_chunk(root, dataset, day, params, client, refresh, offline)
        source[dataset].extend(rows)
        if dataset == "WINDFOR":
            publication_bounds.extend(
                [
                    (
                        timestamp(params["publishDateTimeFrom"]),
                        timestamp(params["publishDateTimeTo"]),
                    )
                ]
                * len(rows)
            )
        chunks.append(meta)
    forecasts, fc = clean(source["WINDFOR"], "WINDFOR", publication_bounds)
    actuals, ac = clean(source["FUELHH"], "FUELHH")
    actual_coverage = coverage(actuals, 30)
    target_coverage = coverage(forecasts, 60)
    publications = Counter(stamp(row["publishTime"]) for row in forecasts)
    raw_publications = {
        stamp(timestamp(row["publishTime"])) for row in source["WINDFOR"]
    }
    raw_by_date = Counter(value[:10] for value in raw_publications)
    by_date = Counter()
    for publication in publications:
        by_date[publication[:10]] += 1
    horizons = [
        (row["startTime"] - row["publishTime"]).total_seconds() / 3600
        for row in forecasts
    ]
    artifacts = {
        "forecasts.csv": csv_bytes(forecasts, FORECAST_COLUMNS),
        "actuals_half_hourly.csv": csv_bytes(actuals, ACTUAL_COLUMNS),
    }
    manifest = {
        "transformation_version": VERSION,
        "built_at": stamp(datetime.now(UTC)),
        "offline": offline,
        "chunks": chunks,
        "scope": {
            "decision_dates": ["2026-01-01", "2026-01-31"],
            "delivery_interval": ["2026-01-02T00:00:00Z", "2026-02-02T00:00:00Z"],
            "publication_interval": ["2025-12-30T00:00:00Z", "2026-02-01T00:00:00Z"],
        },
        "schemas": {
            "forecasts.csv": FORECAST_COLUMNS,
            "actuals_half_hourly.csv": ACTUAL_COLUMNS,
        },
        "field_types": {
            "publishTime": "ISO 8601 timezone-aware UTC timestamp",
            "startTime": "ISO 8601 timezone-aware UTC interval start",
            "generation": "finite decimal MW; preserved without binary-float rounding",
            "settlementDate": "ISO date",
            "settlementPeriod": "integer, 1..48",
            "fuelType": "literal WIND",
        },
        "artifacts": {
            name: {"sha256": digest(body), "bytes": len(body)}
            for name, body in artifacts.items()
        },
        "quality": {
            "forecasts": fc,
            "actuals": ac,
            "actual_coverage": actual_coverage,
            "forecast_target_coverage": target_coverage,
            "publications_by_date": dict(sorted(by_date.items())),
            "raw_publications_by_date": dict(sorted(raw_by_date.items())),
            "raw_publication_range": [
                min(raw_publications, default=None),
                max(raw_publications, default=None),
            ],
            "publication_range": [
                min(publications, default=None),
                max(publications, default=None),
            ],
            "target_range": [
                stamp(forecasts[0]["startTime"]) if forecasts else None,
                stamp(forecasts[-1]["startTime"]) if forecasts else None,
            ],
            "horizon_hours": [min(horizons, default=None), max(horizons, default=None)],
            "generation_summary_mw": {
                name: {
                    "minimum": str(min((r["generation"] for r in rows), default="")),
                    "maximum": str(max((r["generation"] for r in rows), default="")),
                    "zero_rows": sum(r["generation"] == 0 for r in rows),
                }
                for name, rows in (("forecasts", forecasts), ("actuals", actuals))
            },
        },
    }
    # Finish all downloads, validation and serialization before touching output.
    report = quality_report(manifest)
    artifacts["manifest.json"] = json_bytes(manifest)
    outputs = {root / "data/processed" / name: body for name, body in artifacts.items()}
    outputs[root / "docs/data-quality.md"] = report.encode()
    publish(outputs)
    return manifest


def publish(outputs: dict[Path, bytes]) -> None:
    """Atomic individual replacements, with rollback on a recoverable write error."""
    previous = {path: path.read_bytes() if path.exists() else None for path in outputs}
    written = []
    try:
        for path, body in outputs.items():
            atomic(path, body)
            written.append(path)
    except OSError:
        for path in reversed(written):
            if previous[path] is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, previous[path])
        raise


def quality_report(manifest: dict) -> str:
    q = manifest["quality"]
    states = Counter(chunk["state"] for chunk in manifest["chunks"])
    cleaning_counts = json.dumps(
        {"WINDFOR": q["forecasts"], "FUELHH": q["actuals"]},
        indent=2,
        sort_keys=True,
    )
    return f"""# Elexon data quality report

Generated {manifest["built_at"]}; transformation {VERSION}.

All 64 requested daily chunks accounted for: 33 WINDFOR publication windows and
31 FUELHH settlement days.
Downloaded: {states["downloaded"]}; reused: {states["reused"]}.
Download completeness does not imply source coverage completeness.

## Cleaning counts

Order: schema/source validation → daily and global half-open publication bounds
→ duplicate checks → negative horizon removal → delivery scope filter.
Counts are disjoint;
raw = invalid + outside publication + duplicates collapsed + negative horizon +
outside delivery + processed.
Invalid schema or conflicting duplicates block publication.

```json
{cleaning_counts}
```

## Coverage and source observations

Actuals: {q["actual_coverage"]["observed"]} unique half-hours / 1488 expected.
Forecast targets: {q["forecast_target_coverage"]["observed"]} unique hours
/ 744 expected.
Publication range: {q["publication_range"]}. Target range: {q["target_range"]}.
Retained forecast horizon range (hours): {q["horizon_hours"]}.
No generation values are clipped or zero-filled. Negative generation counts are
reported above for investigation; finite values including zero are preserved.
Retained generation ranges and zero counts (MW):
```json
{json.dumps(q["generation_summary_mw"], indent=2, sort_keys=True)}
```
Publication counts below describe unique publications among retained forecasts,
not a guaranteed daily schedule. Raw per-chunk counts are in the manifest.

```json
{json.dumps(q["publications_by_date"], indent=2, sort_keys=True)}
```

Raw publication range: {q["raw_publication_range"]}.
Raw unique publications by date, before cleaning:
```json
{json.dumps(q["raw_publications_by_date"], indent=2, sort_keys=True)}
```

Missing actual half-hours:
```json
{json.dumps(q["actual_coverage"]["missing"], indent=2)}
```
Missing forecast target hours:
```json
{json.dumps(q["forecast_target_coverage"]["missing"], indent=2)}
```

Default-cutoff availability has not been assessed. No cutoff selection, hourly
actual aggregation, corrected analytics baseline, or bias cause is assessed in
Phase 2. Source gaps remain missing. Empty successful source responses count as
completed downloads but cannot establish coverage. See manifest for checksums,
source queries, exact counts and original UTC download provenance.
"""
