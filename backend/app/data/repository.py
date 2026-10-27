"""Startup-only local data access behind an injectable in-memory contract."""

import hashlib
import io
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from backend.app.data.cleaning import ACTUAL_COLUMNS, FORECAST_COLUMNS, clean, timestamp
from backend.app.services.analytics import DataError, hourly_actuals, normalize

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[3] / "data/processed"


class Repository(Protocol):
    forecasts: pd.DataFrame
    hourly: pd.DataFrame
    provenance: dict


class MemoryRepository:
    def __init__(
        self,
        forecasts: pd.DataFrame,
        actuals: pd.DataFrame,
        provenance: dict | None = None,
    ):
        self.forecasts = normalize(forecasts, True)
        self.hourly = hourly_actuals(actuals)
        self.provenance = provenance or {
            "built_at": None,
            "raw_chunks": 0,
            "inputs": {},
        }


class FileRepository(MemoryRepository):
    def __init__(self, directory: Path = DEFAULT_DIRECTORY):
        try:
            manifest = json.loads((directory / "manifest.json").read_text())
            timestamp(manifest["built_at"])
            frames = {}
            for name, columns, dataset in (
                ("forecasts.csv", FORECAST_COLUMNS, "WINDFOR"),
                ("actuals_half_hourly.csv", ACTUAL_COLUMNS, "FUELHH"),
            ):
                body = (directory / name).read_bytes()
                artifact = manifest["artifacts"][name]
                if (
                    hashlib.sha256(body).hexdigest() != artifact["sha256"]
                    or len(body) != artifact["bytes"]
                ):
                    raise DataError(f"Checksum/size mismatch: {name}")
                frame = pd.read_csv(io.BytesIO(body), dtype={"generation": str})
                if (
                    list(frame.columns) != columns
                    or manifest["schemas"][name] != columns
                ):
                    raise DataError(f"Schema mismatch: {name}")
                rows = frame.assign(dataset=dataset).to_dict("records")
                cleaned, _ = clean(rows, dataset)
                if len(cleaned) != len(rows):
                    raise DataError(
                        f"Noncanonical duplicate/out-of-scope records: {name}"
                    )
                frames[name] = frame
            super().__init__(
                frames["forecasts.csv"],
                frames["actuals_half_hourly.csv"],
                {
                    "built_at": manifest["built_at"],
                    "raw_chunks": len(manifest["chunks"]),
                    "inputs": {
                        name: artifact["sha256"]
                        for name, artifact in manifest["artifacts"].items()
                    },
                },
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise DataError(
                f"Cannot load validated local data from {directory}: {exc}"
            ) from exc
