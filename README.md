# Wind Decision

A wind forecast analysis app for a UK utility's day-ahead power purchasing team.
It reconstructs the forecasts available at a chosen decision time and measures
their accuracy against actual generation using Elexon national wind data.

**[Open the live application](https://ekasd.vercel.app/)**

**[Watch the demo video](https://youtu.be/VNEoEWaZmj4)** — customer presentation
and technical walkthrough.

The frontend runs on Vercel and the Dockerized FastAPI backend runs on Render.
The backend may take a moment to respond after inactivity.

## Features

- **Decision view:** select a delivery day and the previous day's decision cutoff
  to see the latest eligible forecast for each delivery hour, including
  publication timestamps, forecast horizons and coverage.
- **Accuracy view:** compare historical forecast selections with actual generation
  over a delivery range. Review MAE, signed bias, P90 absolute error, RMSE and MAPE,
  with breakdowns by forecast horizon, delivery hour and delivery day.
- **Transparent results:** missing observations remain gaps, sample counts are
  visible, and assumptions and limitations accompany the analysis.
- **Browser caching:** date selections persist between tabs, identical queries
  reuse cached results, and Refresh data rechecks the current selection while
  retaining its displayed results.

## Scope and assumptions

- Purchase decisions: **1–31 January 2026**, covering delivery dates
  **2 January–1 February 2026**.
- Source: Elexon **WINDFOR** forecasts and **FUELHH**, filtered to `WIND`, at
  national level. All timestamps and controls use **UTC**.
- The default cutoff is **09:30 UTC on D-1**. This is an assumed decision time,
  not a verified market gate closure.
- A WINDFOR timestamp is assumed to begin a one-hour delivery interval. For each
  hour, the app selects the latest publication at or before the decision cutoff.
  Forecasts published after their target time are excluded, and duplicate
  publication/target pairs are removed.
- Both datasets report power in **MW**. Hourly actual generation is the mean of
  two distinct half-hour observations; both must exist.
- Error is **forecast minus actual**: positive bias means wind was over-forecast.
  Metrics use matched observations. Zero actuals are excluded only from MAPE.
  P90 uses linear percentile interpolation.

For the full delivery range at the default cutoff, there are **744 paired hours**.
MAE is approximately **2,013 MW**, signed bias **+1,730 MW**, and P90 absolute error
**4,144 MW**. The cause of the positive bias remains unresolved; alignment
diagnostics did not establish an explanation. No time-shift or scale correction
is applied.

These statistics describe historical forecast error. They do not establish an
optimal purchase amount or guarantee future shortage coverage. Demand, existing
contracts, portfolio allocation, prices and risk preferences are outside scope.

## Run with Docker

With Docker and Docker Compose installed, run from the repository root:

```sh
docker compose up --build
```

Open **[http://localhost:8080](http://localhost:8080)**. Processed data is included
in the backend image; no Elexon credentials or ingestion step are required.
Internet access is needed for initial image and dependency downloads.

To stop the services:

```sh
docker compose down
```

## Run for development

Prerequisites: **Python 3.13.x**, **Node.js 24.x**, **npm 11.x** and
**uv 0.12.19**. Install dependencies from the repository root:

```sh
uv sync --project backend --frozen
npm ci --prefix frontend
```

Start the backend:

```sh
backend/.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, start the frontend:

```sh
npm run dev --prefix frontend
```

Open **[http://localhost:5173](http://localhost:5173)**. Interactive API
documentation is available at **[http://localhost:8000/docs](http://localhost:8000/docs)**.

Optional configuration is documented in `.env.example`. Copy it to `.env` in
the repository root to override the default cutoff, logging, CORS origins or
processed-data directory. Environment variables take precedence. Keep `.env`
out of version control.

## Architecture and data flow

```text
Elexon WINDFOR / FUELHH
        |
        v
Separate ingestion -> raw responses -> cleaned CSVs + checksum manifest
                                                |
                                                v
                                  FastAPI startup validation
                                                |
                                                v
                                  In-memory data repository
                                                |
                                                v
                                   /api/v1 -> React views
```

The API loads validated processed files once at startup. Requests run against
that in-memory snapshot and do not download from Elexon or reread data files.
The repository interface allows a future scheduled refresh process to be added
without coupling ingestion to user requests.

The frontend makes relative `/api/v1` requests. Vite proxies them during local
development, Nginx proxies them in Docker Compose, and `frontend/vercel.json`
forwards them to the Render backend in the deployed app.

Browser queries remain fresh for five minutes; inactive results are retained
for 30 minutes. Stale queries may refresh on remount, window focus or network
reconnection. Refresh data rechecks the selected result and metadata, while
dataset checksum changes invalidate cached analytics. The browser cache resets
on a page reload. New Elexon data requires separate ingestion and a backend
restart or redeployment.

## Repository structure

| Path | Purpose |
| --- | --- |
| `backend/app/api/v1/` | Versioned metadata, forecast, accuracy and health routes |
| `backend/app/services/` | Forecast selection, hourly aggregation, metrics and historical risk context |
| `backend/app/data/` | Ingestion, cleaning and validated data repositories |
| `backend/app/schemas/` | Typed API responses and error contracts |
| `backend/app/core/` | Environment configuration and structured logging |
| `backend/tests/` | Unit, API, ingestion and real-data regression tests |
| `frontend/src/pages/` | Decision and Accuracy views |
| `frontend/src/components/` | Charts, tables, loading, error and refresh states |
| `frontend/src/api/`, `frontend/src/hooks/`, `frontend/src/types/` | API client, query cache, request hook and TypeScript contracts |
| `frontend/src/App.test.tsx` | Component and query behavior tests |
| `data/raw/` | Source responses and provenance sidecars |
| `data/processed/` | Cleaned forecast and half-hour actual CSVs with checksum manifest |
| `scripts/` | Ingestion, cache verification, analysis and Docker smoke checks |
| `backend/Dockerfile`, `frontend/Dockerfile` | Multi-stage container builds |
| `docker-compose.yml`, `frontend/nginx.conf` | Local service orchestration and API proxy |
| `frontend/vercel.json` | Deployed frontend-to-backend API routing |
| `.github/workflows/ci.yml` | Backend lint, formatting and tests; frontend lint, tests and build |
| `.env.example`, `.python-version`, `.node-version` | Configuration example and runtime versions |

## Validation

Run from the repository root:

```sh
backend/.venv/bin/ruff check backend scripts
backend/.venv/bin/ruff format --check backend scripts
backend/.venv/bin/python -m pytest backend/tests
npm run lint --prefix frontend
npm run test --prefix frontend -- --run
npm run build --prefix frontend
```

Tests cover cutoff boundaries and future-data leakage, hourly aggregation,
duplicates, invalid horizons, missing data, metric calculations, API validation,
real-data regression values, frontend states and cache behavior. GitHub Actions
runs backend and frontend checks on pushes and pull requests.

With Docker Compose running, verify the containerized application:

```sh
docker compose exec -T backend python - < scripts/smoke_docker.py
```

## Data reproduction

The committed processed dataset allows the app to run without external data
access. To download or rebuild data separately:

```sh
backend/.venv/bin/python scripts/ingest_elexon.py
backend/.venv/bin/python scripts/ingest_elexon.py --offline
```

Ingestion uses daily chunks, retry/backoff for rate limits, provenance records
and deterministic cleaning. The default run reuses verified raw chunks; offline
mode requires the complete raw cache. See `scripts/README.md` for ingestion options.

To verify the cache and reproduce the analysis:

```sh
backend/.venv/bin/python scripts/verify_elexon_cache.py
backend/.venv/bin/python scripts/analyze_wind.py
```

The verifier checks integrity and reproduces processed CSVs from temporary copies
with network access blocked. The analysis command generates local reports in
`docs/`, including the regression baseline and alignment diagnostic. Neither
command changes the running backend snapshot.

## AI assistance

OpenAI Codex was used to assist with implementation, analysis, documentation and
verification.
