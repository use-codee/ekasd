# Elexon ingestion

Run from the project root, using Python 3.13 and uv 0.12.19:

```sh
uv sync --project backend --frozen
backend/.venv/bin/python scripts/ingest_elexon.py
```

This sequential command downloads 33 WINDFOR publication windows (30 December
2025–31 January 2026, half-open daily UTC windows) and 31 FUELHH WIND settlement
days (2 January–1 February 2026 inclusive). It then validates the entire input,
writes two CSVs and a manifest in `data/processed/`, and generates
`docs/data-quality.md`. No API process is needed. It never starts FastAPI.

Default reruns verify and reuse successful raw chunks, downloading only missing
chunks. A body or metadata file without its partner, invalid JSON, checksum/count
mismatch, or invalid provenance stops the run with a clear error. Source records
are also validated before processed publication. Completed raw chunks remain
available after failures. Empty source arrays are valid responses, but their gaps
are reported explicitly and never filled.

Rebuild without HTTP or an HTTP client (all 64 raw inputs required):

```sh
backend/.venv/bin/python scripts/ingest_elexon.py --offline
```

Force an explicit refresh of all daily requests:

```sh
backend/.venv/bin/python scripts/ingest_elexon.py --refresh
```

Repair only missing or invalid raw/provenance pairs, reusing all valid chunks:

```sh
backend/.venv/bin/python scripts/ingest_elexon.py --repair
```

Refresh, repair and offline flags are mutually exclusive. Repair validates each
pair offline and redownloads failures using the same HTTP retry/timeout policy;
it never replaces a sidecar hash to approve existing unverified bytes. Preserve
mismatch evidence before invoking repair because successful source downloads
replace affected bodies and sidecars. Valid chunks keep their original download
provenance. A failed repair retains completed downloads and protects processed
output until all inputs validate. Repair checks raw/provenance integrity; source
schema errors in a checksum-valid pair still block processing.

Refresh replaces all successfully fetched raw chunks and metadata. An interrupted
refresh/repair can leave different download times, which the manifest preserves.
Never edit source values or sidecar checksums to bypass validation.

## HTTP policy and storage

No credentials are needed. Each request uses a 30-second HTTP I/O timeout, with
four attempts maximum. Only network/transport errors, 429, and 5xx are retried.
Exponential backoff is 1, 2, 4 seconds without a Retry-After header. Valid numeric
or HTTP-date Retry-After values extend the delay up to a **30-second cap per
wait**, so a large server-requested delay is capped; total sleep is at most 90
seconds per chunk. These are I/O timeouts, not a hard wall-clock process deadline.
Permanent 4xx and malformed successful responses fail immediately. Logs record
dataset, daily window, attempt, HTTP status/failure, cache state and record count.

Successful response bytes are stored unchanged in `data/raw/{windfor,fuelhh}/`.
Each daily `.meta.json` sidecar records endpoint, exact query, SHA-256, record
count, and original UTC download time. Raw byte checksums, not rewritten JSON,
verify reuse. Metadata and bodies use atomic individual replacements; an
interruption between them is detected as an incomplete/mismatched cache.

CSV serialization uses standard-library `csv` and `Decimal`: no binary float
rounding of JSON decimal generations, no clipping, and no fabricated rows.
All validation and serialization finish before processed output is touched.
Each output is atomically replaced, with rollback on recoverable write errors.
The CSVs, manifest and Markdown are not a single crash-atomic filesystem
transaction. After a power loss during publication, rerun offline and verify
checksums before consumption. Concurrent ingestion writers are unsupported;
run one command at a time.

The manifest records transformation version, source queries, complete raw chunk
provenance, schemas/types, processed CSV hashes/sizes, scope, and cleaning/coverage
counts. Offline rebuilds preserve original download times; build time, offline
flag and per-run reuse states change, while CSV bytes remain deterministic.

## Verify

```sh
backend/.venv/bin/ruff check backend scripts
backend/.venv/bin/ruff format --check backend scripts
backend/.venv/bin/python -m pytest backend/tests
backend/.venv/bin/python scripts/verify_elexon_cache.py
```

The final command requires the real cache. It blocks HTTP and socket connection
creation, exercises default reuse and two offline rebuilds in an isolated copy,
checks unchanged CSV
checksums/download provenance, revalidates stored schemas/UTC grids/scope, checks
unique sorted keys and asserts the observed complete 1488/744 timestamp grids.
If source data changes to introduce gaps, that strict verification fails; the
quality report still reports the real gaps honestly. Default pytest uses only
mocked HTTP and small synthetic fixtures; it does not need the real cache or
Elexon access. Verification is read-only for the project: it audits original raw
and processed checksums before rebuilding in a temporary copied raw directory,
then checks the original manifest/report and actual CSVs. It preserves production
bodies, sidecars, CSVs, manifest and report bytes, including build timestamps.

For an independent read-only integrity audit without rebuilding:

```sh
backend/.venv/bin/python scripts/verify_elexon_cache.py --audit-only
```

This checks all 64 expected raw paths for JSON parseability, checksum, row count,
endpoint, exact query window, UTC download time and manifest provenance, plus
stored CSV hashes/sizes. It reports all raw failures together. Run the full
verifier to also check semantic validation, reproducibility and timestamp coverage.

Ingestion is separate from the app. FastAPI now loads validated processed files
once at startup, aggregates actuals and serves metadata/decision/accuracy from
memory. Requests never read files or contact Elexon. Restart the API after an
intentional cache refresh. Run `backend/.venv/bin/python scripts/analyze_wind.py`
to reproduce the offline baseline and alignment diagnosis in analysis docs only.
