# Wind Decision

A local analyst workspace for historical UK day-ahead wind purchasing decisions.
The Decision view shows the latest forecast available for each delivery hour at
a chosen D-1 cutoff. Accuracy compares those same selections with hourly Elexon
WIND actuals, with coverage, error metrics and transparent historical context.

Decision dates: **1–31 January 2026**. Delivery dates: **2 January–1 February 2026**.
All times are UTC. The default **D-1 09:30 UTC** cutoff is assumed decision timing,
not a verified market gate closure. The data source is Elexon national WIND only.

## Run with Docker

Prerequisite: Docker with Compose and a running daemon. From the root:

```sh
docker compose up --build
```

Open [the production demo](http://localhost:8080). Nginx serves built assets and
proxies `/api/` to the internal backend, which validates and loads embedded
processed data at startup. No host Python/Node/uv or data volume is required.
Initial images/dependencies need internet; backend runtime traffic stays on an internal
network, while the frontend publishes port 8080 on its edge network. Backend health is awaited before frontend startup.

Detached startup, checks, rebuild and shutdown:

```sh
docker compose config --quiet
docker compose build
docker compose up -d --wait --wait-timeout 90
docker compose exec -T backend python - < scripts/smoke_docker.py
docker compose up -d --build --force-recreate --wait --wait-timeout 90
docker compose down
```

Remote hosting is separate; Vercel would need its own `/api` routing configuration.

## Native development installation

Use Python **3.13.x**, Node **24.x**, npm **11.x**, uv **0.12.19**. From the root:

```sh
uv sync --project backend --frozen
npm ci --prefix frontend
```

uv creates `backend/.venv`; both runtime and development dependencies are locked
in `backend/uv.lock`. npm uses `frontend/package-lock.json`. Keep both lockfiles
when placing this folder under version control. No global test/lint packages are
needed. The real datasets already exist locally; startup does not download data.

## Run the native development demo

Terminal 1, from the root:

```sh
backend/.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2, from the root:

```sh
npm run dev --prefix frontend
```

Open [Wind Decision](http://127.0.0.1:5173). Use the Decision / Accuracy navigation.
Delivery day and range pickers are constrained by API metadata; choose an HH:MM
D-1 cutoff. Expand the hourly data and breakdown tables for accessible exact
values, source publication times, sample counts and horizons.

Vite proxies `/api` to `http://127.0.0.1:8000`; frontend port 5173 is strict.
[API docs](http://127.0.0.1:8000/docs) describe the typed responses.
Stop each server with Ctrl+C. No external network is needed once dependencies and
local datasets are installed. The Vite proxy is for native local development; the Docker path above uses
Nginx for production serving. Remote deployment remains deferred.

Optional settings: copy `.env.example` to `.env`. `WIND_CORS_ORIGINS` is a JSON
array, `WIND_LOG_LEVEL` defaults to INFO, `WIND_DEFAULT_CUTOFF` defaults to 09:30,
and `WIND_PROCESSED_DIR` can override the validated cache directory (prefer an
absolute path). The default directory resolves relative to source, independent
of cwd. `.env` is read from cwd; environment variables take precedence.

## Verify and reproduce analysis

```sh
backend/.venv/bin/ruff check backend scripts
backend/.venv/bin/ruff format --check backend scripts
backend/.venv/bin/python -m pytest backend/tests
npm run lint --prefix frontend
npm run test --prefix frontend -- --run
npm run build --prefix frontend
backend/.venv/bin/python scripts/analyze_wind.py
backend/.venv/bin/python scripts/verify_elexon_cache.py
```

The analysis command is offline and writes only `docs/analysis.md` and
`docs/regression-baseline.json`. It computes the corrected full-scope baseline and
alignment shifts -3..+3 on a common subset. The bias cause remains unknown; no
shift/scale correction is applied to the app. The read-only cache verifier blocks
HTTP/sockets while rebuilding copies in a temporary directory and checks original
raw/processed integrity, provenance, identical CSVs, and complete timestamp grids.

With both servers running, sample proxy checks:

```sh
curl --fail 'http://127.0.0.1:5173/api/v1/metadata'
curl --fail 'http://127.0.0.1:5173/api/v1/forecasts?delivery_date=2026-01-02&cutoff_time=09:30'
curl --fail 'http://127.0.0.1:5173/api/v1/forecasts?delivery_date=2026-02-01&cutoff_time=00:00'
curl --fail 'http://127.0.0.1:5173/api/v1/accuracy?delivery_from=2026-01-02&delivery_to=2026-02-01&cutoff_time=09:30'
```

Health at `/api/v1/health` is process liveness only. During normal startup the API
validates CSV schemas/hashes and prepares actuals once; requests use memory and
never reread files or contact Elexon. Restart to load a refreshed cache.

## Data maintenance

```sh
backend/.venv/bin/python scripts/ingest_elexon.py
backend/.venv/bin/python scripts/ingest_elexon.py --offline
backend/.venv/bin/python scripts/ingest_elexon.py --repair
```

Default ingestion verifies/reuses daily raw chunks; offline requires all chunks;
repair authentically redownloads only missing/invalid raw pairs. `--refresh` forces
all 64 requests. See `scripts/README.md` for retries, provenance and failure
protection. Ingestion is separate from app startup and requests. Raw and processed
data are eligible for later version control; this folder has no Git repository.

## Structure and interpretation

- `backend/app/services/analytics.py`, `buffer.py`: pure selection, aggregation,
  metrics and descriptive historical purchasing context.
- `backend/app/data/repository.py`: replaceable startup-loaded local repository.
  `ingestion.py`, `cleaning.py`: separate downloader and deterministic validation.
- `backend/app/api/v1/`, `schemas/`: metadata, forecasts, accuracy, health, typed
  contracts and consistent error envelopes. `core/`: settings and JSON logging.
- `backend/tests/`: isolated fixtures and frozen real-data regression checks;
  tests need no Elexon access and do not modify production data.
- `frontend/src/`: connected pages, chart/table/state components, typed API client,
  cancellation/stale-response protection, UTC formatting and UI behavior tests.
- `data/raw/`: authentic source bytes and provenance sidecars;
  `data/processed/`: forecast/half-hour actual CSVs and checksum manifest.
- `scripts/`: ingestion, read-only cache verification, offline analysis and a
  container smoke check.
- `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`,
  `.dockerignore`, `docker-compose.yml`: production containers and same-origin
  proxy. Local Docker instructions are above.
- `.github/workflows/ci.yml`: locked installs, backend lint/format/tests and
  frontend lint/tests/build. Hosted CI is not claimed without a repository.

Missing values remain missing. Metrics use pairs; MAPE excludes zero actuals only
from its own denominator. Positive bias means over-forecast. P90 absolute error
uses linear interpolation and is historical magnitude, not an optimal or
calibrated purchasing buffer. Demand, prices and risk preferences are not modeled.

## AI assistance and remaining delivery scope

OpenAI Codex assisted with implementation, analysis, documentation and verification.
Review the analysis and source before submission. This milestone completes the
local demo and Docker packaging; deployment, public repository publication, demo video and
submission remain deferred. There is no deployed application URL at this stage.
