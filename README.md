# NewStock Alert Bot

Production-ready async Telegram stock alert bot focused on Amazon India stock tracking.

The bot starts Telegram polling, initializes the SQLite database automatically, and runs a recurring background scheduler that checks active product alerts.

## Stack

- Python 3.12
- aiogram 3.x for Telegram bot integration
- Playwright Chromium for Amazon checks
- SQLite through `aiosqlite` for async persistence
- APScheduler for recurring stock checks
- Pydantic Settings for environment-backed configuration
- Docker and Docker Compose for production deployment

## Module layout

```text
app/
  bot/                         aiogram Bot and Dispatcher factories plus Telegram command routers.
  core/                        typed settings loaded from environment variables and .env files.
  database/                    SQLite connection lifecycle, schema creation, and repository implementations.
  domain/entities/             pure typed dataclasses and enums for users, products, pincodes, and stock checks.
  domain/repositories/         repository protocols that keep business logic independent from SQLite.
  integrations/marketplaces/   shared marketplace adapter contracts and Amazon implementation.
  observability/               structured logging setup for container-friendly production logs.
  services/browser/            Playwright browser session lifecycle.
  services/notifications/      notification protocol and Telegram alert delivery.
  services/scheduler/          APScheduler setup and recurring stock-check job.
```

## Configuration

Create a `.env` file before running locally or with Docker Compose:

```bash
cp .env.example .env
```

Required and production-facing variables:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `BOT_TOKEN` | Yes | - | Telegram bot token from BotFather. `TELEGRAM_BOT_TOKEN` is still accepted for compatibility. |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./data/newstock_alert_bot.sqlite3` locally, `/app/data/...` in Docker | Async SQLAlchemy SQLite URL. |
| `STOCK_CHECK_INTERVAL_SECONDS` | No | `300` | Scheduler interval for background stock checks. |
| `LOG_LEVEL` | No | `INFO` | Python logging level. |
| `PLAYWRIGHT_TIMEOUT` | No | `30` | Playwright launch/navigation timeout in seconds. |
| `MAX_CONCURRENT_CHECKS` | No | `2` | Maximum concurrent background stock checks. |

Additional optional variables include `APP_ENV`, `SCHEDULER_TIMEZONE`, `BROWSER_HEADLESS`, browser pool settings, Amazon retry/backoff settings, and the browser user agent.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
cp .env.example .env
python -m app
```

On startup the application:

1. Loads environment configuration.
2. Initializes the database schema if needed.
3. Starts the stock-check scheduler.
4. Starts Telegram polling.

On shutdown it stops the scheduler, closes the Playwright browser pool, disposes database connections, and closes the Telegram bot session.

## Docker build

Build the production image:

```bash
docker build -t newstock-alert-bot:latest .
```

Run the image directly:

```bash
docker run --rm \
  --env-file .env \
  -e DATABASE_URL=sqlite+aiosqlite:////app/data/newstock_alert_bot.sqlite3 \
  -v newstock-alert-bot-data:/app/data \
  newstock-alert-bot:latest
```

The Dockerfile uses a multi-stage build, Python 3.12 slim runtime, Playwright Chromium system dependencies, a non-root `bot` user, a persistent `/app/data` volume, and a container health check.

## Docker Compose

First create and edit `.env`:

```bash
cp .env.example .env
# edit BOT_TOKEN and any production tuning values
```

Start the bot:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f bot
```

Check status and health:

```bash
docker compose ps
```

Stop the bot:

```bash
docker compose down
```

The Compose file defines the bot service, a persistent named database volume, restart policy `unless-stopped`, environment variables, and JSON-file log rotation.

## First run

1. Create your Telegram bot with BotFather and copy its token.
2. Put the token in `.env` as `BOT_TOKEN=...`.
3. Start with `docker compose up -d --build`.
4. Open Telegram and send `/start` to the bot.
5. Use the existing bot commands to add and check Amazon products.

## Production deployment

Recommended production steps:

1. Build and tag an immutable image in CI.
2. Store `BOT_TOKEN` and other secrets in your deployment platform secret manager.
3. Mount `/app/data` to durable storage, or set `DATABASE_URL` to a durable SQLite path on a persistent volume.
4. Keep `BROWSER_HEADLESS=true` and tune `MAX_CONCURRENT_CHECKS` based on CPU and memory.
5. Use `docker compose up -d` or an equivalent orchestrator with restart policy enabled.
6. Monitor `docker compose logs -f bot` and container health checks.

## Useful checks

```bash
python -m app.healthcheck
pytest
ruff check .
```
