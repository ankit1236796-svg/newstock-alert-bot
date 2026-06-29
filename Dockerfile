# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    APP_ENV=production \
    DATABASE_URL=sqlite+aiosqlite:////app/data/newstock_alert_bot.sqlite3 \
    STOCK_CHECK_INTERVAL_SECONDS=300 \
    LOG_LEVEL=INFO \
    PLAYWRIGHT_TIMEOUT=30 \
    MAX_CONCURRENT_CHECKS=2

WORKDIR /app

RUN groupadd --system --gid 10001 bot \
    && useradd --system --uid 10001 --gid bot --home-dir /app --shell /usr/sbin/nologin bot

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && python -m playwright install --with-deps chromium \
    && rm -rf /wheels /root/.cache/pip \
    && mkdir -p /app/data \
    && chown -R bot:bot /app /ms-playwright \
    && chmod 755 /app \
    && chmod 700 /app/data

USER bot

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python -m app.healthcheck

CMD ["python", "-m", "app"]
