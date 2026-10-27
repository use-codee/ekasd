# Both stages use the same Python minor/distribution for virtualenv compatibility.
FROM python:3.13-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
WORKDIR /build
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN uv sync --project backend --frozen --no-dev --no-install-project

FROM python:3.13-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WIND_PROCESSED_DIR=/app/data/processed \
    PORT=8000
WORKDIR /app
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
COPY backend/__init__.py ./backend/__init__.py
COPY backend/app ./backend/app
# Ingestion uses private host file modes; normalize image-only read permissions.
COPY data/processed/forecasts.csv data/processed/actuals_half_hourly.csv data/processed/manifest.json ./data/processed/
RUN chmod 0555 /app/data /app/data/processed \
    && chmod 0444 /app/data/processed/*
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import json,os,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/health',timeout=3); assert json.load(r)=={'status':'ok'}"
# Quoted runtime expansion plus exec preserves PORT and signal handling.
CMD ["sh", "-c", "exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
