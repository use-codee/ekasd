"""Run from the project root with backend/.venv/bin/python scripts/ingest_elexon.py."""

import argparse
import logging
import sys
from pathlib import Path

# Direct script execution puts scripts/, rather than the project root, on sys.path.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from backend.app.core.logging import configure_logging  # noqa: E402
from backend.app.data.cleaning import QualityError  # noqa: E402
from backend.app.data.ingestion import IngestionError, build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Elexon January decision-scope data"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline",
        action="store_true",
        help="Require all verified raw cache files; no HTTP",
    )
    mode.add_argument(
        "--refresh", action="store_true", help="Redownload all daily chunks"
    )
    mode.add_argument(
        "--repair",
        action="store_true",
        help="Redownload only missing or invalid raw/provenance pairs",
    )
    args = parser.parse_args()
    configure_logging("INFO")
    try:
        if args.offline:
            manifest = build(ROOT, offline=True)
        else:
            with httpx.Client(headers={"Accept": "application/json"}) as client:
                manifest = build(
                    ROOT, refresh=args.refresh, repair=args.repair, client=client
                )
        logging.info("Published processed cache: %s", manifest["artifacts"])
    except (IngestionError, QualityError, OSError) as exc:
        logging.error("Ingestion failed; completed raw chunks retained: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
